"""Testes unitários determinísticos do Gestor de Caixa e Liquidez (sem LLM)."""

from datetime import date

import pytest
from google.adk.tools.tool_context import ToolContext

from copiloto_fatura.autorizacao import assinar, cotar, parametros, resumo, verificar
from gestor_caixa.esquemas import (
    CompromissoContratual,
    ProjecaoCaixa30d,
    RegimeCliente,
    TipoCompromisso,
)
from gestor_caixa.motor_projecao import MotorProjecaoCaixa
from gestor_caixa.portao_risco import PortaoRisco
from gestor_caixa.simulador_liquidez import SimuladorLiquidez
from mock_core.store import STORE


@pytest.fixture(autouse=True)
def _reset():
    STORE.reset()


def test_simulador_liquidez_calculos_exatos():
    sim = SimuladorLiquidez.simular_rendimento(10000.0, dias_corridos=30)
    assert sim["valor_aplicado"] == 10000.0
    assert sim["rendimento_bruto"] > 0
    assert sim["iof_valor"] == 0.0  # no 30º dia IOF é zero
    assert sim["ir_aliquota_pct"] == 22.5
    assert sim["ir_valor"] > 0
    assert sim["rendimento_liquido"] == round(sim["rendimento_bruto"] - sim["ir_valor"], 2)
    assert sim["valor_final_liquido"] == round(10000.0 + sim["rendimento_liquido"], 2)


def test_simulador_liquidez_com_iof_curto_prazo():
    # 5 dias corridos: IOF é 83%
    sim = SimuladorLiquidez.simular_rendimento(10000.0, dias_corridos=5)
    assert sim["iof_valor"] > 0
    assert sim["rendimento_liquido"] < sim["rendimento_bruto"]


def test_portao_risco_bloqueia_saldo_negativo():
    proj = ProjecaoCaixa30d(
        cliente_id="C_TEST",
        saldo_atual=-500.0,
        renda_mensal_esperada=5000.0,
        regime=RegimeCliente.DEFICIT_CRITICO,
    )
    autorizado, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    assert not autorizado
    assert "BLOQUEIO_SALDO_DEVEDOR" in motivo
    assert PortaoRisco.avaliar_necessidade_alivio_passivo(proj)


def test_portao_risco_bloqueia_deficit_previsto():
    proj = ProjecaoCaixa30d(
        cliente_id="C_TEST",
        saldo_atual=2000.0,
        renda_mensal_esperada=5000.0,
        total_compromissos_fixos=2500.0,
        saldo_livre_efetivo=0.0,
        regime=RegimeCliente.DEFICIT_PREVISTO,
    )
    autorizado, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    assert not autorizado
    assert "BLOQUEIO_LIQUIDEZ" in motivo


def test_portao_risco_autoriza_cliente_com_capital_ocioso():
    proj = ProjecaoCaixa30d(
        cliente_id="C_TEST",
        saldo_atual=25000.0,
        renda_mensal_esperada=10000.0,
        total_compromissos_fixos=5000.0,
        saldo_livre_efetivo=15000.0,
        regime=RegimeCliente.OPORTUNIDADE_LIQUIDEZ,
    )
    autorizado, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    assert autorizado
    assert "AUTORIZADO" in motivo


def test_motor_projecao_extrai_compromissos_reais():
    cliente_raw = {
        "cliente_id": "C_TEST",
        "saidas_previstas": [
            {"descricao": "financiamento habitacional", "valor": 2845.0, "dia_offset": 8},
            {"descricao": "mensalidade escolar", "valor": 1050.0, "dia_offset": 10},
        ],
        "fatura": {"status": "aberta", "valor_total": 2000.0, "pago": 0.0, "dias_ate_vencimento": 15},
    }
    proj = MotorProjecaoCaixa.projetar("C_TEST", 30000.0, 12000.0, cliente_raw, hoje=date(2026, 9, 21))
    assert len(proj.compromissos_identificados) == 3
    assert proj.total_compromissos_fixos == 5895.0
    assert proj.saldo_livre_efetivo > 20000.0
    assert proj.regime == RegimeCliente.OPORTUNIDADE_LIQUIDEZ


def test_autorizacao_e_execucao_aplicar_cdb():
    cliente_id = "C001"
    perfil = STORE.get_perfil(cliente_id)
    # Garante saldo suficiente em C001 para o teste
    STORE._cliente(cliente_id)["saldo_conta"] = 15000.0

    args = {"valor": 5000.0, "dias_permanencia": 30}
    q = cotar(STORE, "aplicar_cdb", cliente_id, args)
    assert q["acao"] == "aplicar_cdb"
    assert q["valor"] == 5000.0
    assert q["rendimento_liquido"] > 0

    texto_resumo = resumo(q)
    assert "CDB Itaú Liquidez Diária" in texto_resumo

    token = assinar(q, "nonce-teste-123")
    recibo = STORE.executar_autorizada("aplicar_cdb", cliente_id, args, token)

    assert recibo["status"] == "efetivado"
    assert recibo["valor_aplicado"] == 5000.0
    assert recibo["novo_saldo_conta"] == 10000.0
    assert recibo["saldo_total_investido"] == 5000.0

    # Teste de resgate subsequente
    args_resg = {"valor": 2000.0}
    q_resg = cotar(STORE, "resgatar_cdb", cliente_id, args_resg)
    token_resg = assinar(q_resg, "nonce-teste-456")
    recibo_resg = STORE.executar_autorizada("resgatar_cdb", cliente_id, args_resg, token_resg)

    assert recibo_resg["status"] == "efetivado"
    assert recibo_resg["valor_resgatado"] == 2000.0
    assert recibo_resg["novo_saldo_conta"] == 12000.0
    assert recibo_resg["saldo_total_investido"] == 3000.0


def test_tools_contexto_analisar_caixa_e_liquidez():
    from types import SimpleNamespace
    from copiloto_fatura.tools.contexto import analisar_caixa_e_liquidez

    ctx = SimpleNamespace(state={"cliente_id": "C001"})
    diag = analisar_caixa_e_liquidez(ctx)

    assert diag["status"] == "ok"
    assert diag["cliente_id"] == "C001"
    assert "saldo_atual" in diag
    assert "colchao_minimo_obrigatorio" in diag
    assert "regime" in diag


def test_aplicar_cdb_bloqueado_pelo_portao_no_caminho_de_execucao():
    # cliente com saldo, mas em déficit crítico: nem cotação nem execução passam
    cliente_id = "C001"
    c = STORE._cliente(cliente_id)
    c["saldo_conta"] = 15000.0
    c["negativado"] = True

    args = {"valor": 1000.0, "dias_permanencia": 30}
    with pytest.raises(ValueError, match="BLOQUEIO_SUITABILITY"):
        cotar(STORE, "aplicar_cdb", cliente_id, args)

    # capacidade forjada com a cotação de antes: o core recalcula e recusa
    token = assinar({"acao": "aplicar_cdb", "cliente_id": cliente_id, **args}, "nonce-forjado")
    with pytest.raises(ValueError):
        STORE.executar_autorizada("aplicar_cdb", cliente_id, args, token)
    assert c["saldo_conta"] == 15000.0


def test_aplicar_cdb_nao_invade_o_colchao():
    cliente_id = "C004"
    saldo = STORE.get_fluxo_previsto(cliente_id)["saldo_atual"]
    renda = STORE.get_perfil(cliente_id)["renda_mensal"]
    proj = MotorProjecaoCaixa.projetar(cliente_id, saldo, renda, STORE._cliente(cliente_id))
    assert proj.colchao_minimo_obrigatorio > 0

    with pytest.raises(ValueError, match="capital livre"):
        cotar(STORE, "aplicar_cdb", cliente_id, {"valor": saldo})

    # o capital livre inteiro pode ser aplicado
    q = cotar(STORE, "aplicar_cdb", cliente_id, {"valor": proj.saldo_livre_efetivo})
    assert q["valor"] == proj.saldo_livre_efetivo


def test_motor_usa_prazos_dos_dados_e_janela_de_30_dias():
    cliente_raw = {
        "saidas_previstas": [
            {"descricao": "aluguel", "valor": 950.0, "dia_offset": 10},
            {"descricao": "seguro anual", "valor": 4000.0, "dia_offset": 45},  # fora da janela
        ],
        "fatura": {"status": "aberta", "valor_total": 1850.0, "pago": 350.0, "dias_ate_vencimento": 5},
    }
    proj = MotorProjecaoCaixa.projetar("C_TEST", 10000.0, 4000.0, cliente_raw, hoje=date(2026, 9, 28))
    por_tipo = {c.tipo: c for c in proj.compromissos_identificados}
    assert set(por_tipo) == {TipoCompromisso.ALUGUEL, TipoCompromisso.FATURA_CARTAO}
    assert por_tipo[TipoCompromisso.ALUGUEL].dias_ate_vencimento == 10
    assert por_tipo[TipoCompromisso.ALUGUEL].dia_vencimento == 8  # 28/09 + 10 dias = 08/10
    assert por_tipo[TipoCompromisso.FATURA_CARTAO].valor_estimado == 1500.0
    assert proj.total_compromissos_fixos == 2450.0
    assert proj.colchao_minimo_obrigatorio == 2450.0 + 600.0


def test_motor_debito_de_referencia_e_o_maior_da_janela():
    cliente_raw = {
        "saidas_previstas": [
            {"descricao": "energia", "valor": 180.0, "dia_offset": 1},
            {"descricao": "financiamento", "valor": 2845.0, "dia_offset": 8},
            {"descricao": "condominio", "valor": 900.0, "dia_offset": 3},
        ],
    }
    proj = MotorProjecaoCaixa.projetar("C_TEST", 20000.0, 9000.0, cliente_raw, hoje=date(2026, 9, 21))
    assert proj.valor_proximo_grande_debito == 2845.0
    assert proj.dias_ate_proximo_debito == 8
    assert proj.data_proximo_grande_debito.startswith("financiamento")


def test_regime_neutro_nao_e_elegivel():
    # capital livre positivo, mas abaixo do mínimo de oportunidade: regime e portão concordam
    cliente_raw = {"saidas_previstas": [{"descricao": "aluguel", "valor": 1000.0, "dia_offset": 5}]}
    proj = MotorProjecaoCaixa.projetar("C_TEST", 6000.0, 22000.0, cliente_raw, hoje=date(2026, 9, 21))
    assert proj.regime == RegimeCliente.NEUTRO
    assert 1000.0 <= proj.saldo_livre_efetivo < 2000.0
    autorizado, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    assert not autorizado and "BLOQUEIO_COLCHAO" in motivo
