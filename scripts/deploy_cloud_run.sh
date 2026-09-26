#!/usr/bin/env bash
set -e

# Deploy no Google Cloud Run
# Requisitos: gcloud CLI configurado e autenticado

PROJETO="${GOOGLE_CLOUD_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGIAO="${GOOGLE_CLOUD_LOCATION:-us-central1}"
SERVICO="copiloto-fatura"

if [ -z "$PROJETO" ]; then
    echo "Erro: defina GOOGLE_CLOUD_PROJECT ou configure 'gcloud config set project <ID>'."
    exit 1
fi

echo "=========================================================="
echo "Iniciando Deploy do Copiloto da Fatura no Google Cloud Run"
echo "Projeto : $PROJETO"
echo "Região  : $REGIAO"
echo "Serviço : $SERVICO"
echo "=========================================================="

echo "1. APIs do projeto já estão ativas..."

IMAGE_TAG="${REGIAO}-docker.pkg.dev/${PROJETO}/agentes/${SERVICO}:latest"

echo "2. Construindo e enviando container para Artifact Registry..."
docker build -t "$IMAGE_TAG" .
docker push "$IMAGE_TAG"

echo "3. Verificando segredos no Google Secret Manager..."
SECRETS_PARAM=""
if gcloud secrets describe copiloto-auth-secret --project "$PROJETO" >/dev/null 2>&1; then
    echo "Segredo copiloto-auth-secret detectado no Secret Manager. Injetando no Cloud Run..."
    SECRETS_PARAM="--set-secrets=COPILOTO_AUTH_SECRET=copiloto-auth-secret:latest"
else
    echo "Aviso: copiloto-auth-secret não encontrado no Secret Manager. O host gerará a chave dinamicamente."
fi

# Chave oficial provida pelo hackathon
GEMINI_KEY_VAL=""
if gcloud secrets describe gemini-api-key --project "$PROJETO" >/dev/null 2>&1; then
    echo "Chave gemini-api-key detectada no Secret Manager. Injetando no Cloud Run..."
    GEMINI_KEY_VAL=$(gcloud secrets versions access latest --secret="gemini-api-key" --project "$PROJETO" 2>/dev/null || true)
fi

ENV_VARS="GOOGLE_GENAI_USE_ENTERPRISE=0,GOOGLE_CLOUD_PROJECT=$PROJETO,GOOGLE_CLOUD_LOCATION=$REGIAO,PYTHONUTF8=1,COPILOTO_USE_BIGQUERY=1,BIGQUERY_DATASET=hackathon_dados,BIGQUERY_TABLE=extrato_sintetico,COPILOTO_MODEL=gemini-3.5-flash-lite,COPILOTO_THINKING=low"
if [ -n "$GEMINI_KEY_VAL" ]; then
    ENV_VARS="$ENV_VARS,GEMINI_API_KEY=$GEMINI_KEY_VAL"
fi

echo "4. Fazendo deploy no Cloud Run..."
gcloud run deploy "$SERVICO" \
    --image "$IMAGE_TAG" \
    --region "$REGIAO" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --set-env-vars "$ENV_VARS" \
    $SECRETS_PARAM \
    --memory 1Gi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 5 \
    --project "$PROJETO"

URL=$(gcloud run services describe "$SERVICO" --platform managed --region "$REGIAO" --project "$PROJETO" --format 'value(status.url)')

echo "=========================================================="
echo "Deploy finalizado com sucesso!"
echo "Acesse a aplicação em: $URL"
echo "=========================================================="
