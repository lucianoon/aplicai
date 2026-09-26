"""Tools de ação: executam no core bancário (mock) só com autorização do host.

A aprovação não acontece aqui: o ``before_tool_callback``
(``guardrails.exigir_aprovacao``) calcula a cotação, pede a aprovação do
cliente pelo fluxo nativo do ADK e, aprovada, deixa uma capacidade assinada no
estado da chamada. A tool só repassa essa capacidade ao core, que confere tudo
de novo (``Store.executar_autorizada``). Sem capacidade válida, nada executa,
mesmo que o guardrail seja removido por engano.
"""

from __future__ import annotations

from google.adk.tools.tool_context import ToolContext

from mock_core.store import STORE

CHAVE_CAPACIDADE = "capacidade:"
CATEGORIAS_ESCALONAMENTO = {"sofrimento_financeiro", "renegociacao", "fora_do_escopo"}


def _executar(acao: str, args: dict, tool_context: ToolContext) -> dict:
    cid = tool_context.state["cliente_id"]
    token = tool_context.state.get(CHAVE_CAPACIDADE + str(tool_context.function_call_id))
    try:
        return STORE.executar_autorizada(acao, cid, args, token)
    except (ValueError, KeyError) as e:
        return {"status": "bloqueado", "motivo": str(e)}


def parcelar_fatura(n_parcelas: int, tool_context: ToolContext) -> dict:
    """Parcela a fatura atual do cliente da sessão em ``n_parcelas`` (2 a 24).

    Chame quando o cliente escolher parcelar. O sistema mostra a ele o valor
    exato e pede aprovação antes de efetivar; você não precisa pedir "sim" por texto.
    """
    return _executar("parcelar_fatura", {"n_parcelas": n_parcelas}, tool_context)


def pagar_fatura(valor: float, tool_context: ToolContext) -> dict:
    """Paga a fatura (total ou parcial) do cliente da sessão com o saldo em conta.

    Chame quando o cliente escolher pagar. O sistema mostra o valor exato e pede
    aprovação antes de debitar; você não precisa pedir "sim" por texto.
    """
    return _executar("pagar_fatura", {"valor": valor}, tool_context)


def aplicar_cdb(valor: float, dias_permanencia: int = 30, tool_context: ToolContext | None = None) -> dict:
    """Aplica o valor indicado no CDB Itaú Liquidez Diária (100% CDI).

    Chame quando o cliente escolher aplicar capital ocioso. O sistema mostra o valor exato,
    rendimento líquido estimado e pede aprovação antes de efetivar.
    """
    assert tool_context is not None
    return _executar("aplicar_cdb", {"valor": valor, "dias_permanencia": dias_permanencia}, tool_context)


def resgatar_cdb(valor: float, tool_context: ToolContext | None = None) -> dict:
    """Resgata o valor indicado do CDB Liquidez Diária de volta para a conta corrente.

    Chame quando o cliente quiser resgatar recursos investidos. O sistema mostra o valor
    e pede aprovação antes de creditar.
    """
    assert tool_context is not None
    return _executar("resgatar_cdb", {"valor": valor}, tool_context)


def encaminhar_para_humano(motivo: str, tool_context: ToolContext) -> dict:
    """Registra a necessidade de apoio humano (renegociação, sofrimento financeiro, fora do escopo).

    Use quando o cliente demonstrar angústia, mencionar agiota/empréstimo informal,
    pedir algo fora da jornada da fatura, ou quando nem o mínimo couber no caixa.

    Args:
        motivo: uma categoria: "sofrimento_financeiro", "renegociacao" ou "fora_do_escopo".
    """
    # só a categoria é guardada: texto livre do modelo pode carregar dado sensível do cliente
    tool_context.state["escalonado"] = True
    tool_context.state["motivo_escalonamento"] = motivo if motivo in CATEGORIAS_ESCALONAMENTO else "outro"
    return {
        "status": "encaminhamento_simulado",
        "fila": "renegociacao_humana",
        "protocolo": f"HUM-{tool_context.invocation_id[:8]}",
        "mensagem": (
            "Protótipo: o encaminhamento é simulado e nenhum especialista foi acionado. Em produção, "
            "um especialista de renegociação assume esta conversa. Nenhuma ação foi executada. "
            "Para atendimento real agora, oriente os canais oficiais do banco."
        ),
    }
