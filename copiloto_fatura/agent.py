"""Copiloto da Fatura: sistema multiagente em ADK.

Topologia (separação de responsabilidades, item da rubrica de arquitetura):

    copiloto_fatura (orquestrador, Gemini Flash): conversa e decide o fluxo
      ├─ tool  iniciar_atendimento / registrar_preferencia  (identidade e memória)
      ├─ tool  registrar_consentimento / meus_dados / apagar_meus_dados  (LGPD)
      ├─ tool  analisar_fatura      (código determinístico: diagnóstico + opções em reais)
      ├─ tool  encaminhar_para_humano
      └─ sub   agente_acao          (executa no core, com aprovação do cliente)
                 └─ tools parcelar_fatura / pagar_fatura  (direto ou via MCP)

O diagnóstico é código, não um sub-agente: é determinístico, então um LLM ali
só somaria chamadas e tokens sem somar qualidade. LLM onde há conversa e
decisão; código onde há conta.

Guardrails em todos os agentes: PII + injeção (before_model), política e aprovação
das ações (before_tool) e saída (after_model: PII e promessas indevidas).

Variáveis de ambiente:
    COPILOTO_MODEL        modelo do orquestrador (default gemini-3.8-flash); "demo" = roteirizado, sem cota
    COPILOTO_MODEL_ACAO   modelo do agente de ação (default = COPILOTO_MODEL; use um lite)
    COPILOTO_THINKING     nível de raciocínio: minimal|low|medium|high (default low);
                          vazio desliga (modelos sem thinking_level, como os 2.5)
    COPILOTO_USE_MCP=1    usa o servidor MCP (mock_core.server) para as ações
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from copiloto_fatura import prompts
from copiloto_fatura.autorizacao import SEGREDO
from copiloto_fatura.guardrails import politica_before_tool, redigir_pii_before_model, validar_saida_after_model
from copiloto_fatura.rag import consultar_regras_e_politicas
from copiloto_fatura.tools.acao import (
    aplicar_cdb,
    encaminhar_para_humano,
    pagar_fatura,
    parcelar_fatura,
    resgatar_cdb,
)
from copiloto_fatura.tools.contexto import (
    acompanhar_progresso,
    agendar_lembrete,
    analisar_caixa_e_liquidez,
    analisar_fatura,
    apagar_meus_dados,
    consultar_extrato_detalhado,
    iniciar_atendimento,
    meus_dados,
    registrar_consentimento,
    registrar_preferencia,
    simular_investimento,
)

MODEL = os.getenv("COPILOTO_MODEL", "gemini-3.8-flash")
MODEL_ACAO = os.getenv("COPILOTO_MODEL_ACAO") or MODEL


def _modelo(nome: str):
    """`demo` = modelo roteirizado, sem internet e sem cota (plano B da apresentação)."""
    if nome == "demo":
        from copiloto_fatura.demo_llm import DemoLlm

        return DemoLlm()
    return nome
THINKING = os.getenv("COPILOTO_THINKING", "low").strip().upper()
RAIZ = Path(__file__).resolve().parents[1]


def _config() -> types.GenerateContentConfig | None:
    """Raciocínio baixo por padrão: tokens de thinking também contam na cota."""
    if not THINKING:
        return None
    return types.GenerateContentConfig(thinking_config=types.ThinkingConfig(thinking_level=THINKING))


def _tools_de_acao() -> list:
    if os.getenv("COPILOTO_USE_MCP") == "1":
        from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
        from mcp import StdioServerParameters

        return [
            McpToolset(
                connection_params=StdioConnectionParams(
                    server_params=StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "mock_core.server"],
                        cwd=str(RAIZ),
                        # mesmo segredo do host: o core MCP confere a capacidade assinada
                        env={**os.environ, "PYTHONUTF8": "1", "COPILOTO_AUTH_SECRET": SEGREDO},
                    ),
                    timeout=30,
                ),
                # aprovação e capacidade ficam em politica_before_tool, igual às tools diretas
                tool_filter=["parcelar_fatura", "pagar_fatura", "aplicar_cdb", "resgatar_cdb"],
            ),
            acompanhar_progresso,
        ]
    return [
        FunctionTool(parcelar_fatura),
        FunctionTool(pagar_fatura),
        FunctionTool(aplicar_cdb),
        FunctionTool(resgatar_cdb),
        acompanhar_progresso,
    ]


agente_acao = LlmAgent(
    name="agente_acao",
    model=_modelo(MODEL_ACAO),
    description="Executa a decisão do cliente (parcelar/pagar a fatura ou aplicar/resgatar no CDB) depois da aprovação dele.",
    instruction=prompts.ACAO,
    tools=_tools_de_acao(),
    generate_content_config=_config(),
    before_model_callback=redigir_pii_before_model,
    before_tool_callback=politica_before_tool,
    after_model_callback=validar_saida_after_model,
    disallow_transfer_to_peers=True,
)

root_agent = LlmAgent(
    name="copiloto_fatura",
    model=_modelo(MODEL),
    description="Copiloto de Caixa e Fatura: ajuda a decidir como pagar a fatura e como aplicar capital ocioso em liquidez diária, com contas em código.",
    instruction=prompts.ORQUESTRADOR,
    tools=[
        iniciar_atendimento,
        analisar_fatura,
        analisar_caixa_e_liquidez,
        simular_investimento,
        consultar_extrato_detalhado,
        consultar_regras_e_politicas,
        registrar_preferencia,
        registrar_consentimento,
        acompanhar_progresso,
        agendar_lembrete,
        meus_dados,
        apagar_meus_dados,
        encaminhar_para_humano,
    ],
    sub_agents=[agente_acao],
    generate_content_config=_config(),
    before_model_callback=redigir_pii_before_model,
    before_tool_callback=politica_before_tool,
    after_model_callback=validar_saida_after_model,
)
