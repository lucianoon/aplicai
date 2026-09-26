"""Guardrails em camadas (LGPD, injeção de prompt, política de ações).

- ``redigir_pii_before_model``: mascara CPF, cartão, e-mail e telefone antes do
  texto chegar ao modelo e bloqueia tentativas de injeção de prompt. Em
  produção, substituir/complementar por Model Armor + Sensitive Data Protection
  no Agent Gateway.
- ``politica_before_tool``: fixa o titular da sessão (LGPD), exige cliente
  identificado, limita parâmetros e, nas ações, exige a aprovação do cliente
  (``exigir_aprovacao``): cotação calculada em código, aprovação pelo fluxo
  nativo do ADK (``request_confirmation``), válida por 5 minutos, uso único,
  e capacidade assinada que o core confere (``copiloto_fatura.autorizacao``).
  Vale igual para tools diretas e MCP. O LLM não tem como "confirmar sozinho".
- ``validar_saida_after_model``: mascara PII na resposta e bloqueia promessas
  indevidas (aprovação de crédito garantida, humano "já acionado" etc.) e respostas
  discriminatórias (inferência de saúde, religião, raça etc., estereótipo por grupo,
  restrição por idade, gênero ou negativação, ofensa).

Tudo determinístico, auditável e testável sem LLM (ver tests/test_guardrails.py).
"""

from __future__ import annotations

import json
import re
import secrets
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types

from copiloto_fatura.autorizacao import assinar, cotar, resumo
from copiloto_fatura.dlp_adapter import redigir_com_dlp
from mock_core.store import STORE

AUDIT_PATH = Path(__file__).resolve().parents[1] / "mock_core" / "audit.jsonl"

# A ordem importa: os padrões mais longos e específicos vêm antes (CNPJ antes de CPF,
# cartão antes de telefone). Os contextuais (RG, CVV, conta...) levam a palavra-chave junto.
PADROES_PII: list[tuple[str, re.Pattern[str]]] = [
    ("PIX", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)),
    ("CNPJ", re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b")),
    ("CPF", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("CARTAO", re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b|\b3[47]\d{2}[ -]?\d{6}[ -]?\d{5}\b")),
    ("RG", re.compile(r"\brg\b\D{0,6}\d[\d.\-xX]{5,12}|\b\d{1,2}\.\d{3}\.\d{3}-[\dxX]\b", re.I)),
    ("CVV", re.compile(r"\b(cvv|cvc|c[oó]digo\s+(de\s+seguran[cç]a|atr[aá]s|do\s+verso))\D{0,15}\d{3,4}\b", re.I)),
    ("NASCIMENTO", re.compile(r"\b(nasci|nascimento|nascid[oa])\D{0,20}\d{1,2}/\d{1,2}/\d{2,4}\b", re.I)),
    ("CONTA", re.compile(r"\b(ag[eê]ncia|ag\.)\s*:?\s*\d{3,5}(-\d)?\b|\bconta(\s+corrente|\s+poupan[cç]a)?\s*:?\s*(n[ºo°]\.?\s*)?\d{4,12}(-[\dxX])?\b", re.I)),
    ("ENDERECO", re.compile(r"\b(rua|avenida|av\.|travessa|alameda|estrada|rodovia|pra[cç]a)\s+[^,\n\d]{2,60},?\s*(n[ºo°]?\.?\s*)?\d{1,5}\b", re.I)),
    ("CEP", re.compile(r"\b\d{5}-\d{3}\b")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("TELEFONE", re.compile(r"(?<!\d)(\+?55\s?)?\(?\d{2}\)?\s?(9\d{4}|[2-5]\d{3})-?\d{4}(?!\d)")),
]

PADROES_INJECAO = re.compile(
    r"(ignore\s+(as|suas|todas\s+as)\s+instru|"
    r"system\s*prompt|prompt\s+do\s+sistema|"
    r"revele?\s+(suas|as)\s+instru|"
    r"modo\s+desenvolvedor|developer\s+mode|jailbreak|"
    r"finja\s+que\s+(você|voce)\s+(é|e)|"
    r"(você|voce)\s+agora\s+(é|e)\s+um|"
    r"esque[çc]a\s+(tudo|suas\s+regras))",
    re.IGNORECASE,
)

ACOES_SENSIVEIS = {"parcelar_fatura", "pagar_fatura", "aplicar_cdb", "resgatar_cdb"}
TOOLS_EXIGEM_CLIENTE = {"analisar_fatura", "analisar_caixa_e_liquidez", "simular_investimento",
                        "registrar_preferencia", "registrar_consentimento",
                        "meus_dados", "apagar_meus_dados", "agendar_lembrete",
                        "acompanhar_progresso", *ACOES_SENSIVEIS}
MAX_PARCELAS = 24
VALIDADE_APROVACAO_S = 300
CHAVE_APROVACAO = "aprovacao:"
CHAVE_CAPACIDADE = "capacidade:"  # lida por tools/acao.py
# guarda o id da invocação já auditada: callbacks rodam a cada chamada ao modelo
CHAVE_INVOCACAO_AUDITADA = "guardrail_ultima_invocacao"

MSG_INJECAO = (
    "Não posso atender a esse pedido. Eu ajudo com a sua fatura do cartão: "
    "posso mostrar quanto custa cada forma de pagar e executar a opção que você escolher."
)


def redigir(texto: str) -> tuple[str, dict[str, int]]:
    """Mascara PII e devolve o texto limpo e a contagem por tipo.

    Se COPILOTO_USE_CLOUD_DLP=1, tenta a API do Cloud DLP com fallback transparente
    para os padrões regex locais caso a nuvem esteja indisponível.
    """
    dlp_res = redigir_com_dlp(texto)
    if dlp_res is not None:
        return dlp_res

    contagem: dict[str, int] = {}
    for tipo, padrao in PADROES_PII:
        texto, n = padrao.subn(f"[{tipo}_REDIGIDO]", texto)
        if n:
            contagem[tipo] = n
    return texto, contagem


def normalizar(texto: str) -> str:
    """Desfaz ofuscações simples: acentos, caracteres invisíveis e leetspeak (1gn0r3 -> ignore)."""
    texto = unicodedata.normalize("NFKD", texto.casefold())
    texto = "".join(c for c in texto if not unicodedata.combining(c) and unicodedata.category(c) != "Cf")
    return texto.translate(str.maketrans("03415", "oeais"))


def detectar_injecao(texto: str) -> bool:
    return bool(PADROES_INJECAO.search(texto) or PADROES_INJECAO.search(normalizar(texto)))


def _audit(evento: dict[str, Any]) -> None:
    try:
        AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), **evento}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _texto(content: types.Content | None) -> str:
    if content is None or not content.parts:
        return ""
    return " ".join(p.text for p in content.parts if p.text)


def redigir_pii_before_model(callback_context: CallbackContext, llm_request: LlmRequest) -> LlmResponse | None:
    """Camada 1: sanitiza o que vai para o modelo. Roda em TODA chamada ao modelo.

    A redação vale para todo o histórico (a sessão guarda o texto original), mas
    a detecção de injeção e a contagem olham só a mensagem que abriu esta
    invocação (``user_content``). Assim, uma tentativa de injeção antiga não
    bloqueia os turnos seguintes e a PII não é recontada a cada chamada.
    """
    for content in llm_request.contents or []:
        if content.role != "user" or not content.parts:
            continue
        for part in content.parts:
            if part.text:
                part.text = redigir(part.text)[0]

    mensagem = _texto(callback_context.user_content)
    injecao = detectar_injecao(mensagem)
    if callback_context.state.get(CHAVE_INVOCACAO_AUDITADA) != callback_context.invocation_id:
        callback_context.state[CHAVE_INVOCACAO_AUDITADA] = callback_context.invocation_id
        _, contagem = redigir(mensagem)
        if contagem:
            callback_context.state["pii_redigida_total"] = callback_context.state.get("pii_redigida_total", 0) + sum(contagem.values())
            _audit({"guardrail": "pii_redigida", "agente": callback_context.agent_name, "tipos": contagem})
        if injecao:
            callback_context.state["injecoes_bloqueadas"] = callback_context.state.get("injecoes_bloqueadas", 0) + 1
            _audit({"guardrail": "injecao_bloqueada", "agente": callback_context.agent_name})
    if injecao:
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=MSG_INJECAO)]))
    return None


def politica_before_tool(tool: BaseTool, args: dict[str, Any], tool_context: ToolContext) -> dict[str, Any] | None:
    """Camada 2: política de acesso e de ação, antes de qualquer tool executar."""
    cliente_sessao = tool_context.state.get("cliente_id")
    cliente_arg = str(args.get("cliente_id") or "").strip().upper() or None

    if cliente_arg and cliente_sessao and cliente_arg != cliente_sessao:
        evento = "troca_de_titular_bloqueada" if tool.name == "iniciar_atendimento" else "acesso_terceiro_bloqueado"
        _audit({"guardrail": evento, "tool": tool.name, "sessao": cliente_sessao, "pedido": cliente_arg})
        return {
            "status": "bloqueado",
            "motivo": "LGPD: só posso tratar dados do titular desta sessão. Dados de outras pessoas não podem ser consultados.",
        }

    if tool.name in TOOLS_EXIGEM_CLIENTE and not cliente_sessao:
        return {"status": "bloqueado", "motivo": "Identifique o cliente com iniciar_atendimento antes de continuar."}

    if tool.name in ACOES_SENSIVEIS:
        n = args.get("n_parcelas")
        if isinstance(n, (int, float)) and n > MAX_PARCELAS:  # tipo inválido cai em autorizacao.parametros
            return {"status": "bloqueado", "motivo": f"máximo de {MAX_PARCELAS} parcelas"}
        args.pop("autorizacao", None)  # capacidade só o host emite; nunca aceitar do modelo
        remota = not isinstance(tool, FunctionTool)
        if remota:
            args["cliente_id"] = cliente_sessao  # tool MCP: o titular vem da sessão
        return exigir_aprovacao(tool.name, args, tool_context, cliente_sessao, remota)
    return None


def exigir_aprovacao(
    acao: str, args: dict[str, Any], tool_context: ToolContext, cliente_id: str, remota: bool
) -> dict[str, Any] | None:
    """Aprovação do cliente vinculada à cotação exata; devolve None só quando pode executar.

    1ª passagem: calcula a cotação, guarda como pendente e pede aprovação (a execução pausa).
    2ª passagem (o ADK reexecuta a mesma chamada com ``tool_confirmation``): consome a
    pendência e confere recusa, validade, edição da cotação e mudança de valores no core.
    Passou: assina a capacidade que o core vai conferir.
    """
    try:
        q = cotar(STORE, acao, cliente_id, args)
    except (ValueError, KeyError) as e:
        return {"status": "recusado", "motivo": str(e)}
    chave = CHAVE_APROVACAO + str(tool_context.function_call_id)
    pendente = tool_context.state.get(chave)
    confirmacao = tool_context.tool_confirmation

    if confirmacao is None:
        if pendente:
            return {"status": "bloqueado", "motivo": "aprovação já pedida para esta chamada; aguarde o cliente"}
        tool_context.state[chave] = {"cotacao": q, "expira": time.time() + VALIDADE_APROVACAO_S,
                                     "nonce": secrets.token_hex(16), "usada": False}
        tool_context.request_confirmation(hint=resumo(q), payload=q)
        # a pausa não é resultado para o modelo resumir; sem isso ele chamaria a tool de novo
        tool_context.actions.skip_summarization = True
        _audit({"guardrail": "aprovacao_solicitada", "tool": acao, "cliente": cliente_id})
        return {"status": "aguardando_aprovacao", "resumo": resumo(q)}

    if not pendente or pendente.get("usada"):
        return {"status": "bloqueado", "motivo": "aprovação ausente ou já usada; peça nova cotação"}
    tool_context.state[chave] = {**pendente, "usada": True}
    motivo = None
    if not confirmacao.confirmed:
        _audit({"guardrail": "acao_recusada_pelo_cliente", "tool": acao, "cliente": cliente_id})
        return {"status": "cancelado", "motivo": "o cliente não aprovou. Nada foi feito."}
    if pendente["expira"] < time.time():
        motivo = "a aprovação expirou"
    elif confirmacao.payload is not None and confirmacao.payload != pendente["cotacao"]:
        motivo = "a cotação aprovada foi alterada"
    elif pendente["cotacao"] != q:
        motivo = "os valores mudaram desde a aprovação"
    if motivo:
        _audit({"guardrail": "aprovacao_invalida", "tool": acao, "cliente": cliente_id, "motivo": motivo})
        return {"status": "bloqueado", "motivo": f"{motivo}; nada foi feito. Peça nova cotação ao cliente."}

    token = assinar(q, pendente["nonce"])
    if remota:
        args["autorizacao"] = token
    else:
        tool_context.state[CHAVE_CAPACIDADE + str(tool_context.function_call_id)] = token
    _audit({"guardrail": "acao_autorizada", "tool": acao, "cliente": cliente_id})
    return None


PROMESSAS_INDEVIDAS = re.compile(
    r"credito\s+(esta\s+|ja\s+)?(pre\s*-?\s*)?aprovado|aprovacao\s+(e\s+)?garantida|garant\w*\s+(a\s+|que\s+)?(sua\s+)?aprova|"
    r"emprestimo\s+sem\s+juros|sem\s+consulta\s+(ao\s+|a\s+)?(serasa|spc)|"
    r"ja\s+acionei\s+(um\s+|uma\s+)?(especialista|humano|atendente|gerente)"
)
NEGACAO = re.compile(r"\b(nao|nunca|nem|sem|jamais)\b")


def promessa_indevida(texto: str) -> bool:
    """Promessa sem negação logo antes ("não posso garantir a aprovação" passa)."""
    normal = normalizar(texto)
    return any(
        not NEGACAO.search(normal[max(0, m.start() - 30):m.start()])
        for m in PROMESSAS_INDEVIDAS.finditer(normal)
    )


MSG_SAIDA = (
    "Não consigo te responder isso com segurança. Posso mostrar os valores da sua fatura "
    "e as formas de pagar, sem prometer aprovação de crédito."
)

# Equidade: inferir característica pessoal, generalizar por grupo, usar atributo pessoal
# para restringir ou ofender. Roda sobre o texto normalizado (sem acento, minúsculo).
DISCRIMINACAO = re.compile(
    r"(voce|a\s+senhora|o\s+senhor)\s+(esta|parece|deve\s+estar|deve\s+ser|e|anda)\s+"
    r"(doente|deprimid\w*|ansios\w*|gravida|viciad\w*|alcoolatra|dependente\s+quimic\w*)|"
    # inferência a partir dos dados; citar "sua saúde" sem inferir (ex.: "procure um médico") passa
    r"\b(mostra|mostram|indica|indicam|sugere|sugerem|revela|revelam|parece)\s+que\s+(voce|a\s+senhora|o\s+senhor)\s+"
    r"(esta|tem|anda|e)\s+(com\s+)?(algum\w*\s+|uma\s+)?(doente|deprimid\w*|gravida|doenca|problema\s+de\s+saude)|"
    r"\b(sua|seu|tua|teu)\s+(doenca|gravidez|religiao|orientacao\s+sexual|raca|etnia|cor\s+de\s+pele|partido)|"
    r"\b(mulheres|homens|idosos|idosas|velhos|jovens|pobres|negros|nordestinos|evangelicos|aposentados)\s+"
    r"(costumam|sempre|geralmente|tendem|nao\s+sabem|gastam\s+mais)|"
    r"\b(por|como)\s+(ser|voce\s+e|a\s+senhora\s+e|o\s+senhor\s+e|(voce|a\s+senhora|o\s+senhor)\s+ja\s+tem|ja\s+ter|ter)\s+"
    r"[\w\s]{0,20}?(idade|idos|velh|jovem|mulher|homem|negativad|pobre|aposentad)|"
    r"\b(pobre\s+demais|burr[oa]|idiota|imbecil|vagabund\w*|preguicos\w*|caloteir\w*|macaco|crioulo|retardad\w*)\b"
)
MSG_RESPEITO = (
    "Não posso responder isso. Eu ajudo com os valores e as formas de pagar a sua fatura, "
    "do mesmo jeito para qualquer pessoa, sem fazer suposições sobre você."
)


def discriminatoria(texto: str) -> bool:
    """Inferência sensível, estereótipo, restrição por atributo pessoal ou ofensa, sem negação logo antes."""
    normal = normalizar(texto)
    return any(
        not NEGACAO.search(normal[max(0, m.start() - 45):m.start()])
        for m in DISCRIMINACAO.finditer(normal)
    )


def validar_saida_after_model(callback_context: CallbackContext, llm_response: LlmResponse) -> LlmResponse | None:
    """Camada 3: o que o modelo diz ao cliente.

    PII na resposta é mascarada; promessa indevida troca a resposta inteira por uma
    mensagem segura (e descarta chamadas de tool que vinham junto). Heurístico e
    conservador: não substitui avaliação semântica nem revisão humana.
    """
    content = llm_response.content
    if not content or not content.parts:
        return None
    partes_texto = [p for p in content.parts if p.text and not p.thought]
    if not partes_texto:
        return None
    if promessa_indevida(" ".join(p.text for p in partes_texto)):
        _audit({"guardrail": "promessa_bloqueada", "agente": callback_context.agent_name})
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=MSG_SAIDA)]))
    if discriminatoria(" ".join(p.text for p in partes_texto)):
        _audit({"guardrail": "resposta_discriminatoria_bloqueada", "agente": callback_context.agent_name})
        return LlmResponse(content=types.Content(role="model", parts=[types.Part(text=MSG_RESPEITO)]))
    total = 0
    for part in partes_texto:
        part.text, contagem = redigir(part.text)
        total += sum(contagem.values())
    if total:
        _audit({"guardrail": "pii_na_saida_redigida", "agente": callback_context.agent_name, "total": total})
        return llm_response
    return None
