"""Script para criar dataset/tabela e carregar os clientes no BigQuery.

Uso:
    uv run python scripts/carregar_bigquery.py [--projeto SEU_PROJETO] [--dataset copiloto_fatura]
"""

import argparse
import json
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from proativo.gcp_adapters import exportar_para_bigquery


def main():
    parser = argparse.ArgumentParser(description="Carrega clientes sintéticos no BigQuery.")
    parser.add_argument("--projeto", default=os.getenv("GOOGLE_CLOUD_PROJECT"), help="ID do projeto GCP")
    parser.add_argument("--dataset", default="copiloto_fatura", help="Nome do dataset no BigQuery")
    parser.add_argument("--tabela", default="clientes", help="Nome da tabela no BigQuery")
    args = parser.parse_args()

    if not args.projeto:
        print("Erro: informe --projeto ou configure GOOGLE_CLOUD_PROJECT.")
        sys.exit(1)

    caminho_dados = RAIZ / "data" / "clientes.json"
    if not caminho_dados.exists():
        from data.gerar_dataset import main as gerar
        gerar()

    clientes = json.loads(caminho_dados.read_text(encoding="utf-8"))["clientes"]
    print(f"Carregando {len(clientes)} clientes em {args.projeto}.{args.dataset}.{args.tabela}...")

    sucesso = exportar_para_bigquery(
        clientes,
        project_id=args.projeto,
        dataset_id=args.dataset,
        table_id=args.tabela,
    )

    if sucesso:
        print("Carga concluída com sucesso no BigQuery!")
    else:
        print("Erro na carga do BigQuery.")
        sys.exit(1)


if __name__ == "__main__":
    main()
