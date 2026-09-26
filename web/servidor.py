"""Servidor do SuperApp Itaú e APIs de Produção (com Copiloto IA.Í / ADK).

Endpoints:
- /                             : Tela principal do Itaú SuperApp (Mobile)
- /api/contas                   : Lista de contas disponíveis no ambiente
- /api/conta/{cliente_id}       : Visão consolidada (Saldos, Fatura, Custódia, Smart Cards do Gestor de Caixa)
- /api/executar/investimento    : Execução de aplicação CDB com capability HMAC (2-Phase Commit)
- /api/executar/resgate         : Resgate de CDB para conta corrente
- /api/executar/parcelamento    : Contratação de parcelamento sem rotativo
- /demo/personas, /demo/reiniciar : Compatibilidade retroativa para suíte de testes
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv

load_dotenv(RAIZ / ".env")

import uvicorn
from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from pydantic import BaseModel

from copiloto_fatura.autorizacao import assinar, cotar
from gestor_caixa.motor_projecao import MotorProjecaoCaixa
from gestor_caixa.portao_risco import PortaoRisco
from gestor_caixa.simulador_liquidez import SimuladorLiquidez
from mock_core.store import STORE
from proativo.gatilho import avaliar

ESTATICOS = Path(__file__).resolve().parent / "static"

PERSONAS = {
    "C001": {
        "nome": "Ana Souza",
        "tag": "Imprevisto no Mês",
        "badge": "Falta saldo para o total",
        "cor": "aviso",
        "bigquery_id": "3f3f7877-71fd-4073-b0a8-692b105609d8",
        "resumo": "Fatura de R$ 1.850,00 vence em 5 dias. Saldo de R$ 610,00 (falta R$ 1.240,00). Teve despesa inesperada com veículo.",
        "fatura_formatada": "R$ 1.850,00",
        "saldo_formatado": "R$ 610,00",
        "vencimento_texto": "Vence em 5 dias",
        "cenario": "Déficit pontual no mês (evitar rotativo abusivo)",
    },
    "C002": {
        "nome": "Bruno Silveira",
        "tag": "Descasamento de Fluxo",
        "badge": "Salário após o vencimento",
        "cor": "atencao",
        "bigquery_id": "3df4aa25-75c6-4a76-af42-40f761ada3fe",
        "resumo": "Salário entra no dia 10 (R$ 9.800), mas fatura de R$ 3.100 vence dia 05. Paga juros de rotativo desnecessários por apenas 5 dias.",
        "fatura_formatada": "R$ 3.100,00",
        "saldo_formatado": "R$ 7.400,00 (no salário)",
        "vencimento_texto": "Vence em 5 dias",
        "cenario": "Ajuste preventivo do vencimento para o dia 12",
    },
    "C003": {
        "nome": "Carla Pereira",
        "tag": "Superendividamento",
        "badge": "Sem saldo para o mínimo",
        "cor": "critico",
        "bigquery_id": "16c787c7-9510-41fa-a10c-7183c7d12008",
        "resumo": "12 meses no negativo, saldo no extrato de -R$ 14.078,22. Fatura aberta de R$ 2.380 sem margem para o mínimo.",
        "fatura_formatada": "R$ 2.380,00",
        "saldo_formatado": "-R$ 14.078,22",
        "vencimento_texto": "Vence em 2 dias",
        "cenario": "Proteção Lei 14.181 e acolhimento humano",
    },
    "C004": {
        "nome": "Diego Takahashi",
        "tag": "Poupador & Planejamento",
        "badge": "Controle e Organização",
        "cor": "sucesso",
        "bigquery_id": "fe52b305-9f7c-4e06-8bfe-7950f882fdfa",
        "resumo": "0 meses no negativo, saldo de R$ 38.250,00. Fatura de R$ 4.250 em aberto para categorização inteligente de gastos.",
        "fatura_formatada": "R$ 4.250,00",
        "saldo_formatado": "R$ 38.250,00",
        "vencimento_texto": "Vence em 8 dias",
        "cenario": "Otimização de gastos e reserva financeira",
    },
}

app = get_fast_api_app(agents_dir=str(RAIZ), web=False, use_local_storage=False)


def formatar_moeda(valor: float) -> str:
    sinal = "-" if valor < 0 else ""
    return f"{sinal}R$ {abs(valor):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")


def obter_segmento_e_conta(cid: str, renda: float) -> dict[str, str]:
    num = int("".join(filter(str.isdigit, cid)) or "1")
    agencia = f"{(num * 17) % 9000 + 1000:04d}"
    conta = f"{(num * 31) % 90000 + 10000:05d}-{(num * 7) % 10}"
    if renda >= 12000.0:
        segmento = "Itaú Personnalité"
    elif renda >= 4000.0:
        segmento = "Itaú Uniclass"
    else:
        segmento = "Itaú Varejo"
    return {"agencia": agencia, "conta": conta, "segmento": segmento}


def calcular_diagnostico_cliente(cid: str) -> dict[str, Any]:
    raw = STORE._cliente(cid)
    saldo_atual = float(raw["saldo_conta"])
    renda_mensal = float(raw["renda_mensal"])
    proj = MotorProjecaoCaixa.projetar(cid, saldo_atual, renda_mensal, raw)
    aut_inv, mot_inv = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    alivio_passivo = PortaoRisco.avaliar_necessidade_alivio_passivo(proj)

    simulacao_inv = None
    if aut_inv and proj.saldo_livre_efetivo >= 500.0:
        simulacao_inv = SimuladorLiquidez.simular_rendimento(proj.saldo_livre_efetivo, 30)

    fatura = STORE.get_fatura(cid)
    em_aberto = fatura["valor_em_aberto"]
    simulacao_parc_3x = None
    if fatura["status"] in ("aberta", "paga_parcialmente") and em_aberto > 0:
        simulacao_parc_3x = STORE.cotar_parcelamento(cid, 3)

    # Definição do Smart Card Proativo (Action-First)
    if proj.regime.value == "oportunidade_liquidez":
        rend_mes = simulacao_inv["rendimento_liquido"] if simulacao_inv else 189.07
        smart_card = {
            "tipo": "OPORTUNIDADE_CDB",
            "icone": "⚡",
            "tag": "Oportunidade de Liquidez",
            "titulo": f"Você tem {formatar_moeda(proj.saldo_livre_efetivo)} sem render na conta corrente",
            "descricao": (
                f"Calculamos suas despesas até o próximo ciclo (compromissos fixos e fatura protegidos pelo nosso colchão de {formatar_moeda(proj.colchao_minimo_obrigatorio)}). "
                f"Sua liquidez ociosa pode render {formatar_moeda(rend_mes)} líquidos por mês no CDB Itaú (100% CDI)."
            ),
            "acao_primaria_texto": f"Aplicar {formatar_moeda(proj.saldo_livre_efetivo)} com iToken",
            "acao_primaria_payload": {
                "tipo": "aplicar_cdb",
                "valor": proj.saldo_livre_efetivo,
                "dias_permanencia": 30,
            },
            "acao_secundaria_texto": "Tirar dúvidas com a IA.Í",
            "acao_secundaria_prompt": (
                f"Por que você recomendou aplicar {formatar_moeda(proj.saldo_livre_efetivo)} no CDB "
                f"e deixou {formatar_moeda(proj.colchao_minimo_obrigatorio)} de colchão de segurança?"
            ),
            "destaque_valor": f"+{formatar_moeda(rend_mes)}/mês",
            "destaque_label": "Rendimento Líquido Estimado",
            "cor_tema": "laranja",
        }
    elif proj.regime.value in ("deficit_previsto", "deficit_critico"):
        if proj.regime.value == "deficit_critico":
            smart_card = {
                "tipo": "REPACTUACAO_DIVIDA",
                "icone": "🤝",
                "tag": "Programa de Acolhimento Financeiro",
                "titulo": "Proteção e Repactuação sob a Lei 14.181",
                "descricao": (
                    "Identificamos pressão financeira nos últimos meses. Seus encargos rotativos estão sob monitoramento ético "
                    "e podemos unificar seus compromissos com condições especiais de renegociação."
                ),
                "acao_primaria_texto": "Falar com Especialista de Renegociação",
                "acao_primaria_payload": {"tipo": "especialista"},
                "acao_secundaria_texto": "Entender direitos no Copiloto IA.Í",
                "acao_secundaria_prompt": "Quais são meus direitos sob a Lei do Superendividamento (Lei 14.181) e como o Itaú pode me ajudar?",
                "destaque_valor": "Suspensão de Encargos",
                "destaque_label": "Cuidado e Proteção Ética",
                "cor_tema": "vermelho",
            }
        else:
            valor_parc = simulacao_parc_3x["parcela"] if simulacao_parc_3x else 640.0
            smart_card = {
                "tipo": "ESCUDO_ANTI_ROTATIVO",
                "icone": "🛡️",
                "tag": "Proteção contra Rotativo",
                "titulo": "Evite o rotativo de 14,9% a.m.: Parcele com taxa reduzida",
                "descricao": (
                    f"Seu saldo previsto não cobrirá o total da fatura ({formatar_moeda(em_aberto)}). "
                    f"Ao optar pelo parcelamento planejado em 3x de {formatar_moeda(valor_parc)}, você economiza até R$ 375,10 em juros abusivos."
                ),
                "acao_primaria_texto": f"Proteger Fatura em 3x de {formatar_moeda(valor_parc)}",
                "acao_primaria_payload": {
                    "tipo": "parcelar_fatura",
                    "n_parcelas": 3,
                },
                "acao_secundaria_texto": "Simular outras parcelas com a IA.Í",
                "acao_secundaria_prompt": "Quais são as opções de parcelamento da minha fatura e quanto economizo em relação ao rotativo?",
                "destaque_valor": "Economia de R$ 375,10",
                "destaque_label": "Juros Evitados vs Rotativo",
                "cor_tema": "amarelo",
            }
    else:
        smart_card = {
            "tipo": "EQUILIBRIO_FINANCEIRO",
            "icone": "✨",
            "tag": "Finanças em Dia",
            "titulo": "Suas contas e fatura estão equilibradas neste ciclo",
            "descricao": "Nenhum risco de rotativo identificado e fluxo futuro coberto pelos recebimentos previstos.",
            "acao_primaria_texto": "Ver Extrato Detalhado",
            "acao_primaria_payload": {"tipo": "extrato"},
            "acao_secundaria_texto": "Consultar IA.Í",
            "acao_secundaria_prompt": "Como posso otimizar meus gastos e planejar minha reserva financeira?",
            "destaque_valor": "100%",
            "destaque_label": "Controle Financeiro",
            "cor_tema": "verde",
        }

    return {
        "regime": proj.regime.value,
        "saldo_atual": proj.saldo_atual,
        "saldo_livre_efetivo": proj.saldo_livre_efetivo,
        "colchao_minimo_obrigatorio": proj.colchao_minimo_obrigatorio,
        "proximo_grande_debito": proj.data_proximo_grande_debito,
        "valor_proximo_grande_debito": proj.valor_proximo_grande_debito,
        "elegivel_investimento": aut_inv,
        "motivo_investimento": mot_inv,
        "alivio_passivo": alivio_passivo,
        "simulacao_investimento": simulacao_inv,
        "simulacao_parcelamento": simulacao_parc_3x,
        "smart_card": smart_card,
    }


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def pagina() -> HTMLResponse:
    conteudo = (ESTATICOS / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(
        content=conteudo,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/api/contas")
def listar_contas() -> dict[str, Any]:
    """Lista contas disponíveis no ambiente com segmentação bancária real."""
    contas = []
    # Clientes prioritários de demonstração e calibração
    ids_foco = ["C004", "C001", "C002", "C003"]
    for cid in ids_foco:
        raw = STORE._cliente(cid)
        seg = obter_segmento_e_conta(cid, raw["renda_mensal"])
        custodia = STORE.get_investimentos(cid)
        fatura = STORE.get_fatura(cid)
        diag = calcular_diagnostico_cliente(cid)
        contas.append({
            "cliente_id": cid,
            "nome": raw["nome"],
            "primeiro_nome": raw["nome"].split()[0],
            "agencia": seg["agencia"],
            "conta": seg["conta"],
            "segmento": seg["segmento"],
            "saldo_conta": raw["saldo_conta"],
            "saldo_formatado": formatar_moeda(raw["saldo_conta"]),
            "investido": custodia.get("cdb_liquidez_diaria", 0.0),
            "investido_formatado": formatar_moeda(custodia.get("cdb_liquidez_diaria", 0.0)),
            "fatura_formatada": formatar_moeda(fatura["valor_total"]),
            "regime": diag["regime"],
            "smart_card_tag": diag["smart_card"]["tag"],
        })
    return {"contas": contas}


@app.get("/api/conta/{cliente_id}")
def obter_conta_detalhada(cliente_id: str) -> dict[str, Any]:
    """Retorna o estado consolidado da conta bancária, investimentos e Smart Card proativo."""
    try:
        raw = STORE._cliente(cliente_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Conta {cliente_id} não encontrada") from e

    seg = obter_segmento_e_conta(cliente_id, raw["renda_mensal"])
    custodia = STORE.get_investimentos(cliente_id)
    fatura = STORE.get_fatura(cliente_id)
    extrato = STORE.get_extrato(cliente_id, dias=30)
    diag = calcular_diagnostico_cliente(cliente_id)

    limite_lis = 5000.0 if raw["renda_mensal"] > 5000 else 1500.0

    return {
        "cliente_id": cliente_id,
        "nome": raw["nome"],
        "primeiro_nome": raw["nome"].split()[0],
        "agencia": seg["agencia"],
        "conta": seg["conta"],
        "segmento": seg["segmento"],
        "saldo_conta": raw["saldo_conta"],
        "saldo_formatado": formatar_moeda(raw["saldo_conta"]),
        "limite_cheque_especial": limite_lis,
        "limite_cheque_especial_formatado": formatar_moeda(limite_lis),
        "custodia_investimentos": custodia,
        "total_investido": custodia.get("cdb_liquidez_diaria", 0.0),
        "total_investido_formatado": formatar_moeda(custodia.get("cdb_liquidez_diaria", 0.0)),
        "fatura": fatura,
        "fatura_formatada": formatar_moeda(fatura["valor_total"]),
        "fatura_em_aberto_formatada": formatar_moeda(fatura["valor_em_aberto"]),
        "extrato_recente": extrato[:5],
        "diagnostico": diag,
    }


class RequisicaoInvestimento(BaseModel):
    cliente_id: str
    valor: float
    dias_permanencia: int = 30


@app.post("/api/executar/investimento")
def executar_investimento(req: RequisicaoInvestimento) -> dict[str, Any]:
    """Aplica no CDB com 2-Phase Commit e capability HMAC assinada (Zero-LLM execution)."""
    raw = STORE._cliente(req.cliente_id)
    proj = MotorProjecaoCaixa.projetar(req.cliente_id, raw["saldo_conta"], raw["renda_mensal"], raw)
    aut, mot = PortaoRisco.avaliar_elegibilidade_investimento(proj)
    if not aut:
        raise HTTPException(status_code=400, detail=mot)

    args = {"valor": req.valor, "dias_permanencia": req.dias_permanencia}
    cotacao = cotar(STORE, "aplicar_cdb", req.cliente_id, args)
    nonce = secrets.token_hex(16)
    token = assinar(cotacao, nonce)
    recibo = STORE.executar_autorizada("aplicar_cdb", req.cliente_id, args, token, canal="app_superapp_itoken")

    # Autenticação digital bancária oficial
    auth_hash = hashlib.sha256(f"{recibo['comprovante_id']}:{nonce}:{time.time()}".encode()).hexdigest()[:24].upper()
    return {
        "status": "sucesso",
        "recibo": recibo,
        "autenticacao_digital": auth_hash,
        "saldo_novo": recibo["novo_saldo_conta"],
        "saldo_investido_novo": recibo["saldo_total_investido"],
    }


class RequisicaoResgate(BaseModel):
    cliente_id: str
    valor: float


@app.post("/api/executar/resgate")
def executar_resgate(req: RequisicaoResgate) -> dict[str, Any]:
    """Resgata do CDB de Liquidez Diária para a conta corrente."""
    args = {"valor": req.valor}
    cotacao = cotar(STORE, "resgatar_cdb", req.cliente_id, args)
    nonce = secrets.token_hex(16)
    token = assinar(cotacao, nonce)
    recibo = STORE.executar_autorizada("resgatar_cdb", req.cliente_id, args, token, canal="app_superapp_itoken")
    auth_hash = hashlib.sha256(f"{recibo['comprovante_id']}:{nonce}:{time.time()}".encode()).hexdigest()[:24].upper()
    return {
        "status": "sucesso",
        "recibo": recibo,
        "autenticacao_digital": auth_hash,
        "saldo_novo": recibo["novo_saldo_conta"],
        "saldo_investido_novo": recibo["saldo_total_investido"],
    }


class RequisicaoParcelamento(BaseModel):
    cliente_id: str
    n_parcelas: int = 3


@app.post("/api/executar/parcelamento")
def executar_parcelamento(req: RequisicaoParcelamento) -> dict[str, Any]:
    """Contrata parcelamento planejado de fatura (sem rotativo)."""
    args = {"n_parcelas": req.n_parcelas}
    cotacao = cotar(STORE, "parcelar_fatura", req.cliente_id, args)
    nonce = secrets.token_hex(16)
    token = assinar(cotacao, nonce)
    recibo = STORE.executar_autorizada("parcelar_fatura", req.cliente_id, args, token, canal="app_superapp_itoken")
    auth_hash = hashlib.sha256(f"{recibo['contrato_id']}:{nonce}:{time.time()}".encode()).hexdigest()[:24].upper()
    return {
        "status": "sucesso",
        "recibo": recibo,
        "autenticacao_digital": auth_hash,
    }


@app.get("/demo/personas")
@app.get("/api/personas")
def personas() -> dict:
    """Compatibilidade com testes existentes e avaliações legadas."""
    lista = []
    for cid, info in PERSONAS.items():
        alvo = avaliar(cid, 30) if STORE.consentiu(cid, "avisos_proativos") else None
        fatura = STORE.get_fatura(cid)
        lista.append({
            "id": cid,
            "nome": info["nome"],
            "primeiro_nome": STORE.get_perfil(cid)["primeiro_nome"],
            "tag": info["tag"],
            "badge": info["badge"],
            "cor": info["cor"],
            "bigquery_id": info["bigquery_id"],
            "resumo": info["resumo"],
            "fatura_formatada": info["fatura_formatada"],
            "saldo_formatado": info["saldo_formatado"],
            "vencimento_texto": info["vencimento_texto"],
            "cenario": info["cenario"],
            "abertura": alvo["mensagem_abertura"] if alvo else None,
            "dias": fatura["dias_ate_vencimento"],
        })
    return {"modelo": os.getenv("COPILOTO_MODEL", "gemini-3.5-flash-lite"), "personas": lista}


@app.post("/demo/reiniciar")
def reiniciar() -> dict:
    """Volta o banco simulado ao estado inicial (faturas, consentimentos e lembretes)."""
    for caminho in (STORE.consent_path, STORE.lembretes_path):
        caminho.unlink(missing_ok=True)
    STORE.reset()
    return {"status": "ok"}


app.mount("/static", StaticFiles(directory=ESTATICOS), name="static")

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    porta = int(os.getenv("PORT") or os.getenv("PORTA") or "8080")
    uvicorn.run(app, host=host, port=porta)
