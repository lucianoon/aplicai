"""Simulador financeiro determinístico da fatura do cartão.

Toda a matemática fica aqui, em código, e nunca no LLM. O agente chama
``simular_opcoes`` e apenas explica o resultado em linguagem simples.

Parâmetros default são aproximações de mercado (set/2026). Ajuste com os
dados públicos do case (BCB, Febraban) e documente a fonte no entregável.

Regras modeladas:
- pagamento mínimo: 15% da fatura;
- rotativo: no máximo 30 dias; depois o banco deve oferecer parcelamento;
- teto legal: juros + encargos não podem superar 100% da dívida original
  (Lei 14.690/2023);
- IOF crédito PF: 0,38% fixo + 0,0082% ao dia.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Parametros:
    taxa_rotativo_am: float = 0.14
    taxa_parcelamento_am: float = 0.09
    taxa_credito_pessoal_am: float = 0.045
    pct_minimo: float = 0.15
    iof_fixo: float = 0.0038
    iof_diario: float = 0.000082
    teto_encargos: float = 1.0
    dias_rotativo: int = 30
    parcelas_pos_rotativo: int = 6


PARAMS = Parametros()
NAO_RECOMENDAVEIS = {"minimo_rotativo", "credito_pessoal_12x"}
# crédito responsável: acima disso de comprometimento da renda, o crédito pessoal não é oferecido
LIMITE_RENDA_CREDITO_PCT = 30.0


def arred(valor: float) -> float:
    return round(valor + 1e-9, 2)


def pagamento_minimo(fatura: float, p: Parametros = PARAMS) -> float:
    return arred(fatura * p.pct_minimo)


def iof(valor: float, dias: int, p: Parametros = PARAMS) -> float:
    return arred(valor * (p.iof_fixo + p.iof_diario * dias))


def juros_compostos(valor: float, taxa_am: float, dias: int) -> float:
    return valor * ((1 + taxa_am) ** (dias / 30) - 1)


def parcela_price(valor: float, n: int, taxa_am: float) -> float:
    if n <= 0:
        raise ValueError("n deve ser >= 1")
    if taxa_am == 0:
        return valor / n
    return valor * taxa_am / (1 - (1 + taxa_am) ** (-n))


def cet_mensal(valor_liberado: float, parcela: float, n: int, tol: float = 1e-8) -> float:
    """Taxa interna de retorno mensal (CET) por bisseção."""

    def vpl(i: float) -> float:
        if i == 0:
            return parcela * n - valor_liberado
        return parcela * (1 - (1 + i) ** (-n)) / i - valor_liberado

    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if vpl(mid) > 0:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def cet_anual(cet_am: float) -> float:
    return (1 + cet_am) ** 12 - 1


def aplicar_teto(divida_original: float, encargos: float, p: Parametros = PARAMS) -> float:
    return min(encargos, divida_original * p.teto_encargos)


def projetar_caixa(
    saldo_atual: float,
    entradas: list[dict],
    saidas: list[dict],
    dias_horizonte: int,
) -> dict:
    """Projeta o saldo em conta até ``dias_horizonte`` dias à frente.

    ``entradas``/``saidas`` são listas de ``{"dia_offset", "valor", "descricao"}``.
    """
    ent = [e for e in entradas if 0 <= e["dia_offset"] <= dias_horizonte]
    sai = [s for s in saidas if 0 <= s["dia_offset"] <= dias_horizonte]
    total_ent = sum(e["valor"] for e in ent)
    total_sai = sum(s["valor"] for s in sai)
    return {
        "saldo_atual": arred(saldo_atual),
        "entradas_previstas": arred(total_ent),
        "saidas_previstas": arred(total_sai),
        "saldo_projetado": arred(saldo_atual + total_ent - total_sai),
        "horizonte_dias": dias_horizonte,
        "detalhe_entradas": ent,
        "detalhe_saidas": sai,
    }


def custo_caminho_rotativo(
    fatura: float, n_parcelas_depois: int, p: Parametros = PARAMS, minimo_restante: float | None = None
) -> float:
    """Custo total de: pagar o mínimo, ficar 30 dias no rotativo e parcelar o resto em n.

    É a comparação justa ("mesmo prazo") para a economia de qualquer opção.
    ``minimo_restante`` informa quanto ainda falta pagar do mínimo neste ciclo.
    """
    minimo = pagamento_minimo(fatura, p) if minimo_restante is None else minimo_restante
    resto = fatura - minimo
    saldo_pos = resto + juros_compostos(resto, p.taxa_rotativo_am, p.dias_rotativo) + iof(resto, p.dias_rotativo, p)
    pmt = parcela_price(saldo_pos, n_parcelas_depois, p.taxa_parcelamento_am)
    encargos = aplicar_teto(fatura, minimo + pmt * n_parcelas_depois - fatura, p)
    return arred(fatura + encargos)


def _opcao(
    id_: str,
    nome: str,
    descricao: str,
    fatura: float,
    desembolso_agora: float,
    custo_total: float,
    parcela: float | None,
    n_parcelas: int | None,
    saldo_projetado: float,
    renda_mensal: float,
    cet_am: float | None,
    alerta: str | None = None,
) -> dict:
    encargos = aplicar_teto(fatura, max(custo_total - fatura, 0.0))
    custo_total = fatura + encargos
    compromisso = (parcela or desembolso_agora) / renda_mensal if renda_mensal else 0.0
    return {
        "id": id_,
        "nome": nome,
        "descricao": descricao,
        "desembolso_agora": arred(desembolso_agora),
        "custo_total": arred(custo_total),
        "juros_e_encargos": arred(encargos),
        "parcela": arred(parcela) if parcela is not None else None,
        "n_parcelas": n_parcelas,
        "cet_mensal_pct": arred(cet_am * 100) if cet_am is not None else 0.0,
        "cet_anual_pct": arred(cet_anual(cet_am) * 100) if cet_am is not None else 0.0,
        "cabe_no_caixa": desembolso_agora <= max(saldo_projetado, 0.0),
        "comprometimento_renda_pct": arred(compromisso * 100),
        "alerta": alerta,
        "recomendada": False,
    }


def simular_opcoes(
    fatura: float,
    saldo_projetado: float,
    renda_mensal: float,
    dias_ate_vencimento: int = 5,
    minimo_restante: float | None = None,
) -> dict:
    """Simula, em reais, as alternativas para pagar a fatura do cartão.

    Use SEMPRE esta ferramenta antes de falar de custo, juros, parcelas ou CET.
    Nunca calcule esses valores de cabeça.

    Args:
        fatura: valor total da fatura atual em reais.
        saldo_projetado: saldo em conta previsto na data do vencimento
            (use a ferramenta de projeção de caixa para obtê-lo).
        renda_mensal: renda mensal líquida do cliente em reais.
        dias_ate_vencimento: dias até o vencimento da fatura.
        minimo_restante: parte do mínimo ainda devida, se houve pagamento parcial.

    Returns:
        Dicionário com a lista ``opcoes`` ordenada da mais barata para a mais
        cara, a opção ``recomendada`` (mais barata que cabe no caixa), a
        ``economia_vs_rotativo`` em reais e ``alertas`` para explicar ao cliente.
    """
    p = PARAMS
    fatura = float(fatura)
    minimo = pagamento_minimo(fatura, p) if minimo_restante is None else minimo_restante
    opcoes: list[dict] = []

    # A) pagar o total
    opcoes.append(
        _opcao(
            "pagar_total",
            "Pagar a fatura inteira",
            "Quita a fatura no vencimento. Custo zero de juros.",
            fatura, fatura, fatura, None, None, saldo_projetado, renda_mensal, None,
        )
    )

    # B) pagar o mínimo e cair no rotativo (30 dias) + parcelamento obrigatório do resto
    resto = fatura - minimo
    juros_rot = juros_compostos(resto, p.taxa_rotativo_am, p.dias_rotativo)
    iof_rot = iof(resto, p.dias_rotativo, p)
    saldo_pos_rot = resto + juros_rot + iof_rot
    pmt_pos = parcela_price(saldo_pos_rot, p.parcelas_pos_rotativo, p.taxa_parcelamento_am)
    custo_b = minimo + pmt_pos * p.parcelas_pos_rotativo
    opcoes.append(
        _opcao(
            "minimo_rotativo",
            "Pagar só o mínimo (rotativo)",
            f"Paga {minimo:.2f} agora; o resto fica 30 dias no rotativo e depois é parcelado em "
            f"{p.parcelas_pos_rotativo}x. É a saída mais cara.",
            fatura, minimo, custo_b, pmt_pos, p.parcelas_pos_rotativo, saldo_projetado,
            renda_mensal, cet_mensal(resto, pmt_pos, p.parcelas_pos_rotativo),
            alerta="Rotativo é a modalidade mais cara do mercado. Evite.",
        )
    )

    # C) parcelar a fatura (3, 6, 12)
    for n in (3, 6, 12):
        pmt = parcela_price(fatura, n, p.taxa_parcelamento_am)
        total = pmt * n + iof(fatura, n * 30, p)
        pmt_total = total / n
        opcoes.append(
            _opcao(
                f"parcelar_fatura_{n}x",
                f"Parcelar a fatura em {n}x",
                f"Divide a fatura em {n} parcelas fixas de {pmt_total:.2f}.",
                fatura, pmt_total, total, pmt_total, n, saldo_projetado, renda_mensal,
                cet_mensal(fatura, pmt_total, n),
            )
        )

    # D) crédito pessoal para quitar a fatura (12x), sujeito a análise
    n_cp = 12
    pmt_cp = parcela_price(fatura, n_cp, p.taxa_credito_pessoal_am)
    total_cp = pmt_cp * n_cp + iof(fatura, n_cp * 30, p)
    pmt_cp_total = total_cp / n_cp
    pct_renda_cp = pmt_cp_total / renda_mensal * 100 if renda_mensal else 0.0
    opcoes.append(
        _opcao(
            "credito_pessoal_12x",
            "Crédito pessoal para quitar a fatura (12x)",
            "Contrata um empréstimo mais barato e paga a fatura inteira. Sujeito a análise de crédito.",
            fatura, pmt_cp_total, total_cp, pmt_cp_total, n_cp, saldo_projetado, renda_mensal,
            cet_mensal(fatura, pmt_cp_total, n_cp),
            # crédito responsável (Lei 14.181/2021): informação clara de que é uma dívida nova
            alerta=(f"É uma dívida nova de {n_cp} meses, que compromete {pct_renda_cp:.0f}% da renda por mês. "
                    "Depende de análise de crédito: nunca prometa aprovação ao cliente."),
        )
    )

    # E) pagar parte agora (90% do que cabe) e parcelar o resto
    if minimo < saldo_projetado < fatura:
        parcial = arred(saldo_projetado * 0.9)
        resto_e = fatura - parcial
        n_e = 6
        pmt_e = parcela_price(resto_e, n_e, p.taxa_parcelamento_am)
        total_e = parcial + pmt_e * n_e + iof(resto_e, n_e * 30, p)
        opcoes.append(
            _opcao(
                "parcial_mais_parcelamento",
                f"Pagar {parcial:.2f} agora e parcelar o resto em {n_e}x",
                "Usa o que cabe no caixa, mantém uma reserva e parcela só a diferença.",
                fatura, parcial, total_e, (total_e - parcial) / n_e, n_e, saldo_projetado,
                renda_mensal, cet_mensal(resto_e, (total_e - parcial) / n_e, n_e),
            )
        )

    opcoes.sort(key=lambda o: o["custo_total"])
    requer_apoio_humano = False
    # nunca recomendar o rotativo (o mais caro no mesmo prazo) nem o crédito pessoal
    # (dívida nova que depende de aprovação): eles podem ser mostrados, não indicados
    recomendada = next((o for o in opcoes if o["cabe_no_caixa"] and o["id"] not in NAO_RECOMENDAVEIS), None)
    if recomendada is None:
        # nada cabe: menor parcela entre os parcelamentos garantidos (sem rotativo e sem
        # crédito sujeito a análise), e sinaliza apoio humano
        candidatas = [o for o in opcoes if o["id"].startswith("parcelar_fatura")]
        recomendada = min(candidatas, key=lambda o: (o["desembolso_agora"], o["custo_total"]))
        requer_apoio_humano = True
    recomendada["recomendada"] = True
    # economia justa: contra o caminho "mínimo + rotativo 30d + parcelar no MESMO prazo"
    n_equiv = recomendada["n_parcelas"] or p.parcelas_pos_rotativo
    custo_rot = custo_caminho_rotativo(fatura, n_equiv, p, minimo_restante=minimo)
    for o in opcoes:
        o["economia_vs_rotativo_mesmo_prazo"] = arred(
            custo_caminho_rotativo(fatura, o["n_parcelas"] or p.parcelas_pos_rotativo, p,
                                   minimo_restante=minimo) - o["custo_total"]
        )

    if minimo_restante is None:
        aviso_minimo = f"O pagamento mínimo é R$ {minimo:.2f} (15% da fatura)."
    elif minimo:
        aviso_minimo = f"Faltam R$ {minimo:.2f} para completar o pagamento mínimo desta fatura."
    else:
        aviso_minimo = "O pagamento mínimo já foi cumprido; o saldo em aberto pode entrar no rotativo."
    alertas = [
        aviso_minimo,
        "O rotativo tem a maior taxa (CET) de todas as opções: no mesmo prazo, sempre custa mais que parcelar.",
    ]
    if saldo_projetado < minimo:
        alertas.append(
            "O saldo projetado não cobre nem o mínimo. Sinal de aperto: considerar renegociação "
            "e apoio humano."
        )
    if requer_apoio_humano:
        alertas.append(
            "Nenhuma opção cabe no caixa projetado. A recomendada é a de menor parcela; "
            "acione encaminhar_para_humano para renegociação."
        )
    if recomendada["comprometimento_renda_pct"] > 30:
        alertas.append("A parcela recomendada compromete mais de 30% da renda. Avaliar prazo maior.")

    return {
        "fatura": arred(fatura),
        "pagamento_minimo": minimo,
        "saldo_projetado": arred(saldo_projetado),
        "dias_ate_vencimento": dias_ate_vencimento,
        "opcoes": opcoes,
        "recomendada_id": recomendada["id"],
        "requer_apoio_humano": requer_apoio_humano,
        "economia_vs_rotativo": arred(custo_rot - recomendada["custo_total"]),
        "alertas": alertas,
        "parametros": {
            "taxa_rotativo_am_pct": p.taxa_rotativo_am * 100,
            "taxa_parcelamento_am_pct": p.taxa_parcelamento_am * 100,
            "taxa_credito_pessoal_am_pct": p.taxa_credito_pessoal_am * 100,
        },
    }
