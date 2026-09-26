import math

import pytest

from copiloto_fatura.tools import simulador as s


def test_pagamento_minimo_15_pct():
    assert s.pagamento_minimo(1000.0) == 150.0


def test_parcela_price_valor_conhecido():
    # 1000 em 12x a 1% a.m. -> 88,85 (tabela Price)
    assert math.isclose(s.parcela_price(1000, 12, 0.01), 88.8488, rel_tol=1e-4)


def test_cet_recupera_taxa_da_price():
    pmt = s.parcela_price(1000, 12, 0.02)
    assert math.isclose(s.cet_mensal(1000, pmt, 12), 0.02, abs_tol=1e-6)


def test_teto_legal_100_pct():
    assert s.aplicar_teto(1000, 5000) == 1000
    assert s.aplicar_teto(1000, 300) == 300


def test_projecao_de_caixa_respeita_horizonte():
    proj = s.projetar_caixa(
        100.0,
        [{"dia_offset": 3, "valor": 500.0, "descricao": "salário"}, {"dia_offset": 20, "valor": 999.0, "descricao": "fora"}],
        [{"dia_offset": 2, "valor": 50.0, "descricao": "luz"}],
        dias_horizonte=5,
    )
    assert proj["saldo_projetado"] == 550.0
    assert len(proj["detalhe_entradas"]) == 1


def test_rotativo_tem_a_maior_taxa_e_economia_e_positiva_no_mesmo_prazo():
    r = s.simular_opcoes(fatura=1850.0, saldo_projetado=610.0, renda_mensal=3200.0, dias_ate_vencimento=5)
    por_id = {o["id"]: o for o in r["opcoes"]}
    cet_rot = por_id["minimo_rotativo"]["cet_mensal_pct"]
    assert all(cet_rot >= o["cet_mensal_pct"] for o in r["opcoes"] if o["id"] != "minimo_rotativo")
    assert r["economia_vs_rotativo"] > 0
    # no mesmo prazo, qualquer opção (exceto o próprio rotativo) economiza
    assert all(o["economia_vs_rotativo_mesmo_prazo"] > 0 for o in r["opcoes"] if o["id"] != "minimo_rotativo")


def test_caminho_rotativo_custa_mais_que_parcelar_direto_no_mesmo_prazo():
    for n in (3, 6, 12):
        direto = s.parcela_price(1000.0, n, s.PARAMS.taxa_parcelamento_am) * n + s.iof(1000.0, n * 30)
        assert s.custo_caminho_rotativo(1000.0, n) > direto


def test_opcoes_ordenadas_e_uma_recomendada():
    r = s.simular_opcoes(1850.0, 610.0, 3200.0)
    custos = [o["custo_total"] for o in r["opcoes"]]
    assert custos == sorted(custos)
    assert sum(o["recomendada"] for o in r["opcoes"]) == 1
    assert r["opcoes"][0]["id"] == "pagar_total"
    assert r["opcoes"][0]["juros_e_encargos"] == 0.0


def test_recomendada_cabe_no_caixa_quando_possivel():
    r = s.simular_opcoes(1850.0, 610.0, 3200.0)
    rec = next(o for o in r["opcoes"] if o["recomendada"])
    assert rec["cabe_no_caixa"] is True
    assert rec["id"] != "pagar_total"
    assert r["requer_apoio_humano"] is False


def test_quando_cabe_tudo_recomenda_pagar_total():
    r = s.simular_opcoes(3100.0, 12000.0, 9800.0)
    assert r["recomendada_id"] == "pagar_total"
    assert r["economia_vs_rotativo"] > 0


def test_quando_nada_cabe_nao_recomenda_pagar_total_e_pede_humano():
    r = s.simular_opcoes(2380.0, -120.0, 2100.0, dias_ate_vencimento=2)
    assert r["recomendada_id"] not in ("pagar_total", "minimo_rotativo")
    assert r["requer_apoio_humano"] is True
    assert any("apoio humano" in a for a in r["alertas"])


def test_opcao_parcial_aparece_so_quando_faz_sentido():
    com = s.simular_opcoes(1850.0, 610.0, 3200.0)
    sem = s.simular_opcoes(1850.0, 100.0, 3200.0)  # abaixo do mínimo
    assert any(o["id"] == "parcial_mais_parcelamento" for o in com["opcoes"])
    assert not any(o["id"] == "parcial_mais_parcelamento" for o in sem["opcoes"])


@pytest.mark.parametrize("n", [3, 6, 12])
def test_parcelamento_custo_cresce_com_prazo(n):
    r = s.simular_opcoes(1000.0, 0.0, 3000.0)
    por_id = {o["id"]: o for o in r["opcoes"]}
    assert por_id[f"parcelar_fatura_{n}x"]["n_parcelas"] == n
    assert por_id["parcelar_fatura_3x"]["custo_total"] < por_id["parcelar_fatura_6x"]["custo_total"] < por_id["parcelar_fatura_12x"]["custo_total"]
