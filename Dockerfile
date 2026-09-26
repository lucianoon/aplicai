FROM python:3.12-slim

# Instala ferramentas essenciais
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Instala uv diretamente
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Otimização de camadas de cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copia todo o código-fonte
COPY . .

# Pré-gera o dataset sintético na imagem
RUN uv run python -m data.gerar_dataset

ENV PYTHONUNBUFFERED=1
ENV PYTHONUTF8=1
ENV PORT=8080

EXPOSE 8080

CMD ["uv", "run", "python", "-m", "web.servidor"]
