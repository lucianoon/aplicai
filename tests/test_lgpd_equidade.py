"""LGPD (minimização, dado sensível, direitos do titular, oposição) e equidade, sem LLM."""

import inspect
from types import SimpleNamespace

import pytest
from google.adk.models import LlmResponse
from google.genai import types

from copiloto_fatura import guardrails as g
from copiloto_fatura.tools import contexto as c
from copiloto_fatura.tools.simulador import simular_opcoes
from mock_core.store import STORE, Store
from proativo import gatilho


@pytest.fixture(autouse=True)
def isolado(tmp_path, monkeypatch):
    monkeypatch.setattr(STORE, "audit_path", tmp_path / "audit.jsonl")
    monkeypatch.setattr(STORE, "consent_path", tmp_path / "consentimentos.json")
    monkeypatch.setattr(g, "AUDIT_PATH", tmp_path / "guardrails.jsonl")
    STORE.reset()
    yield
    STORE.reset()


def _ctx(cid=None, **state):
    if cid:
        state["cliente_id"] = cid
    return SimpleNamespace(state=state)


# ---------- dados pessoais no texto ----------

@pytest.mark.parametrize("tipo,texto", [
    ("CPF", "meu cpf 12345678909"), ("RG", "meu RG é 12.345.678-9"), ("CNPJ", "CNPJ 12.345.678/0001-90"),
    ("PIX", "chave pix 123e4567-e89b-12d3-a456-426614174000"), ("TELEFONE", "liga no (11) 3333-4444"),
    ("CARTAO", "cartão 3782 822463 10005"), ("NASCIMENTO", "nasci em 12/03/1968"),
    ("ENDERECO", "moro na Rua das Flores, 123"), ("CONTA", "agência 1234"), ("CVV", "o código atrás é 123"),
    ("CEP", "CEP 01310-100"),
])
def test_redige_dados_pessoais_brasileiros(tipo, texto):
    assert tipo in g.redigir(texto)[1]


@pytest.mark.parametrize("texto", [
    "Sua fatura é de R$ 1.850,00 e vence em 5 dias.", "Pague R$ 549,00 agora e 6x de R$ 294,04.",
    "O saldo no vencimento é R$ 17.200,00.", "A conta fica negativa em R$ -120,00.",
    "Contrato PARC-C001-0001, protocolo HUM-1a2b3c4d.", "aluguel de R$ 950 no dia 10",
])
def test_nao_redige_valores_nem_comprovantes(texto):
    assert g.redigir(texto)[1] == {}


# ---------- saída discriminatória ----------

@pytest.mark.parametrize("texto", [
    "Pelos gastos na farmácia, parece que você está doente.",
    "Seus gastos na farmácia mostram que você tem algum problema de saúde.",
    "Como a senhora já tem mais idade, melhor a opção simples.", "Por ser negativada, você não merece o crédito.",
    "Mulheres costumam gastar mais com roupas.", "Você é pobre demais para parcelar em 3x.",
])
def test_bloqueia_inferencia_estereotipo_e_ofensa(texto):
    ctx = SimpleNamespace(state={}, agent_name="t")
    r = g.validar_saida_after_model(ctx, LlmResponse(content=types.Content(role="model", parts=[types.Part(text=texto)])))
    assert r is not None and r.content.parts[0].text == g.MSG_RESPEITO


@pytest.mark.parametrize("texto", [
    "Os gastos com farmácia foram R$ 240,00.", "Sua saúde financeira melhora se evitar o rotativo.",
    "Não faço suposições sobre a sua saúde.", "Como sempre, o salário cai no dia 9.",
    "A aposentadoria entra no dia 10.", "Você não é irresponsável: imprevistos acontecem.",
    "Para cuidar da sua saúde, procure um médico.",
    "Não sou médico e não consigo avaliar a sua saúde nem fazer qualquer diagnóstico pelos gastos.",
    "Se estiver preocupada com a sua saúde, vale conversar com um profissional.",
])
def test_nao_bloqueia_frases_legitimas(texto):
    assert not g.discriminatoria(texto)


# ---------- minimização e equidade ----------

def test_payload_nao_leva_negativacao_idade_nem_score():
    r = c.analisar_fatura(_ctx("C003"))  # Carla é negativada e usou o rotativo 5x
    texto = str(r).lower()
    assert "negativ" not in texto and "rotativo 5x" not in texto
    assert not {"idade", "score", "negativado", "historico_rotativo_12m"} & set(r)
    assert r["motivo_recomendacao"]


def test_contas_so_recebem_valores_financeiros():
    assert set(inspect.signature(simular_opcoes).parameters) == {
        "fatura", "saldo_projetado", "renda_mensal", "dias_ate_vencimento", "minimo_restante"}


def test_mudar_atributos_pessoais_nao_muda_nada_no_diagnostico():
    """Contrafactual: mesma situação financeira, outra pessoa -> mesmo resultado, byte a byte."""
    antes = c.analisar_fatura(_ctx("C001"))
    cliente = STORE._cliente("C001")
    cliente.update(nome="João Pereira", idade=72, negativado=True, historico_rotativo_12m=5, score=250,
                   letramento_financeiro="alto", acessibilidade="leitor_de_tela", objetivo_declarado=None)
    assert c.analisar_fatura(_ctx("C001")) == antes


# ---------- acessibilidade é dado sensível ----------

def test_acessibilidade_so_com_consentimento():
    state = {}
    r = c.iniciar_atendimento("C003", SimpleNamespace(state=state))
    assert "acessibilidade" not in r and r["oferecer_adaptacao"] is True
    assert c.registrar_preferencia("acessibilidade", "baixa_visao", SimpleNamespace(state=state))["status"] == "bloqueado"

    c.registrar_consentimento("acessibilidade", True, SimpleNamespace(state=state))
    r = c.iniciar_atendimento("C003", SimpleNamespace(state=state))
    assert r["acessibilidade"] == "baixa_visao" and "oferecer_adaptacao" not in r
    assert c.registrar_preferencia("acessibilidade", "baixa_visao", SimpleNamespace(state=state))["status"] == "ok"

    c.registrar_consentimento("acessibilidade", False, SimpleNamespace(state=state))
    assert "acessibilidade" not in state["user:preferencias:C003"]
    r = c.iniciar_atendimento("C003", SimpleNamespace(state=state))
    assert "acessibilidade" not in r and "oferecer_adaptacao" not in r  # já respondeu: não insiste


def test_oferta_de_adaptacao_e_igual_para_todos():
    """Quem não tem nenhuma necessidade registrada recebe a mesma oferta: nada é revelado."""
    assert c.iniciar_atendimento("C001", SimpleNamespace(state={}))["oferecer_adaptacao"] is True


# ---------- direitos do titular e oposição ----------

def test_meus_dados_e_apagar():
    state = {"cliente_id": "C001"}
    c.registrar_preferencia("canal", "whatsapp", SimpleNamespace(state=state))
    c.registrar_consentimento("avisos_proativos", True, SimpleNamespace(state=state))
    d = c.meus_dados(SimpleNamespace(state=state))
    assert d["preferencias_lembradas"] == {"canal": "whatsapp"} and "avisos_proativos" in d["consentimentos"]
    assert "negativação" in d["dados_que_nao_usamos"]
    r = c.apagar_meus_dados(SimpleNamespace(state=state))
    assert r["apagado"] == ["canal"] and state["user:preferencias:C001"] == {}
    assert "avisos_proativos" in STORE.consentimentos("C001")  # comprovação fica
    assert "preferencias_apagadas" in STORE.audit_path.read_text(encoding="utf-8")


def test_oposicao_aos_avisos_e_respeitada_pela_rotina_proativa():
    alvo = gatilho.avaliar("C017", 5)
    assert alvo is not None and alvo["mensagem_abertura"].endswith(gatilho.OPT_OUT) and alvo["motivo_prioridade"]
    c.registrar_consentimento("avisos_proativos", False, SimpleNamespace(state={"cliente_id": "C017"}))
    assert gatilho.avaliar("C017", 5) is None


def test_consentimento_persiste_entre_processos(tmp_path):
    STORE.registrar_consentimento("C017", "avisos_proativos", False)
    outro = Store(audit_path=tmp_path / "a2.jsonl", consent_path=STORE.consent_path)  # ex.: a rotina proativa
    assert outro.consentiu("C017", "avisos_proativos") is False


def test_ferramentas_de_lgpd_exigem_titular():
    for nome in ("registrar_consentimento", "meus_dados", "apagar_meus_dados", "registrar_preferencia"):
        r = g.politica_before_tool(SimpleNamespace(name=nome), {}, SimpleNamespace(state={}))
        assert r["status"] == "bloqueado"


def test_finalidade_desconhecida_e_recusada():
    r = c.registrar_consentimento("marketing", True, SimpleNamespace(state={"cliente_id": "C001"}))
    assert r["status"] == "bloqueado"
