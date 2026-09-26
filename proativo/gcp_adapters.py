"""Adaptadores para Google Cloud Pub/Sub e BigQuery (Gatilho Proativo e Dados).

Permite:
1. Publicar gatilhos proativos identificados na esteira do Google Cloud Pub/Sub
   para acionamento multicanal (WhatsApp, Push Notification, SMS, e-mail).
2. Consultar saldos, faturas e fluxo de caixa projetado diretamente no Google Cloud BigQuery
   quando COPILOTO_USE_BIGQUERY=1.
3. Exportar a base sintética local para o BigQuery em ambientes de desenvolvimento ou staging.

Mantém total compatibilidade e fallback gracioso para execução local e testes rápidos.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def pubsub_ativo() -> bool:
    """Verifica se o envio para Pub/Sub está configurado."""
    return bool(os.getenv("COPILOTO_PUBSUB_TOPIC"))


def bigquery_ativo() -> bool:
    """Verifica se a leitura via BigQuery está configurada."""
    return os.getenv("COPILOTO_USE_BIGQUERY", "0").strip() in {"1", "true", "True"}


def publicar_gatilhos_pubsub(
    gatilhos: list[dict[str, Any]],
    project_id: str | None = None,
    topic_id: str | None = None,
) -> int:
    """Publica a lista de gatilhos proativos identificados no tópico Pub/Sub.

    Cada mensagem contém o JSON completo do gatilho e atributos para roteamento
    (cliente_id, prioridade, canal).

    Retorna o número de mensagens publicadas com sucesso.
    """
    topico = topic_id or os.getenv("COPILOTO_PUBSUB_TOPIC")
    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")

    if not topico:
        logger.debug("Pub/Sub desativado (COPILOTO_PUBSUB_TOPIC não definido).")
        return 0

    try:
        from google.cloud import pubsub_v1

        publisher = pubsub_v1.PublisherClient()
        if "/" not in topico and projeto:
            topic_path = publisher.topic_path(projeto, topico)
        else:
            topic_path = topico

        publicados = 0
        for g in gatilhos:
            data = json.dumps(g, ensure_ascii=False).encode("utf-8")
            future = publisher.publish(
                topic_path,
                data=data,
                cliente_id=str(g.get("cliente_id", "")),
                prioridade=str(g.get("prioridade", "3")),
                canal=str(g.get("canal", "app")),
            )
            future.result(timeout=10)
            publicados += 1

        logger.info("Publicados %d gatilhos no Pub/Sub: %s", publicados, topic_path)
        return publicados
    except Exception as exc:
        logger.warning("Falha ao publicar no Pub/Sub: %s", exc)
        return 0


def obter_extrato_bigquery(
    cliente_id: str,
    project_id: str | None = None,
    dataset_id: str = "hackathon_dados",
    table_id: str = "extrato_sintetico",
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Busca as transações mais recentes de um cliente diretamente no BigQuery."""
    if not bigquery_ativo():
        return []

    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "batalha-time-09-nciv")
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=projeto)
        query = f"""
            SELECT 
                anomesdia,
                tipo,
                descr,
                vlr,
                nom_cate_macro,
                nom_cate_micro,
                saldo_apos,
                parcela_atual,
                parcela_total
            FROM `{projeto}.{dataset_id}.{table_id}`
            WHERE LOWER(id_usuario) = LOWER(@cliente_id)
            ORDER BY anomesdia DESC
            LIMIT @limite
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cliente_id", "STRING", cliente_id),
                bigquery.ScalarQueryParameter("limite", "INT64", limite),
            ]
        )
        query_job = client.query(query, job_config=job_config)
        return [dict(row.items()) for row in query_job]
    except Exception as exc:
        logger.warning("Erro ao buscar extrato no BigQuery para cliente %s: %s", cliente_id, exc)
        return []


def obter_kpis_globais_bigquery(
    project_id: str | None = None,
    dataset_id: str = "hackathon_dados",
    table_id: str = "extrato_sintetico",
) -> dict[str, Any] | None:
    """Calcula os KPIs agregados de toda a base de clientes no BigQuery."""
    if not bigquery_ativo():
        return None

    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", "batalha-time-09-nciv")
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=projeto)
        query = f"""
            SELECT
                COUNT(*) as total_transacoes,
                COUNT(DISTINCT id_usuario) as total_usuarios,
                ROUND(SUM(IF(tipo = 'E', vlr, 0)), 2) as volume_entradas,
                ROUND(SUM(IF(tipo = 'S', vlr, 0)), 2) as volume_saidas,
                ROUND(AVG(IF(tipo = 'S', vlr, NULL)), 2) as ticket_medio_saida,
                COUNTIF(saldo_apos < 0) as transacoes_saldo_negativo,
                COUNT(DISTINCT IF(saldo_apos < 0, id_usuario, NULL)) as usuarios_saldo_negativo
            FROM `{projeto}.{dataset_id}.{table_id}`
        """
        job = client.query(query)
        rows = [dict(row.items()) for row in job]
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("Erro ao calcular KPIs no BigQuery: %s", exc)
        return None


def carregar_clientes_bigquery(
    project_id: str | None = None,
    dataset_id: str = "copiloto_fatura",
    table_id: str = "clientes",
) -> list[dict[str, Any]] | None:
    """Carrega dados consolidados de clientes do BigQuery.

    Suporta tanto a tabela legada de clientes (dados_json) quanto a tabela
    oficial da batalha hackathon_dados.extrato_sintetico.
    Retorna lista de dicionários ou None se desativado / erro.
    """
    if not bigquery_ativo():
        return None

    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not projeto:
        logger.warning("COPILOTO_USE_BIGQUERY=1, mas GOOGLE_CLOUD_PROJECT não configurado.")
        return None

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=projeto)

        if table_id == "extrato_sintetico" or dataset_id == "hackathon_dados":
            from scripts.carregar_dados_extrato_sintetico import carregar_clientes_do_bigquery
            return carregar_clientes_do_bigquery(
                project_id=projeto,
                dataset_id=dataset_id,
                table_id=table_id,
            )

        query = f"""
            SELECT cliente_id, dados_json
            FROM `{projeto}.{dataset_id}.{table_id}`
        """
        query_job = client.query(query)
        resultados = []
        for row in query_job:
            dados = json.loads(row["dados_json"]) if isinstance(row["dados_json"], str) else row["dados_json"]
            resultados.append(dados)
        return resultados
    except Exception as exc:
        logger.warning("Falha ao consultar BigQuery: %s. Utilizando fallback local.", exc)
        return None


def exportar_para_bigquery(
    clientes: list[dict[str, Any]],
    project_id: str | None = None,
    dataset_id: str = "copiloto_fatura",
    table_id: str = "clientes",
) -> bool:
    """Exporta a lista de clientes para uma tabela do BigQuery."""
    projeto = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
    if not projeto:
        logger.error("GOOGLE_CLOUD_PROJECT não configurado para exportação ao BigQuery.")
        return False

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=projeto)
        table_ref = f"{projeto}.{dataset_id}.{table_id}"

        rows_to_insert = [
            {
                "cliente_id": c.get("id") or c.get("cliente_id"),
                "dados_json": json.dumps(c, ensure_ascii=False),
            }
            for c in clientes
        ]

        errors = client.insert_rows_json(table_ref, rows_to_insert)
        if errors:
            logger.error("Erros ao inserir no BigQuery: %s", errors)
            return False

        logger.info("Exportados com sucesso %d registros para %s", len(rows_to_insert), table_ref)
        return True
    except Exception as exc:
        logger.error("Erro na exportação para o BigQuery: %s", exc)
        return False
