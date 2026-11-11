# Single container: FastAPI serves the API and the built React app on one port.
# Slim build for free hosts (Render free = 512 MB): embeddings come from Pinecone's
# hosted models, so there is no torch or local model in the image.

FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build


FROM python:3.15-slim

# git is needed to clone repositories during ingestion
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

# Run as an unprivileged user
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    STATIC_DIR=/home/user/app/static \
    DATA_DIR=/home/user/app/data \
    EMBEDDING_PROVIDER=pinecone \
    CLIENT_IP_HEADER=true-client-ip \
    PORT=10000
WORKDIR $HOME/app

COPY --chown=user backend/requirements.txt .
RUN pip install --user -r requirements.txt

COPY --chown=user backend/alembic.ini ./
COPY --chown=user backend/migrations ./migrations
COPY --chown=user backend/app ./app
COPY --chown=user backend/ingestion ./ingestion
COPY --chown=user backend/storage ./storage
COPY --chown=user backend/retrieval ./retrieval
COPY --chown=user --from=web /web/dist ./static
RUN mkdir -p data

EXPOSE 10000
# One worker: ingest jobs and the ingest semaphore live in-process.
# No --proxy-headers: X-Forwarded-For can be set by the visitor, and Render's proxy keeps what they sent.
# The visitor's address comes from CLIENT_IP_HEADER instead, which Render's Cloudflare edge sets itself.
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
