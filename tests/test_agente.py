"""Tools do agente e fluxo de aprovação ponta a ponta, sem LLM real (zero tokens).

O ``RoteiroLlm`` devolve respostas pré-definidas: o que se testa aqui é o
runtime do ADK + guardrails + tools, não o modelo.
"""

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.genai import types

from copiloto_fatura import guardrails as g
from copiloto_fatura.tools.acao import parcelar_fatura
from copiloto_fatura.tools.contexto import analisar_fatura, iniciar_atendimento
from mock_core.store import STORE


@pytest.fixture(autouse=True)
def store_isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(STORE, "audit_path", tmp_path / "audit.jsonl")
    monkeypatch.setattr(STORE, "consent_path", tmp_path / "consentimentos.json")
    monkeypatch.setattr(g, "AUDIT_PATH", tmp_path / "guardrails.jsonl")
    STORE.reset()
    yield
    STORE.reset()


def _tctx(state):
    return SimpleNamespace(state=state)


def test_iniciar_atendimento_fixa_o_titular():
    state = {}
    assert iniciar_atendimento("c001", _tctx(state))["primeiro_nome"] == "Ana"
    assert state["cliente_id"] == "C001"
    r = iniciar_atendimento("C002", _tctx(state))
    assert r["status"] == "bloqueado" and state["cliente_id"] == "C001"


def test_preferencias_so_valores_permitidos_e_por_cliente():
    from copiloto_fatura.tools.contexto import registrar_preferencia

    state = {"cliente_id": "C001"}
    assert registrar_preferencia("canal", "whatsapp", _tctx(state))["status"] == "ok"
    assert registrar_preferencia("saude", "depressao", _tctx(state))["status"] == "bloqueado"
    assert registrar_preferencia("canal", "tenho depressão", _tctx(state))["status"] == "bloqueado"
    assert state["user:preferencias:C001"] == {"canal": "whatsapp"}
    outra = {"user:preferencias:C001": {"canal": "whatsapp"}}
    assert iniciar_atendimento("C003", _tctx(outra))["preferencias_lembradas"] == {}


def test_encaminhamento_e_simulado_e_nao_guarda_texto_livre():
    from copiloto_fatura.tools.acao import encaminhar_para_humano

    state = {}
    r = encaminhar_para_humano("cliente disse que tem depressão", SimpleNamespace(state=state, invocation_id="inv-12345678"))
    assert r["status"] == "encaminhamento_simulado" and "simulado" in r["mensagem"]
    assert state["motivo_escalonamento"] == "outro"


def test_persona_ana_e_o_caminho_feliz():
    """A demo principal: falta dinheiro para o total, mas cabe pagar parte e parcelar."""
    r = analisar_fatura(_tctx({"cliente_id": "C001"}))
    assert r["caixa"]["saldo_no_vencimento"] == 610.0
    assert r["recomendada_id"] == "parcial_mais_parcelamento" and r["requer_apoio_humano"] is False
    assert r["opcoes_para_apresentar"][0]["id"] == r["recomendada_id"]


def test_analise_apos_pagamento_parcial_usa_saldo_e_minimo_restantes():
    STORE.pagar_fatura("C001", 100.0, "parcial-100")
    r = analisar_fatura(_tctx({"cliente_id": "C001"}))
    assert r["fatura"]["total"] == 1850.0
    assert r["fatura"]["em_aberto"] == 1750.0
    assert r["fatura"]["minimo_restante"] == 177.5
    assert r["caixa"]["saldo_no_vencimento"] == 510.0
    assert r["caixa"]["falta_para_o_total"] == 1240.0
    assert next(o for o in r["outras_opcoes"] if o["id"] == "pagar_total")["custo_total"] == 1750.0

    STORE.pagar_fatura("C001", 449.0, "parcial-449")
    r = analisar_fatura(_tctx({"cliente_id": "C001"}))
    assert r["fatura"]["em_aberto"] == 1301.0
    assert r["fatura"]["minimo_restante"] == 0.0
    assert r["caixa"]["cabe_pagar_minimo"] is True
    assert not any("não cobre nem o mínimo" in alerta for alerta in r["alertas_de_caixa"])
    assert r["se_nao_fizer_nada"]["pagar_agora"] == 0.0


@pytest.mark.parametrize("acao,valor,status", [
    ("pagar", 1850.0, "paga"),
    ("parcelar", 6, "parcelada"),
])
def test_analise_nao_oferece_pagamento_para_fatura_encerrada(acao, valor, status):
    if acao == "pagar":
        STORE._cliente("C001")["saldo_conta"] = valor
        STORE.pagar_fatura("C001", valor, "quitacao")
    else:
        STORE.parcelar_fatura("C001", valor, "parcelamento")
    r = analisar_fatura(_tctx({"cliente_id": "C001"}))
    assert r["fatura"]["status"] == status
    assert r["recomendada_id"] is None
    assert r["opcoes_para_apresentar"] == r["outras_opcoes"] == []
    assert r["se_nao_fizer_nada"] is None


def test_carla_so_ve_parcelamentos_e_pede_humano():
    r = analisar_fatura(_tctx({"cliente_id": "C003"}))
    assert r["requer_apoio_humano"] is True
    assert all(o["id"].startswith("parcelar_fatura") for o in r["opcoes_para_apresentar"])


def test_analise_e_compacta_e_nunca_sugere_rotativo():
    for cid in ("C001", "C002", "C003", "C050"):
        r = analisar_fatura(_tctx({"cliente_id": cid}))
        assert len(r["opcoes_para_apresentar"]) <= 3
        assert all(o["id"] != "minimo_rotativo" for o in r["opcoes_para_apresentar"])
        assert len(str(r)) < 3000  # orçamento de tokens: vai para o histórico de todo turno


class RoteiroLlm(BaseLlm):
    model: str = "roteiro"
    respostas: list = []

    async def generate_content_async(self, llm_request, stream=False):
        yield self.respostas.pop(0)


def _chamada(nome, args):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(name=nome, args=args))]))


def _texto(t):
    return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=t)]))


_SEM_PAYLOAD = object()


async def _conversa(aprovar: bool, tools=None, args=None, antes_de_aprovar=None, payload=_SEM_PAYLOAD):
    llm = RoteiroLlm(respostas=[_chamada("parcelar_fatura", args or {"n_parcelas": 6}), _texto("pronto")])
    agente = LlmAgent(
        name="acao_teste", model=llm, instruction="teste",
        tools=tools or [FunctionTool(parcelar_fatura)],
        before_model_callback=g.redigir_pii_before_model,
        before_tool_callback=g.politica_before_tool,
        after_model_callback=g.validar_saida_after_model,
    )
    runner = InMemoryRunner(agent=agente, app_name="t")
    sessao = await runner.session_service.create_session(app_name="t", user_id="u", state={"cliente_id": "C001"})

    async def rodar(msg):
        return [e async for e in runner.run_async(user_id="u", session_id=sessao.id, new_message=msg)]

    eventos = await rodar(types.Content(role="user", parts=[types.Part(text="parcela em 6x")]))
    pedidos = [fc for e in eventos for fc in e.get_function_calls() if fc.name == "adk_request_confirmation"]
    assert len(pedidos) == 1, "a tool deveria pausar pedindo aprovação"
    pedido = pedidos[0]
    assert "6x de R$ 418,12" in str(pedido.args)  # o resumo mostrado ao cliente sai do código
    assert STORE.get_fatura("C001")["status"] == "aberta", "nada pode executar antes da aprovação"
    if antes_de_aprovar:
        antes_de_aprovar()

    decisao = {"confirmed": aprovar}
    if payload is not _SEM_PAYLOAD:
        decisao["payload"] = payload
    resposta = types.Content(role="user", parts=[types.Part(function_response=types.FunctionResponse(
        id=pedido.id, name="adk_request_confirmation", response=decisao))])
    eventos = await rodar(resposta)
    return [fr.response for e in eventos for fr in e.get_function_responses() if fr.name == "parcelar_fatura"]


async def test_acao_so_executa_depois_da_aprovacao():
    respostas = await _conversa(aprovar=True)
    assert respostas and respostas[-1]["status"] == "efetivado"
    assert STORE.get_fatura("C001")["status"] == "parcelada"


async def test_acao_recusada_nao_executa():
    respostas = await _conversa(aprovar=False)
    assert respostas and respostas[-1]["status"] == "cancelado"
    assert STORE.get_fatura("C001")["status"] == "aberta"


async def test_aprovacao_expirada_nao_executa(monkeypatch):
    monkeypatch.setattr(g, "VALIDADE_APROVACAO_S", -1)
    respostas = await _conversa(aprovar=True)
    assert respostas[-1]["status"] == "bloqueado" and "expirou" in respostas[-1]["motivo"]
    assert STORE.get_fatura("C001")["status"] == "aberta"


async def test_valores_mudaram_entre_pedido_e_aprovacao():
    def fatura_muda():
        STORE._cliente("C001")["fatura"]["valor_total"] = 2000.0

    respostas = await _conversa(aprovar=True, antes_de_aprovar=fatura_muda)
    assert respostas[-1]["status"] == "bloqueado" and "mudaram" in respostas[-1]["motivo"]
    assert STORE.get_fatura("C001")["status"] == "aberta"


async def test_cotacao_editada_no_canal_nao_executa():
    respostas = await _conversa(aprovar=True, payload={"acao": "parcelar_fatura", "n_parcelas": 2})
    assert respostas[-1]["status"] == "bloqueado" and "alterada" in respostas[-1]["motivo"]
    assert STORE.get_fatura("C001")["status"] == "aberta"


def test_sem_guardrail_o_core_recusa():
    """Defesa em profundidade: chamando a tool direto, sem capacidade, nada executa."""
    ctx = SimpleNamespace(state={"cliente_id": "C001"}, function_call_id="fc-x")
    r = parcelar_fatura(6, ctx)
    assert r["status"] == "bloqueado" and STORE.get_fatura("C001")["status"] == "aberta"


async def test_acao_via_mcp_com_capacidade_assinada():
    """Caminho MCP real (stdio): a capacidade forjada pelo modelo é descartada; o core confere a do host."""
    from google.adk.tools.mcp_tool import McpToolset, StdioConnectionParams
    from mcp import StdioServerParameters

    from copiloto_fatura.autorizacao import SEGREDO

    raiz = Path(__file__).resolve().parents[1]
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable, args=["-m", "mock_core.server"], cwd=str(raiz),
                env={**os.environ, "PYTHONUTF8": "1", "COPILOTO_AUTH_SECRET": SEGREDO},
            ),
            timeout=30,
        ),
        tool_filter=["parcelar_fatura"],
    )
    try:
        respostas = await _conversa(aprovar=True, tools=[toolset], args={"n_parcelas": 6, "autorizacao": "forjada"})
    finally:
        await toolset.close()
    resultado = json.loads(respostas[-1]["content"][0]["text"])
    assert resultado["status"] == "efetivado" and resultado["cliente_id"] == "C001" and resultado["canal"] == "mcp"
