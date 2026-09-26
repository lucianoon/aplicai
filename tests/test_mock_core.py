import json
import subprocess
import sys
from pathlib import Path

import pytest

from mock_core.store import ClienteNaoEncontrado, Store

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture()
def store(tmp_path):
    st = Store(audit_path=tmp_path / "audit.jsonl")
    yield st
    st.reset()


def test_perfil_minimiza_dados(store):
    p = store.get_perfil("C001")
    assert p["primeiro_nome"] == "Ana"
    assert "cpf" not in {k.lower() for k in p} and "nome" not in p


def test_cliente_inexistente(store):
    with pytest.raises(ClienteNaoEncontrado):
        store.get_fatura("C999")


def test_fatura_minimo_e_limite(store):
    f = store.get_fatura("C001")
    assert f["valor_total"] == 1850.0 and f["valor_minimo"] == 277.5 and f["limite_disponivel"] == 2350.0


def test_parcelamento_idempotente_e_auditado(store, tmp_path):
    a = store.parcelar_fatura("C001", 6, "k1")
    b = store.parcelar_fatura("C001", 6, "k1")
    assert a["status"] == "efetivado" and a["n_parcelas"] == 6 and a["parcela"] > 0
    assert b["replay"] is True and b["contrato_id"] == a["contrato_id"]
    assert store.get_fatura("C001")["status"] == "parcelada"
    linhas = (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 1 and json.loads(linhas[0])["acao"] == "parcelar_fatura"


def test_parcelamento_nao_duplica_com_outra_chave(store):
    """Mesmo com outra chave (ex.: outro n), a fatura já parcelada não é parcelada de novo."""
    store.parcelar_fatura("C001", 6, "k1")
    r = store.parcelar_fatura("C001", 12, "k3")
    assert r["status"] == "recusado" and "parcelada" in r["motivo"]


def test_chave_de_idempotencia_e_de_negocio(store):
    a = store.chave_idempotencia("parcelar", "C001", 6)
    assert a == store.chave_idempotencia("parcelar", "C001", 6) == "parcelar:C001:2026-09-26:6"
    assert a != store.chave_idempotencia("parcelar", "C001", 12)


def test_cotacao_bate_com_o_contrato(store):
    cot = store.cotar_parcelamento("C001", 6)
    contrato = store.parcelar_fatura("C001", 6, "k4")
    assert (cot["parcela"], cot["custo_total"]) == (contrato["parcela"], contrato["custo_total"])


def test_parcelamento_fora_da_faixa(store):
    with pytest.raises(ValueError):
        store.parcelar_fatura("C001", 30, "k2")


def test_pagamento_recusa_sem_saldo_e_debita(store):
    r = store.pagar_fatura("C001", 5000.0, "p1")
    assert r["status"] == "recusado"
    ok = store.pagar_fatura("C001", 600.0, "p2")
    assert ok["status"] == "efetivado" and ok["novo_saldo"] == 10.0 and ok["restante_fatura"] == 1250.0


def test_servidor_mcp_lista_tools():
    """Sobe o servidor MCP por stdio e confere as tools expostas (integração real via protocolo)."""
    codigo = r"""
import asyncio, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mock_core.server"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print(sorted(t.name for t in tools.tools))
            res = await s.call_tool("parcelar_fatura", {"cliente_id": "C001", "n_parcelas": 6})
            print(res.content[0].text)
asyncio.run(main())
"""
    out = subprocess.run([sys.executable, "-c", codigo], cwd=RAIZ, capture_output=True, text=True, timeout=60,
                         env={**__import__("os").environ, "PYTHONUTF8": "1"})
    assert out.returncode == 0, out.stderr
    assert "parcelar_fatura" in out.stdout and "consultar_fatura" in out.stdout
    assert "bloqueado" in out.stdout
