"""Tools de contexto: identificação, diagnóstico da fatura, memória e direitos do titular.

Leem o mock do core bancário (``mock_core.store``). Em produção, cada leitura
vira um adapter para o sistema real, mantendo assinatura e contrato.

O cliente vem sempre do estado da sessão (``cliente_id``), nunca de um argumento
preenchido pelo modelo: isso fecha o acesso a dados de terceiros e economiza
tokens. ``iniciar_atendimento`` simula o login; em produção o ``cliente_id``
chega autenticado no ``state`` da sessão e a tool só carrega o contexto.

LGPD e equidade (ver docs/rai.md):
- minimização: o modelo recebe só o que precisa para explicar a fatura. Negativação,
  histórico de rotativo, idade e score ficam no core e nunca entram no payload;
- acessibilidade é dado de saúde (dado sensível): só vai ao modelo e à memória com
  consentimento explícito registrado no core;
- as opções e a recomendação dependem só de valores financeiros, iguais para todos.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from google.adk.tools.tool_context import ToolContext

from copiloto_fatura.autorizacao import brl
from copiloto_fatura.tools.simulador import (
    LIMITE_RENDA_CREDITO_PCT,
    PARAMS,
    custo_caminho_rotativo,
    projetar_caixa,
    simular_opcoes,
)
from mock_core.store import FINALIDADES, STORE, ClienteNaoEncontrado

CHAVE_PREFS = "user:preferencias"
N_OPCOES_APRESENTAR = 3
# memória só com chaves e valores conhecidos: nada de texto livre (saúde, família, religião...)
PREFERENCIAS_PERMITIDAS = {
    "canal": {"app", "whatsapp", "voz"},
    "linguagem": {"simples", "tecnica"},
    "lembrete_dias_antes": {"1", "3", "5"},
    "opcao_preferida": {"parcelar", "pagar_total", "pagar_parcial", "investir_cdb"},
    "acessibilidade": {"baixa_visao", "leitor_de_tela", "baixa_alfabetizacao"},
}
# preferências que são dado sensível: exigem o consentimento da finalidade
PREFERENCIAS_SENSIVEIS = {"acessibilidade": "acessibilidade"}
DADOS_USADOS = [
    "primeiro nome", "familiaridade com finanças", "canal preferido", "objetivo declarado",
    "fatura e itens por categoria", "saldo e entradas e saídas previstas", "renda mensal",
]


def _chave_prefs(cliente_id: str) -> str:
    # escopo user: é por usuário do canal; no adk web todas as sessões usam o mesmo user_id
    return f"{CHAVE_PREFS}:{cliente_id}"


def iniciar_atendimento(cliente_id: str, tool_context: ToolContext) -> dict:
    """Identifica o cliente da sessão e carrega o perfil e as preferências lembradas.

    Chame UMA vez, assim que souber o identificador do cliente (ex.: "C001").
    O cliente fica fixo na sessão: pedidos sobre qualquer outro cliente são
    bloqueados (LGPD). Se vier ``oferecer_adaptacao``, ofereça adaptar as respostas.

    Args:
        cliente_id: identificador do cliente, no formato C###.
    """
    cliente_id = cliente_id.strip().upper()
    atual = tool_context.state.get("cliente_id")
    if atual and atual != cliente_id:
        return {"status": "bloqueado", "motivo": "LGPD: esta sessão já pertence a outro titular."}
    try:
        perfil = STORE.get_perfil(cliente_id)
    except ClienteNaoEncontrado:
        return {"status": "erro", "motivo": f"cliente {cliente_id} não encontrado"}
    tool_context.state["cliente_id"] = cliente_id
    tool_context.state["primeiro_nome"] = perfil["primeiro_nome"]
    r = {
        "status": "ok",
        "primeiro_nome": perfil["primeiro_nome"],
        "letramento_financeiro": perfil["letramento_financeiro"],
        "canal_preferido": perfil["canal_preferido"],
        "objetivo_declarado": perfil["objetivo_declarado"],
        "preferencias_lembradas": tool_context.state.get(_chave_prefs(cliente_id), {}),
    }
    consentimentos = STORE.consentimentos(cliente_id)
    if STORE.consentiu(cliente_id, "acessibilidade"):
        r["acessibilidade"] = perfil["acessibilidade"]
    elif "acessibilidade" not in consentimentos:
        # oferta igual para todos: não revela se o banco tem alguma informação sobre a pessoa
        r["oferecer_adaptacao"] = True
    return r


def _compacta(o: dict) -> dict:
    """Só o que o modelo precisa para explicar a opção (cada campo custa tokens em todo turno)."""
    c = {
        "id": o["id"],
        "nome": o["nome"],
        "parcela": o["parcela"],
        "n_parcelas": o["n_parcelas"],
        "custo_total": o["custo_total"],
        "juros_e_encargos": o["juros_e_encargos"],
        "cet_mensal_pct": o["cet_mensal_pct"],
        "cabe_no_caixa": o["cabe_no_caixa"],
        "economia_vs_rotativo": o["economia_vs_rotativo_mesmo_prazo"],
    }
    if o["parcela"] is None or o["desembolso_agora"] != o["parcela"]:
        c["pagar_agora"] = o["desembolso_agora"]
    if o["alerta"]:
        c["alerta"] = o["alerta"]
    return c


def _escolher_apresentacao(sim: dict) -> list[dict]:
    """Recomendada primeiro, depois as mais baratas que cabem (o rotativo nunca é sugerido).

    Se nada cabe no caixa, só parcelamentos garantidos, da menor parcela para a maior.
    """
    opcoes = sim["opcoes"]
    rec = next(o for o in opcoes if o["id"] == sim["recomendada_id"])
    if sim["requer_apoio_humano"]:
        resto = sorted(
            (o for o in opcoes if o is not rec and o["id"].startswith("parcelar_fatura")),
            key=lambda o: o["desembolso_agora"],
        )
    else:
        resto = [o for o in opcoes if o is not rec and o["id"] != "minimo_rotativo" and o["cabe_no_caixa"]
                 and not _credito_irresponsavel(o)]
    return [rec, *resto[: N_OPCOES_APRESENTAR - 1]]


def _credito_irresponsavel(o: dict) -> bool:
    """Crédito responsável (Lei 14.181/2021): dívida nova só se couber na renda, pela capacidade de pagamento."""
    return o["id"] == "credito_pessoal_12x" and o["comprometimento_renda_pct"] > LIMITE_RENDA_CREDITO_PCT


def _motivo(sim: dict, saldo_venc: float) -> str:
    """Explicação da recomendação gerada pelo código (LGPD art. 20: decisão explicável)."""
    if sim["requer_apoio_humano"]:
        return ("Nenhuma opção cabe no saldo previsto para o vencimento; esta é a de menor parcela, "
                "e o melhor caminho é renegociar com apoio humano.")
    if sim["recomendada_id"] == "pagar_total":
        return "Cabe no saldo previsto para o vencimento e não tem juros."
    return (f"É a opção de menor custo total entre as que cabem no saldo previsto para o "
            f"vencimento ({brl(saldo_venc)}).")


def analisar_fatura(tool_context: ToolContext) -> dict:
    """Diagnóstico da fatura do cliente da sessão, com as opções de pagamento já simuladas em reais.

    Traz fatura, caixa projetado no vencimento, maiores gastos, alertas de caixa,
    as opções a apresentar (a recomendada primeiro, com o motivo), o que acontece se
    o cliente pagar só o mínimo (rotativo) e as demais opções. Todos os números vêm
    de código determinístico: use exatamente estes valores, nunca calcule de cabeça.
    """
    cid = tool_context.state["cliente_id"]
    fatura = STORE.get_fatura(cid)
    em_aberto = fatura["valor_em_aberto"]
    pago = round(fatura["valor_total"] - em_aberto, 2)
    minimo_restante = round(max(fatura["valor_minimo"] - pago, 0.0), 2)
    resumo_fatura = {
        "total": fatura["valor_total"],
        "em_aberto": em_aberto,
        "minimo": fatura["valor_minimo"],
        "minimo_restante": minimo_restante,
        "vence_em_dias": fatura["dias_ate_vencimento"],
        "status": fatura["status"],
    }
    if fatura["status"] not in ("aberta", "paga_parcialmente") or em_aberto <= 0:
        return {
            "fatura": resumo_fatura,
            "mensagem": "A fatura já foi paga ou parcelada; não há novas opções de pagamento para este ciclo.",
            "recomendada_id": None,
            "opcoes_para_apresentar": [],
            "outras_opcoes": [],
            "se_nao_fizer_nada": None,
        }

    renda = STORE.get_perfil(cid)["renda_mensal"]
    fluxo = STORE.get_fluxo_previsto(cid)
    dias = fatura["dias_ate_vencimento"]
    proj = projetar_caixa(fluxo["saldo_atual"], fluxo["entradas"], fluxo["saidas"], dias)
    saldo_venc = proj["saldo_projetado"]
    gap = round(saldo_venc - em_aberto, 2)
    # só valores financeiros entram na conta: nenhum atributo pessoal muda opções ou recomendação
    sim = simular_opcoes(em_aberto, saldo_venc, renda, dias,
                        minimo_restante=minimo_restante if pago else None)

    alertas_caixa = []
    if gap < 0:
        alertas_caixa.append("o saldo no vencimento não cobre a fatura inteira")
    if minimo_restante > 0 and saldo_venc < minimo_restante:
        alertas_caixa.append("o saldo no vencimento não cobre nem o mínimo")

    apresentar = _escolher_apresentacao(sim)
    rotativo = next(o for o in sim["opcoes"] if o["id"] == "minimo_rotativo")
    ids_apresentados = {o["id"] for o in apresentar}
    return {
        "fatura": resumo_fatura,
        "caixa": {
            "saldo_hoje": proj["saldo_atual"],
            "saldo_no_vencimento": saldo_venc,
            "falta_para_o_total": max(-gap, 0.0),
            "cabe_pagar_total": gap >= 0,
            "cabe_pagar_minimo": minimo_restante == 0 or saldo_venc >= minimo_restante,
        },
        "renda_mensal": renda,
        "maiores_gastos": sorted(fatura["itens"], key=lambda i: i["valor"], reverse=True)[:2],
        "alertas_de_caixa": alertas_caixa,
        "recomendada_id": sim["recomendada_id"],
        "motivo_recomendacao": _motivo(sim, saldo_venc),
        "economia_vs_rotativo": sim["economia_vs_rotativo"],
        "requer_apoio_humano": sim["requer_apoio_humano"],
        "opcoes_para_apresentar": [_compacta(o) for o in apresentar],
        "se_nao_fizer_nada": _compacta(rotativo),
        "outras_opcoes": [
            {"id": o["id"], "parcela": o["parcela"], "n_parcelas": o["n_parcelas"], "custo_total": o["custo_total"]}
            for o in sim["opcoes"]
            if o["id"] not in ids_apresentados and o["id"] != "minimo_rotativo"
        ],
        "alertas": sim["alertas"],
    }


def registrar_preferencia(chave: str, valor: str, tool_context: ToolContext) -> dict:
    """Guarda uma preferência do cliente para o próximo mês (memória de longo prazo).

    Chaves e valores aceitos: canal (app, whatsapp, voz); linguagem (simples, tecnica);
    lembrete_dias_antes (1, 3, 5); opcao_preferida (parcelar, pagar_total, pagar_parcial);
    acessibilidade (baixa_visao, leitor_de_tela, baixa_alfabetizacao), esta só depois do
    consentimento de acessibilidade. Nunca registre saúde, família, religião ou outros dados pessoais.
    """
    cid = tool_context.state.get("cliente_id")
    permitidos = PREFERENCIAS_PERMITIDAS.get(chave)
    if not cid or permitidos is None or valor not in permitidos:
        return {"status": "bloqueado", "motivo": "preferência não permitida; só guardo as opções listadas na ferramenta."}
    finalidade = PREFERENCIAS_SENSIVEIS.get(chave)
    if finalidade and not STORE.consentiu(cid, finalidade):
        return {"status": "bloqueado", "motivo": "é dado sensível: peça o consentimento com registrar_consentimento antes."}
    prefs = dict(tool_context.state.get(_chave_prefs(cid), {}))
    prefs[chave] = valor
    tool_context.state[_chave_prefs(cid)] = prefs
    return {"status": "ok", "preferencias": prefs}


def registrar_consentimento(finalidade: str, aceito: bool, tool_context: ToolContext) -> dict:
    """Registra a escolha do cliente para uma finalidade de uso de dados.

    Finalidades: "acessibilidade" (usar a necessidade de acessibilidade para adaptar as
    respostas) e "avisos_proativos" (receber avisos antes do vencimento). Use aceito=false
    quando o cliente recusar ou disser que não quer mais os avisos. Só registre o que o
    cliente disse com clareza nesta conversa.
    """
    cid = tool_context.state["cliente_id"]
    if finalidade not in FINALIDADES:
        return {"status": "bloqueado", "motivo": f"finalidades aceitas: {', '.join(FINALIDADES)}"}
    registro = STORE.registrar_consentimento(cid, finalidade, bool(aceito))
    if finalidade == "acessibilidade" and not aceito:
        prefs = dict(tool_context.state.get(_chave_prefs(cid), {}))
        if prefs.pop("acessibilidade", None) is not None:
            tool_context.state[_chave_prefs(cid)] = prefs
    return {"status": "ok", "finalidade": finalidade, "descricao": FINALIDADES[finalidade], **registro}


def meus_dados(tool_context: ToolContext) -> dict:
    """Mostra ao cliente quais dados dele o Copiloto usa e o que está guardado (LGPD, art. 18)."""
    cid = tool_context.state["cliente_id"]
    return {
        "dados_usados_na_conversa": DADOS_USADOS,
        "dados_que_nao_usamos": ["CPF", "endereço", "telefone", "idade", "score", "negativação"],
        "preferencias_lembradas": tool_context.state.get(_chave_prefs(cid), {}),
        "consentimentos": STORE.consentimentos(cid),
        "lembrete_dias_antes": STORE.lembrete(cid),
        "direitos": "posso apagar as preferências lembradas e registrar se você não quiser mais avisos. "
                    "O registro das suas escolhas de consentimento fica guardado como comprovação.",
    }


def apagar_meus_dados(tool_context: ToolContext) -> dict:
    """Apaga as preferências lembradas do cliente (LGPD, art. 18). Chame só se o cliente pedir."""
    cid = tool_context.state["cliente_id"]
    apagadas = sorted(tool_context.state.get(_chave_prefs(cid), {}))
    tool_context.state[_chave_prefs(cid)] = {}
    STORE._audit({"acao": "preferencias_apagadas", "cliente_id": cid, "chaves": apagadas})
    return {
        "status": "ok",
        "apagado": apagadas or "nada estava guardado",
        "mantido": "registro de consentimentos e de operações financeiras, exigido como comprovação",
    }


def _proximo_vencimento(vencimento: str) -> date:
    d = date.fromisoformat(vencimento)
    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def agendar_lembrete(dias_antes: int, tool_context: ToolContext) -> dict:
    """Agenda o aviso da próxima fatura para N dias antes do vencimento (1 a 10).

    Use quando o cliente aceitar ser lembrado. A rotina proativa passa a avisá-lo nessa janela.
    """
    cid = tool_context.state["cliente_id"]
    try:
        STORE.registrar_lembrete(cid, int(dias_antes))
    except ValueError as e:
        return {"status": "bloqueado", "motivo": str(e)}
    venc = _proximo_vencimento(STORE.vencimento(cid))
    aviso = venc - timedelta(days=int(dias_antes))
    return {"status": "ok", "proximo_vencimento": venc.strftime("%d/%m/%Y"), "aviso_em": aviso.strftime("%d/%m/%Y")}


def acompanhar_progresso(tool_context: ToolContext) -> dict:
    """Mostra o resultado do mês para o cliente: o que foi feito, quanto economizou frente ao rotativo,
    o compromisso mensal e o próximo lembrete. Use depois de uma ação efetivada e quando o cliente
    perguntar como está indo. Os números vêm do core; não calcule nada.
    """
    cid = tool_context.state["cliente_id"]
    fatura = STORE.get_fatura(cid)
    ops = STORE.operacoes(cid)
    pago = round(sum(o["valor_pago"] for o in ops if o["tipo"] == "pagamento"), 2)
    parc = next((o for o in ops if o["tipo"] == "parcelamento"), None)
    total = fatura["valor_total"]
    r: dict = {"objetivo_declarado": STORE.get_perfil(cid)["objetivo_declarado"], "status_da_fatura": fatura["status"]}
    if parc:
        custo = pago + parc["custo_total"]
        feito = f"parcelou {brl(parc['valor_original'])} em {parc['n_parcelas']}x"
        r.update(decisao=f"pagou {brl(pago)} e {feito}" if pago else feito,
                 compromisso_mensal=parc["parcela"], meses=parc["n_parcelas"],
                 economia_vs_rotativo=round(custo_caminho_rotativo(total, parc["n_parcelas"]) - custo, 2))
    elif fatura["status"] == "paga":
        r.update(decisao="pagou a fatura inteira, sem juros",
                 economia_vs_rotativo=round(custo_caminho_rotativo(total, PARAMS.parcelas_pos_rotativo) - total, 2))
    elif pago:
        r.update(decisao=f"pagou {brl(pago)}; faltam {brl(fatura['valor_em_aberto'])}",
                 alerta="o que falta vai para o rotativo se não for pago ou parcelado até o vencimento")
    else:
        r["decisao"] = "nada foi feito ainda neste mês"
    r["evitou_o_rotativo"] = fatura["status"] in {"paga", "parcelada"}
    dias = STORE.lembrete(cid)
    if dias:
        venc = _proximo_vencimento(STORE.vencimento(cid))
        r["proximo_aviso"] = (venc - timedelta(days=dias)).strftime("%d/%m/%Y")
    else:
        r["oferecer_lembrete"] = True
    return r


def consultar_extrato_detalhado(limite: int = 10, tool_context: ToolContext = None) -> dict:
    """Consulta os lançamentos e compras recentes do extrato do cliente.

    Use quando o cliente pedir para detalhar gastos, ver onde mais gastou,
    ou verificar transações específicas (PIX, mercado, delivery, assinaturas).
    Busca diretamente no BigQuery se ativo, com fallback para o core bancário.
    """
    if not tool_context or "cliente_id" not in tool_context.state:
        return {"status": "erro", "motivo": "cliente_id não identificado na sessão"}
    cid = tool_context.state["cliente_id"]
    from proativo.gcp_adapters import bigquery_ativo, obter_extrato_bigquery

    transacoes = []
    fonte = "core_local"
    if bigquery_ativo():
        transacoes = obter_extrato_bigquery(cid, limite=limite)
        if transacoes:
            fonte = "bigquery_extrato_sintetico"

    if not transacoes:
        transacoes = STORE.get_extrato(cid, dias=30)[:limite]

    return {
        "status": "ok",
        "cliente_id": cid,
        "fonte": fonte,
        "total_encontrado": len(transacoes),
        "transacoes": transacoes,
    }


def analisar_caixa_e_liquidez(tool_context: ToolContext = None) -> dict:
    """Diagnóstico preditivo de fluxo de caixa de 30 dias, reserva blindada de compromissos e capital ocioso.

    Identifica compromissos contratuais (financiamento habitacional, mensalidade escolar, condomínio, fatura)
    e calcula o capital ocioso disponível para aplicação em CDB Liquidez Diária, aplicando as travas
    de suitability e risco (política interna inspirada na CVM 30 e na Lei 14.181).
    """
    if not tool_context or "cliente_id" not in tool_context.state:
        return {"status": "erro", "motivo": "cliente_id não identificado na sessão"}
    cid = tool_context.state["cliente_id"]
    cliente_raw = STORE._cliente(cid)
    fluxo = STORE.get_fluxo_previsto(cid)
    saldo_atual = fluxo["saldo_atual"]
    renda = STORE.get_perfil(cid)["renda_mensal"]

    from gestor_caixa.motor_projecao import MotorProjecaoCaixa
    from gestor_caixa.portao_risco import PortaoRisco
    from gestor_caixa.simulador_liquidez import SimuladorLiquidez

    proj = MotorProjecaoCaixa.projetar(cid, saldo_atual, renda, cliente_raw, date.fromisoformat(STORE.hoje()))
    elegivel, motivo_regulatorio = PortaoRisco.avaliar_elegibilidade_investimento(proj)

    resultado = {
        "status": "ok",
        "cliente_id": cid,
        "saldo_atual": proj.saldo_atual,
        "renda_mensal": proj.renda_mensal_esperada,
        "regime": proj.regime.value,
        "compromissos_fixos_proximos": [c.model_dump() for c in proj.compromissos_identificados],
        "colchao_minimo_obrigatorio": proj.colchao_minimo_obrigatorio,
        "capital_ocioso_efetivo": proj.saldo_livre_efetivo,
        "proximo_grande_debito": proj.data_proximo_grande_debito,
        "elegivel_investimento": elegivel,
        "justificativa_suitability": motivo_regulatorio,
        "perfil_investidor": proj.perfil_investidor if proj.perfil_investidor_valido else "ausente ou vencido",
    }

    if elegivel and proj.saldo_livre_efetivo >= 1000.0:
        sim = SimuladorLiquidez.simular_rendimento(proj.saldo_livre_efetivo, 30)
        resultado["oportunidade_cdb"] = {
            "valor_sugerido": proj.saldo_livre_efetivo,
            "produto": "CDB Itaú Liquidez Diária (100% CDI)",
            "rendimento_liquido_30d": sim["rendimento_liquido"],
            "valor_final_liquido_30d": sim["valor_final_liquido"],
            "resgate_programado": f"D-1 de {proj.data_proximo_grande_debito}" if proj.data_proximo_grande_debito else None,
        }

    return resultado


def simular_investimento(valor: float, dias_permanencia: int = 30, tool_context: ToolContext = None) -> dict:
    """Simula o rendimento líquido de um valor em CDB Itaú Liquidez Diária (100% CDI).

    Se o cliente estiver no vermelho ou com gap de caixa, a ferramenta bloqueia a simulação
    por conformidade regulatória e ética financeira.
    """
    if not tool_context or "cliente_id" not in tool_context.state:
        return {"status": "erro", "motivo": "cliente_id não identificado na sessão"}
    cid = tool_context.state["cliente_id"]
    cliente_raw = STORE._cliente(cid)
    fluxo = STORE.get_fluxo_previsto(cid)
    renda = STORE.get_perfil(cid)["renda_mensal"]

    from gestor_caixa.motor_projecao import MotorProjecaoCaixa
    from gestor_caixa.portao_risco import PortaoRisco
    from gestor_caixa.simulador_liquidez import SimuladorLiquidez

    proj = MotorProjecaoCaixa.projetar(cid, fluxo["saldo_atual"], renda, cliente_raw, date.fromisoformat(STORE.hoje()))
    elegivel, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    if not elegivel:
        return {
            "status": "bloqueado",
            "motivo_suitability": motivo,
            "orientacao": "O rendimento de investimentos é muito menor que o custo de juros da dívida. A prioridade financeira é sanear passivos.",
        }

    sim = SimuladorLiquidez.simular_rendimento(valor, dias_permanencia)
    return {
        "status": "ok",
        "produto": "CDB Itaú Liquidez Diária (100% CDI)",
        **sim,
    }


