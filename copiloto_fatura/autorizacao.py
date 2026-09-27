"""Autorização de ações: cotação aprovada pelo cliente -> capacidade assinada -> core confere.

Fluxo (ver ``guardrails.exigir_aprovacao`` e ``mock_core.store.executar_autorizada``):

1. O guardrail calcula a cotação com dados do core e pede aprovação pelo canal
   de ToolConfirmation do ADK. A aprovação vale 5 minutos, para aquela chamada
   e aquela cotação, e só pode ser usada uma vez.
2. Aprovada, o host emite uma capacidade assinada (HMAC, 60 segundos) com a
   cotação e um nonce. O modelo nunca vê nem preenche esse valor.
3. O core confere assinatura, validade, ação, cliente e parâmetros, recalcula a
   cotação e só então executa. A mesma capacidade repetida devolve o recibo
   original (replay), sem novo débito. Vale para tools diretas e para o MCP.

O segredo é gerado no host e passado ao processo MCP pelo ambiente
(``COPILOTO_AUTH_SECRET``). Em produção: chave em Secret Manager/KMS e
titular vindo da sessão autenticada do canal.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import secrets
import time

SEGREDO = os.getenv("COPILOTO_AUTH_SECRET") or secrets.token_hex(32)
VALIDADE_CAPACIDADE_S = 60
ACOES = ("parcelar_fatura", "pagar_fatura", "aplicar_cdb", "resgatar_cdb")


def brl(valor: float) -> str:
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def parametros(acao: str, args: dict) -> dict:
    """Parâmetros normalizados da ação (o que a aprovação e a capacidade vinculam)."""
    if acao == "parcelar_fatura":
        n = args.get("n_parcelas")
        if isinstance(n, bool) or not isinstance(n, (int, float)) or int(n) != n or not 2 <= n <= 24:
            raise ValueError("parcelas devem ser um número inteiro entre 2 e 24")
        return {"n_parcelas": int(n)}
    if acao in ("pagar_fatura", "aplicar_cdb", "resgatar_cdb"):
        v = args.get("valor")
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            raise ValueError("valor deve ser um número positivo")
        p = {"valor": round(float(v), 2)}
        if acao == "aplicar_cdb":
            dias = args.get("dias_permanencia", 30)
            p["dias_permanencia"] = int(dias) if isinstance(dias, (int, float)) and dias > 0 else 30
        return p
    raise ValueError("operação não permitida")


def cotar(store, acao: str, cliente_id: str, args: dict) -> dict:
    """Cotação da ação com dados atuais do core. Recalculada na execução: se mudar, não executa."""
    p = parametros(acao, args)
    if acao in ("aplicar_cdb", "resgatar_cdb"):
        q = {"acao": acao, "cliente_id": cliente_id, **p}
        if acao == "aplicar_cdb":
            from gestor_caixa.motor_projecao import MotorProjecaoCaixa
            from gestor_caixa.portao_risco import PortaoRisco
            from gestor_caixa.simulador_liquidez import SimuladorLiquidez

            # portão de suitability e colchão no caminho de execução: vale para agente, MCP e app
            saldo = store.get_fluxo_previsto(cliente_id)["saldo_atual"]
            renda = store.get_perfil(cliente_id)["renda_mensal"]
            proj = MotorProjecaoCaixa.projetar(cliente_id, saldo, renda, store._cliente(cliente_id))
            elegivel, motivo = PortaoRisco.avaliar_elegibilidade_investimento(proj)
            if not elegivel:
                raise ValueError(motivo)
            if p["valor"] > proj.saldo_livre_efetivo:
                raise ValueError(
                    f"o valor passa do capital livre para aplicar ({brl(proj.saldo_livre_efetivo)}): "
                    f"{brl(proj.colchao_minimo_obrigatorio)} ficam reservados para os compromissos do mês"
                )
            sim = SimuladorLiquidez.simular_rendimento(p["valor"], p.get("dias_permanencia", 30))
            q.update(
                rendimento_liquido=sim["rendimento_liquido"],
                valor_final=sim["valor_final_liquido"],
                produto="CDB Itaú Liquidez Diária (100% CDI)",
            )
        else:  # resgatar_cdb
            investido = store.get_investimentos(cliente_id).get("cdb_liquidez_diaria", 0.0)
            if p["valor"] > investido:
                raise ValueError(f"saldo investido ({brl(investido)}) insuficiente para resgate de {brl(p['valor'])}")
            q.update(novo_saldo_investido=round(investido - p["valor"], 2))
        return q

    fatura = store.get_fatura(cliente_id)
    if fatura["status"] not in ("aberta", "paga_parcialmente"):
        raise ValueError(f"a fatura já está {fatura['status']}")
    em_aberto = fatura["valor_em_aberto"]
    q = {"acao": acao, "cliente_id": cliente_id, "vencimento": store.vencimento(cliente_id),
         "fatura": em_aberto, "restante": em_aberto < fatura["valor_total"], **p}
    if acao == "parcelar_fatura":
        cot = store.cotar_parcelamento(cliente_id, p["n_parcelas"])
        q.update(parcela=cot["parcela"], custo_total=cot["custo_total"])
    else:
        if p["valor"] > em_aberto:
            raise ValueError(f"o valor passa do que falta pagar da fatura ({brl(em_aberto)})")
        if p["valor"] > store.get_fluxo_previsto(cliente_id)["saldo_atual"]:
            raise ValueError("saldo em conta insuficiente para esse valor")
    return q


def resumo(q: dict) -> str:
    """Texto que o cliente vê na aprovação, gerado a partir da cotação (não pelo modelo)."""
    if q["acao"] == "aplicar_cdb":
        rend_est = q.get("rendimento_liquido", 0.0)
        return (f"Aplicar {brl(q['valor'])} no CDB Itaú Liquidez Diária (100% CDI) "
                f"com rendimento estimado de {brl(rend_est)} em {q.get('dias_permanencia', 30)} dias. Aprova?")
    if q["acao"] == "resgatar_cdb":
        return f"Resgatar {brl(q['valor'])} do CDB Liquidez Diária para a sua conta corrente. Aprova?"
    restante = q.get("restante")
    if q["acao"] == "parcelar_fatura":
        alvo = f"o restante da fatura, {brl(q['fatura'])}," if restante else f"a fatura de {brl(q['fatura'])}"
        return (f"Parcelar {alvo} em {q['n_parcelas']}x de {brl(q['parcela'])} "
                f"(custo total {brl(q['custo_total'])}). Aprova?")
    alvo = f"do restante da fatura ({brl(q['fatura'])})" if restante else f"da fatura de {brl(q['fatura'])}"
    return f"Pagar {brl(q['valor'])} {alvo} com o saldo da conta. Aprova?"


def assinar(cotacao: dict, nonce: str) -> str:
    payload = json.dumps({"cotacao": cotacao, "nonce": nonce, "expira": time.time() + VALIDADE_CAPACIDADE_S},
                         sort_keys=True, ensure_ascii=False)
    sig = hmac.new(SEGREDO.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return json.dumps({"payload": payload, "assinatura": sig})


def verificar(token: str | None, acao: str, cliente_id: str, args: dict) -> dict:
    """Confere a capacidade no core. Qualquer divergência vira a mesma recusa genérica."""
    try:
        envelope = json.loads(token or "")
        payload = envelope["payload"]
        sig = hmac.new(SEGREDO.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, envelope["assinatura"]):
            raise ValueError
        dados = json.loads(payload)
        q = dados["cotacao"]
        if dados["expira"] < time.time() or q["acao"] != acao or q["cliente_id"] != cliente_id:
            raise ValueError
        if any(q[k] != v for k, v in parametros(acao, args).items()):
            raise ValueError
        return dados
    except (ValueError, TypeError, KeyError):
        raise ValueError("autorização ausente, inválida ou expirada: peça a aprovação do cliente de novo") from None
