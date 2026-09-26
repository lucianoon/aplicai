"""Capacidade assinada conferida pelo core (vale igual para tools diretas e MCP)."""

import json

import pytest

from copiloto_fatura import autorizacao as a
from mock_core.store import Store


@pytest.fixture()
def store(tmp_path):
    st = Store(audit_path=tmp_path / "audit.jsonl")
    yield st
    st.reset()


def _token(store, acao="parcelar_fatura", args=None, nonce="n1"):
    args = args or {"n_parcelas": 6}
    return a.assinar(a.cotar(store, acao, "C001", args), nonce)


def test_capacidade_valida_executa_e_replay_nao_duplica(store):
    t = _token(store)
    r1 = store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 6}, t)
    r2 = store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 6}, t)
    assert r1["status"] == "efetivado" and r2["replay"] is True and r2["contrato_id"] == r1["contrato_id"]
    assert len(store._contratos) == 1


def test_sem_capacidade_ou_forjada_nao_executa(store):
    for token in (None, "", "forjada", json.dumps({"payload": "{}", "assinatura": "0" * 64})):
        with pytest.raises(ValueError, match="autorização"):
            store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 6}, token)
    assert store.get_fatura("C001")["status"] == "aberta"


def test_payload_adulterado_invalida_assinatura(store):
    env = json.loads(_token(store))
    env["payload"] = env["payload"].replace('"n_parcelas": 6', '"n_parcelas": 2')
    with pytest.raises(ValueError):
        store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 2}, json.dumps(env))


def test_capacidade_nao_serve_para_outro_parametro_cliente_ou_acao(store):
    t = _token(store)
    for acao, cid, args in (("parcelar_fatura", "C001", {"n_parcelas": 12}),
                            ("parcelar_fatura", "C002", {"n_parcelas": 6}),
                            ("pagar_fatura", "C001", {"valor": 100.0})):
        with pytest.raises(ValueError):
            store.executar_autorizada(acao, cid, args, t)


def test_capacidade_expirada(store, monkeypatch):
    monkeypatch.setattr(a, "VALIDADE_CAPACIDADE_S", -1)
    with pytest.raises(ValueError, match="expirada"):
        store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 6}, _token(store))


def test_core_recota_e_recusa_se_valores_mudaram(store):
    t = _token(store)
    store._cliente("C001")["fatura"]["valor_total"] = 2000.0
    with pytest.raises(ValueError, match="mudaram"):
        store.executar_autorizada("parcelar_fatura", "C001", {"n_parcelas": 6}, t)


def test_pagamento_valida_valor_antes_de_pedir_aprovacao(store):
    with pytest.raises(ValueError, match="saldo"):
        a.cotar(store, "pagar_fatura", "C001", {"valor": 1000.0})  # fatura 1.850, saldo 610
    with pytest.raises(ValueError):
        a.cotar(store, "pagar_fatura", "C001", {"valor": -5})
    assert a.cotar(store, "pagar_fatura", "C001", {"valor": 549})["valor"] == 549.0
