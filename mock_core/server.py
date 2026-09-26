"""Servidor MCP (stdio) que expõe o core bancário mock.

Uso direto:   uv run python -m mock_core.server
Pelo agente:  COPILOTO_USE_MCP=1 uv run adk web

Mostra à banca a integração via protocolo aberto (MCP) e a separação entre
o agente e os sistemas transacionais.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from mock_core.store import STORE

mcp = MCPServer("core-bancario-mock")


@mcp.tool()
def consultar_perfil(cliente_id: str) -> dict:
    """Perfil do cliente com minimização de dados (sem CPF, endereço ou telefone)."""
    return STORE.get_perfil(cliente_id)


@mcp.tool()
def consultar_fatura(cliente_id: str) -> dict:
    """Fatura atual do cartão: total, mínimo, vencimento, limite e itens."""
    return STORE.get_fatura(cliente_id)


@mcp.tool()
def consultar_extrato(cliente_id: str, dias: int = 30) -> list[dict]:
    """Transações da conta nos últimos ``dias`` dias."""
    return STORE.get_extrato(cliente_id, dias)


@mcp.tool()
def consultar_fluxo_previsto(cliente_id: str) -> dict:
    """Saldo atual e entradas/saídas previstas (salário, contas recorrentes)."""
    return STORE.get_fluxo_previsto(cliente_id)


# Ações: só executam com a capacidade assinada pelo host depois da aprovação do
# cliente (``autorizacao``). O core confere a assinatura e recalcula a cotação.
# Pelo agente, ``cliente_id`` e ``autorizacao`` vêm da sessão, nunca do modelo.


@mcp.tool()
def parcelar_fatura(cliente_id: str, n_parcelas: int, autorizacao: str = "") -> dict:
    """Efetiva o parcelamento da fatura. Exige autorização emitida pelo host após a aprovação do cliente."""
    try:
        return STORE.executar_autorizada("parcelar_fatura", cliente_id, {"n_parcelas": n_parcelas}, autorizacao, canal="mcp")
    except (ValueError, KeyError) as e:
        return {"status": "bloqueado", "motivo": str(e)}


@mcp.tool()
def pagar_fatura(cliente_id: str, valor: float, autorizacao: str = "") -> dict:
    """Paga a fatura com saldo em conta. Exige autorização emitida pelo host após a aprovação do cliente."""
    try:
        return STORE.executar_autorizada("pagar_fatura", cliente_id, {"valor": valor}, autorizacao, canal="mcp")
    except (ValueError, KeyError) as e:
        return {"status": "bloqueado", "motivo": str(e)}


if __name__ == "__main__":
    mcp.run()
