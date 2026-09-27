"""Sincroniza e enriquece data/clientes.json a partir do BigQuery (extrato_sintetico).

Lê os dados reais da tabela hackathon_dados.extrato_sintetico do projeto batalha-time-09-nciv,
agrega os 1.000 clientes e gera o arquivo clientes.json compatível com o mock_core/store.py,
mantendo intactas as 3 personas de teste (C001, C002, C003) para garantir que
todos os testes do pytest e evalsets continuem passando com 100% de sucesso.

Uso:
    uv run python scripts/carregar_dados_extrato_sintetico.py [--limite 200] [--projeto batalha-time-09-nciv]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from google.cloud import bigquery

from data.gerar_dataset import perfil_investidor_sintetico

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

RAIZ = Path(__file__).resolve().parents[1]
SAIDA = RAIZ / "data" / "clientes.json"

NOMES = [
    "Ana", "Bruno", "Carla", "Diego", "Elaine", "Fábio", "Gabriela", "Henrique", "Isabela",
    "João", "Karina", "Lucas", "Mariana", "Nelson", "Olívia", "Paulo", "Quitéria", "Rafael",
    "Sônia", "Tiago", "Úrsula", "Vinícius", "Wagner", "Ximena", "Yara", "Zeca",
]
SOBRENOMES = ["Silva", "Santos", "Oliveira", "Souza", "Lima", "Pereira", "Costa", "Ferreira"]


def carregar_clientes_do_bigquery(
    project_id: str = "batalha-time-09-nciv",
    dataset_id: str = "hackathon_dados",
    table_id: str = "extrato_sintetico",
    limite_clientes: int = 200,
) -> list[dict[str, Any]]:
    """Consulta o extrato_sintetico no BigQuery e consolida perfis financeiros."""
    client = bigquery.Client(project=project_id)
    tabela_completa = f"`{project_id}.{dataset_id}.{table_id}`"

    logger.info("Consultando BigQuery: %s (limite: %d clientes)...", tabela_completa, limite_clientes)

    # 1. Agregação financeira dos clientes
    sql_agregado = f"""
    WITH ultimas_transacoes AS (
        SELECT 
            id_usuario,
            saldo_apos,
            anomesdia,
            ROW_NUMBER() OVER(PARTITION BY id_usuario ORDER BY anomesdia DESC) as rn
        FROM {tabela_completa}
    ),
    metricas AS (
        SELECT
            id_usuario,
            ROUND(SUM(IF(tipo = 'E', vlr, 0)) / 12, 2) as renda_mensal,
            ROUND(SUM(IF(tipo = 'S', vlr, 0)) / 12, 2) as gasto_mensal,
            ROUND(AVG(IF(nom_cate_micro = 'Pagamento de fatura', vlr, NULL)), 2) as media_fatura,
            COUNT(DISTINCT IF(saldo_apos < 0, anomes, NULL)) as meses_rotativo_negativo,
            ROUND(MIN(saldo_apos), 2) as pior_saldo,
            COUNT(*) as total_transacoes
        FROM {tabela_completa}
        GROUP BY id_usuario
    )
    SELECT 
        m.id_usuario,
        m.renda_mensal,
        m.gasto_mensal,
        COALESCE(m.media_fatura, ROUND(m.gasto_mensal * 0.4, 2)) as fatura_estimada,
        m.meses_rotativo_negativo,
        m.pior_saldo,
        m.total_transacoes,
        u.saldo_apos as ultimo_saldo
    FROM metricas m
    JOIN ultimas_transacoes u ON m.id_usuario = u.id_usuario AND u.rn = 1
    ORDER BY m.meses_rotativo_negativo DESC, m.renda_mensal DESC
    LIMIT {limite_clientes}
    """

    job = client.query(sql_agregado)
    usuarios_agregados = [dict(row.items()) for row in job]
    logger.info("Recuperados %d usuários agregados.", len(usuarios_agregados))

    # 2. Buscar últimas transações de cartão e categorias para compor a fatura
    ids_lista = "', '".join([u["id_usuario"] for u in usuarios_agregados])
    sql_faturas = f"""
    SELECT 
        id_usuario,
        nom_cate_macro,
        nom_cate_micro,
        ROUND(SUM(vlr), 2) as total_cat
    FROM {tabela_completa}
    WHERE id_usuario IN ('{ids_lista}')
      AND tipo = 'S'
      AND nom_cate_micro != 'Pagamento de fatura'
      AND nom_cate_micro != 'Financiamento de imovel'
      AND anomes = 202512
    GROUP BY id_usuario, nom_cate_macro, nom_cate_micro
    ORDER BY total_cat DESC
    """
    job_itens = client.query(sql_faturas)
    itens_por_usuario: dict[str, list[dict[str, Any]]] = {}
    for row in job_itens:
        uid = row["id_usuario"]
        itens_por_usuario.setdefault(uid, []).append({
            "categoria": (row["nom_cate_macro"] or "outros").lower(),
            "micro": row["nom_cate_micro"],
            "valor": float(row["total_cat"]),
        })

    # 3. Montar objetos cliente no formato do copiloto
    rng = random.Random(42)
    clientes_formatados = []

    for idx, u in enumerate(usuarios_agregados, start=1):
        uid = u["id_usuario"]
        renda = float(u["renda_mensal"])
        saldo = float(u["ultimo_saldo"] or 0.0)
        fatura_val = float(u["fatura_estimada"] or (renda * 0.35))
        meses_neg = int(u["meses_rotativo_negativo"])
        negativado = meses_neg >= 3 or float(u["pior_saldo"]) < -5000.0

        itens_fatura = itens_por_usuario.get(uid, [])
        if not itens_fatura:
            itens_fatura = [
                {"categoria": "supermercado", "valor": round(fatura_val * 0.45, 2)},
                {"categoria": "lojas e sites", "valor": round(fatura_val * 0.35, 2)},
                {"categoria": "outros", "valor": round(fatura_val * 0.20, 2)},
            ]
        else:
            # simplificar categorias
            itens_fatura = [{"categoria": it["categoria"], "valor": it["valor"]} for it in itens_fatura[:5]]

        letramento = "baixo" if (negativado or meses_neg >= 2) else ("alto" if renda > 8000 and meses_neg == 0 else "medio")
        canal = rng.choice(["app", "whatsapp", "app", "voz"])
        acessibilidade = rng.choice([None, None, None, None, "baixa_visao", "leitor_de_tela", "baixa_alfabetizacao"])
        objetivo = rng.choice([None, "sair do vermelho", "reserva de emergência", "organizar contas"]) if meses_neg > 0 else "reserva de emergência"

        # Simular entradas e saídas previstas dos próximos dias
        dia_salario = rng.randint(5, 10)
        entradas_previstas = [
            {"dia_offset": dia_salario, "valor": round(renda * 0.95, 2), "descricao": "salário clt"}
        ]
        saidas_previstas = [
            {"dia_offset": rng.randint(1, 10), "valor": round(renda * 0.25, 2), "descricao": "moradia / condomínio"},
            {"dia_offset": rng.randint(5, 15), "valor": round(renda * 0.06, 2), "descricao": "energia elétrica"},
        ]

        cliente_dict = {
            "cliente_id": f"C{idx+3:03d}",
            "uuid": uid,
            "alias_id": uid,
            "nome": f"{rng.choice(NOMES)} {rng.choice(SOBRENOMES)}",
            "idade": rng.randint(22, 68),
            "renda_mensal": renda,
            "saldo_conta": saldo,
            "score": max(300, min(950, int(850 - meses_neg * 50 + (renda / 100)))),
            "negativado": negativado,
            "letramento_financeiro": letramento,
            "acessibilidade": acessibilidade,
            "canal_preferido": canal,
            "historico_rotativo_12m": meses_neg,
            "objetivo_declarado": objetivo,
            "perfil_investidor": perfil_investidor_sintetico(f"C{idx+3:03d}"),
            "limite_total": round(max(fatura_val * 1.5, renda * 0.8), 2),
            "fatura": {
                "valor_total": fatura_val,
                "dias_ate_vencimento": rng.randint(2, 10),
                "itens": itens_fatura,
                "status": "aberta",
            },
            "entradas_previstas": entradas_previstas,
            "saidas_previstas": saidas_previstas,
            "transacoes_30d": [
                {
                    "dias_atras": rng.randint(1, 28),
                    "categoria": it["categoria"],
                    "valor": round(it["valor"] * 0.3, 2),
                    "meio": "cartao",
                }
                for it in itens_fatura
            ],
        }
        clientes_formatados.append(cliente_dict)

    return clientes_formatados


def main():
    parser = argparse.ArgumentParser(description="Gera data/clientes.json a partir do BigQuery.")
    parser.add_argument("--limite", type=int, default=200, help="Quantidade de clientes a importar do BigQuery")
    parser.add_argument("--projeto", default="batalha-time-09-nciv", help="Projeto GCP")
    parser.add_argument("--dataset", default="hackathon_dados", help="Dataset BigQuery")
    parser.add_argument("--tabela", default="extrato_sintetico", help="Tabela BigQuery")
    args = parser.parse_args()

    # Importar personas de demo existentes para manter 100% compatibilidade de testes
    from data.gerar_dataset import personas_demo

    personas = personas_demo()

    try:
        clientes_bq = carregar_clientes_do_bigquery(
            project_id=args.projeto,
            dataset_id=args.dataset,
            table_id=args.tabela,
            limite_clientes=args.limite,
        )
    except Exception as exc:
        logger.error("Erro ao ler do BigQuery: %s", exc)
        return

    # Unir personas com dados reais
    todos_clientes = list(personas) + clientes_bq

    resultado = {
        "meta": {
            "gerado_em": datetime.now(timezone.utc).isoformat(),
            "fonte": f"{args.projeto}.{args.dataset}.{args.tabela}",
            "hoje": "2026-09-21",
            "total_clientes": len(todos_clientes),
            "origem": "BigQuery extrato_sintetico + personas de teste",
        },
        "clientes": todos_clientes,
    }

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Sucesso! %d clientes gravados em %s", len(todos_clientes), SAIDA)


if __name__ == "__main__":
    main()
