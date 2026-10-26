# Single container: FastAPI serves the API and the built React app on one port.
# Used for Hugging Face Spaces (port 7860, runs as UID 1000) and any one-service host.
# The multi-service stack (Postgres + nginx) lives in docker-compose.yml.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.12-slim

# git is needed to clone repositories during ingestion
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface \
    STATIC_DIR=/home/user/app/static \
    DATA_DIR=/home/user/app/data \
    PORT=7860
WORKDIR $HOME/app

# CPU-only torch keeps the image ~2GB smaller than the default CUDA build
COPY --chown=user backend/requirements.txt .
RUN pip install --user --index-url https://download.pytorch.org/whl/cpu "torch==2.9.1" \
    && pip install --user -r requirements.txt

# Bake the embedding model in so the first ingest doesn't download it
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY --chown=user backend/app ./app
COPY --chown=user backend/ingestion ./ingestion
COPY --chown=user backend/storage ./storage
COPY --chown=user backend/retrieval ./retrieval
COPY --chown=user --from=web /web/dist ./static
RUN mkdir -p data

EXPOSE 7860
# One worker: ingest jobs, the ingest semaphore and the login limiter live in-process
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips "*"
