#!/usr/bin/env bash
set -e

# Criação de recursos auxiliares no GCP (Pub/Sub e BigQuery)

PROJETO="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGIAO="${GOOGLE_CLOUD_LOCATION:-us-central1}"
TOPICO="copiloto-gatilhos"
DATASET="copiloto_fatura"

if [ -z "$PROJETO" ]; then
    echo "Erro: defina GOOGLE_CLOUD_PROJECT ou configure 'gcloud config set project <ID>'."
    exit 1
fi

echo "=========================================================="
echo "Criando recursos auxiliares GCP no projeto: $PROJETO"
echo "=========================================================="

echo "1. Criando Tópico Pub/Sub: $TOPICO..."
gcloud pubsub topics describe "$TOPICO" --project "$PROJETO" >/dev/null 2>&1 || \
    gcloud pubsub topics create "$TOPICO" --project "$PROJETO"

echo "2. Criando Dataset BigQuery: $DATASET..."
bq --location="$REGIAO" show "$PROJETO:$DATASET" >/dev/null 2>&1 || \
    bq --location="$REGIAO" mk --dataset "$PROJETO:$DATASET"

echo "3. Criando Tabela BigQuery: clientes..."
bq show "$PROJETO:$DATASET.clientes" >/dev/null 2>&1 || \
    bq mk --table "$PROJETO:$DATASET.clientes" cliente_id:STRING,dados_json:STRING

echo "4. Provisionando Secret no Google Cloud Secret Manager..."
gcloud services enable secretmanager.googleapis.com --project "$PROJETO"

if ! gcloud secrets describe copiloto-auth-secret --project "$PROJETO" >/dev/null 2>&1; then
    CHAVE_HMAC=$(openssl rand -hex 32)
    echo -n "$CHAVE_HMAC" | gcloud secrets create copiloto-auth-secret \
        --data-file=- \
        --replication-policy="automatic" \
        --project "$PROJETO"
    echo "Segredo copiloto-auth-secret criado com sucesso."
else
    echo "Segredo copiloto-auth-secret já existe."
fi

# Concede permissão de leitura para a Service Account padrão do Cloud Run
PROJECT_NUMBER=$(gcloud projects describe "$PROJETO" --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding copiloto-auth-secret \
    --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" \
    --project "$PROJETO" >/dev/null

echo "=========================================================="
echo "Recursos provisionados com sucesso!"
echo "- Pub/Sub: $TOPICO"
echo "- BigQuery: $DATASET.clientes"
echo "- Secret Manager: copiloto-auth-secret"
echo ""
echo "Para carregar os clientes no BigQuery, execute:"
echo "uv run python scripts/carregar_bigquery.py --projeto $PROJETO"
echo "=========================================================="
