FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

# git is needed to clone repositories during ingestion
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch keeps the image ~2GB smaller than the default CUDA build
COPY requirements.txt .
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch==2.9.1" \
    && pip install -r requirements.txt

# Bake the embedding model into the image so the first ingest doesn't download it
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY app ./app
COPY ingestion ./ingestion
COPY storage ./storage
COPY retrieval ./retrieval

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data && chown -R appuser /app/data
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"

# One worker: ingest jobs, the ingest semaphore and the login limiter live in-process
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
