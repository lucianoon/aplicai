"""Rotina proativa: mensagem de abertura em português correto e respeito à escolha do cliente."""

from proativo.gatilho import OPT_OUT, abertura


def test_abertura_simples_usa_valores_redondos_sem_estragar_a_pontuacao():
    t = abertura("Ana", 5, -1240.0, 375.1, "baixo")
    assert t.startswith("Oi, Ana. Sua fatura vence em 5 dias e, pelo que vejo,") and "R$ 1.240" in t and "R$ 375 " in t
    assert t.endswith(OPT_OUT)


def test_abertura_completa_usa_formato_brasileiro():
    t = abertura("Bia", 3, -2345.5, 1375.1, "alto")
    assert "R$ 2.345,50" in t and "R$ 1.375,10" in t and "1,375" not in t


def test_quem_nao_tem_caixa_nem_para_o_minimo_nao_recebe_promessa():
    t = abertura("Carla", 2, -2500.0, 175.28, "baixo", nada_cabe=True)
    assert "a menos" not in t and "especialista em renegociação" in t and t.endswith(OPT_OUT)


def test_reais_negativos():
    from copiloto_fatura.autorizacao import brl

    assert brl(-120) == "-R$ 120,00" and brl(1850) == "R$ 1.850,00"
