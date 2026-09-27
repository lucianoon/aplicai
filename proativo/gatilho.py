"""Gatilho proativo: quem precisa do Aplicaí hoje?

Varre a base, projeta o caixa de cada cliente até o vencimento e seleciona
quem deve receber a abertura de conversa. Tudo determinístico e sem LLM:
detecção barata em lote (BigQuery/Pub/Sub em produção), LLM só na conversa.
É o argumento de "momento certo" (Design) e de FinOps de tokens (Arquitetura).

Uso: uv run python -m proativo.gatilho [--janela 5]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from copiloto_fatura.autorizacao import brl
from copiloto_fatura.tools.simulador import projetar_caixa, simular_opcoes
from mock_core.store import STORE
from proativo.gcp_adapters import publicar_gatilhos_pubsub, pubsub_ativo

SAIDA = Path(__file__).resolve().parent / "gatilhos.json"
# LGPD: toda abordagem proativa diz como parar de recebê-la
OPT_OUT = " Se não quiser mais estes avisos, é só responder PARAR."
MOTIVOS = {
    1: "o saldo previsto não cobre nem o pagamento mínimo",
    2: "o saldo previsto não cobre a fatura e há uso recente do rotativo ou restrição de crédito",
    3: "o saldo previsto não cobre a fatura inteira",
}


def _reais_inteiros(valor: float) -> str:
    return f"R$ {valor:,.0f}".replace(",", ".")


def abertura(nome: str, dias: int, gap: float, economia: float, letramento: str, nada_cabe: bool = False) -> str:
    falta = abs(gap)
    if nada_cabe:
        # não prometer solução a quem não tem caixa nem para o mínimo: o caminho é renegociar com apoio humano
        texto = (
            f"Oi, {nome}. Sua fatura vence em {dias} dias e, pelo que vejo, o saldo não cobre nem o pagamento mínimo. "
            "Posso te mostrar os caminhos e te ajudar a falar com um especialista em renegociação, sem julgamento. Quer ver?"
        )
    elif letramento == "baixo":
        # valores redondos, no formato brasileiro (só o milhar leva ponto)
        texto = (
            f"Oi, {nome}. Sua fatura vence em {dias} dias e, pelo que vejo, vai faltar uns {_reais_inteiros(falta)}. "
            f"Tenho um jeito de resolver que custa {_reais_inteiros(economia)} a menos do que deixar no rotativo. Quer ver?"
        )
    else:
        texto = (
            f"{nome}, sua fatura vence em {dias} dias e o saldo projetado fica {brl(falta)} abaixo do total. "
            f"Simulei as alternativas: a melhor economiza {brl(economia)} frente ao rotativo. Posso te mostrar?"
        )
    return texto + OPT_OUT


def avaliar(cliente_id: str, janela: int) -> dict | None:
    perfil = STORE.get_perfil(cliente_id)
    fatura = STORE.get_fatura(cliente_id)
    fluxo = STORE.get_fluxo_previsto(cliente_id)
    dias = fatura["dias_ate_vencimento"]
    janela = STORE.lembrete(cliente_id) or janela  # o cliente pode ter escolhido quantos dias antes
    if dias > janela or fatura["status"] != "aberta":
        return None
    if not STORE.consentiu(cliente_id, "avisos_proativos"):  # oposição registrada pelo cliente
        return None
    proj = projetar_caixa(fluxo["saldo_atual"], fluxo["entradas"], fluxo["saidas"], dias)
    gap = round(proj["saldo_projetado"] - fatura["valor_total"], 2)
    if gap >= 0:
        return None
    sim = simular_opcoes(fatura["valor_total"], proj["saldo_projetado"], perfil["renda_mensal"], dias)
    prioridade = 3
    if proj["saldo_projetado"] < fatura["valor_minimo"]:
        prioridade = 1
    elif perfil["historico_rotativo_12m"] >= 2 or perfil["negativado"]:
        prioridade = 2
    return {
        "cliente_id": cliente_id,
        "primeiro_nome": perfil["primeiro_nome"],
        "dias_ate_vencimento": dias,
        "fatura": fatura["valor_total"],
        "saldo_projetado": proj["saldo_projetado"],
        "gap": gap,
        "prioridade": prioridade,
        "motivo_prioridade": MOTIVOS[prioridade],
        "recomendada": sim["recomendada_id"],
        "economia_vs_rotativo": sim["economia_vs_rotativo"],
        "canal": perfil["canal_preferido"],
        "mensagem_abertura": abertura(perfil["primeiro_nome"], dias, gap, sim["economia_vs_rotativo"],
                                      perfil["letramento_financeiro"], nada_cabe=sim["requer_apoio_humano"]),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--janela", type=int, default=5, help="dias antes do vencimento para disparar")
    ap.add_argument("--pubsub", action="store_true", help="publica os gatilhos no Google Cloud Pub/Sub")
    ap.add_argument("--topico", type=str, default=None, help="tópico do Pub/Sub (ou use COPILOTO_PUBSUB_TOPIC)")
    args = ap.parse_args()
    gatilhos = [g for cid in STORE.listar_ids() if (g := avaliar(cid, args.janela))]
    gatilhos.sort(key=lambda g: (g["prioridade"], g["dias_ate_vencimento"]))
    SAIDA.write_text(json.dumps(gatilhos, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
    total = len(STORE.listar_ids())
    print(f"hoje={STORE.hoje()} janela={args.janela}d | base={total} | gatilhos={len(gatilhos)} "
          f"(P1={sum(g['prioridade']==1 for g in gatilhos)} P2={sum(g['prioridade']==2 for g in gatilhos)} "
          f"P3={sum(g['prioridade']==3 for g in gatilhos)}) | economia potencial=R$ {sum(g['economia_vs_rotativo'] for g in gatilhos):,.2f}")
    for g in gatilhos[:8]:
        print(f"  P{g['prioridade']} {g['cliente_id']} {g['primeiro_nome']:<10} vence em {g['dias_ate_vencimento']}d "
              f"gap R$ {g['gap']:>9.2f} -> {g['recomendada']:<26} economia R$ {g['economia_vs_rotativo']:.2f} [{g['canal']}]")
    print(f"gravado em {SAIDA}")

    if args.pubsub or pubsub_ativo():
        n = publicar_gatilhos_pubsub(gatilhos, topic_id=args.topico)
        if n:
            print(f"publicado no Pub/Sub: {n} mensagens enviadas")


if __name__ == "__main__":
    main()
