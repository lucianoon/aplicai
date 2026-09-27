"""Tela da demo: a API que o front usa (sessão, /run, aprovação), em modo demo e sem internet."""

import importlib

import pytest
from fastapi.testclient import TestClient

from copiloto_fatura import guardrails as g
from mock_core.store import STORE


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    for attr, nome in (("audit_path", "audit.jsonl"), ("consent_path", "c.json"), ("lembretes_path", "l.json")):
        monkeypatch.setattr(STORE, attr, tmp_path / nome)
    monkeypatch.setattr(g, "AUDIT_PATH", tmp_path / "g.jsonl")
    monkeypatch.setenv("COPILOTO_MODEL", "demo")
    STORE.reset()
    from copiloto_fatura import agent

    importlib.reload(agent)  # o servidor carrega o agente já importado: garante o modelo demo
    from web import servidor

    importlib.reload(servidor)
    yield TestClient(servidor.app)
    monkeypatch.undo()
    importlib.reload(agent)
    STORE.reset()


def _run(c, sessao, parte):
    r = c.post("/run", json={"appName": "copiloto_fatura", "userId": "demo", "sessionId": sessao,
                             "newMessage": {"role": "user", "parts": [parte]}})
    assert r.status_code == 200, r.text
    return r.json()


def _textos(eventos):
    return " ".join(p["text"] for e in eventos if e["author"] != "user" for p in e["content"].get("parts", []) if p.get("text"))


def _aprovacao(eventos):
    return next(p["functionCall"] for e in eventos for p in e["content"].get("parts", [])
                if p.get("functionCall", {}).get("name") == "adk_request_confirmation")


def test_pagina_e_personas(cliente):
    assert "Copiloto da Fatura" in cliente.get("/").text
    dados = cliente.get("/demo/personas").json()
    assert dados["modelo"] == "demo" and [p["id"] for p in dados["personas"]] == ["C001", "C002", "C003", "C004"]
    ana = dados["personas"][0]
    assert "PARAR" in ana["abertura"] and dados["personas"][1]["abertura"] is None  # Bruno não precisa de aviso


def test_conversa_com_aprovacao_pela_api(cliente):
    s = cliente.post("/apps/copiloto_fatura/users/demo/sessions",
                     json={"state": {"cliente_id": "C001", "primeiro_nome": "Ana"}}).json()["id"]
    assert "R$ 549,00" in _textos(_run(cliente, s, {"text": "Quero ver as opções"}))
    pedido = _aprovacao(_run(cliente, s, {"text": "Quero parcelar em 6x"}))
    assert "6x de R$ 418,12" in pedido["args"]["toolConfirmation"]["hint"]
    fim = _run(cliente, s, {"functionResponse": {"id": pedido["id"], "name": "adk_request_confirmation",
                                                  "response": {"confirmed": True}}})
    assert "Pronto: parcelei" in _textos(fim) and STORE.get_fatura("C001")["status"] == "parcelada"


def test_reiniciar_volta_ao_estado_inicial(cliente):
    STORE.parcelar_fatura("C001", 6, "k")
    STORE.registrar_consentimento("C001", "avisos_proativos", False)
    assert cliente.post("/demo/reiniciar").json()["status"] == "ok"
    assert STORE.get_fatura("C001")["status"] == "aberta" and STORE.consentiu("C001", "avisos_proativos")


def test_api_contas_e_diagnostico(cliente):
    res = cliente.get("/api/contas")
    assert res.status_code == 200
    contas = res.json()["contas"]
    assert len(contas) == 4
    diego = next(c for c in contas if c["cliente_id"] == "C004")
    assert diego["segmento"] == "Itaú Personnalité"
    assert diego["regime"] == "oportunidade_liquidez"

    res_diego = cliente.get("/api/conta/C004")
    assert res_diego.status_code == 200
    dados = res_diego.json()
    assert dados["nome"] == "Diego Takahashi"
    assert dados["diagnostico"]["elegivel_investimento"] is True
    assert dados["diagnostico"]["smart_card"]["tipo"] == "OPORTUNIDADE_CDB"


def test_api_execucoes_bancarias(cliente):
    # Aplicação no CDB
    res_inv = cliente.post("/api/executar/investimento", json={"cliente_id": "C004", "valor": 5000.0, "dias_permanencia": 30})
    assert res_inv.status_code == 200
    body = res_inv.json()
    assert body["status"] == "sucesso"
    assert body["saldo_investido_novo"] == 5000.0
    assert "autenticacao_digital" in body

    # Resgate parcial
    res_resg = cliente.post("/api/executar/resgate", json={"cliente_id": "C004", "valor": 2000.0})
    assert res_resg.status_code == 200
    assert res_resg.json()["saldo_investido_novo"] == 3000.0

    # Parcelamento C001
    res_parc = cliente.post("/api/executar/parcelamento", json={"cliente_id": "C001", "n_parcelas": 3})
    assert res_parc.status_code == 200
    assert res_parc.json()["status"] == "sucesso"


def test_api_investimento_respeita_colchao(cliente):
    saldo = STORE.get_fluxo_previsto("C004")["saldo_atual"]
    res = cliente.post("/api/executar/investimento", json={"cliente_id": "C004", "valor": saldo})
    assert res.status_code == 400
    assert "capital livre" in res.json()["detail"]
    assert STORE.get_fluxo_previsto("C004")["saldo_atual"] == saldo
