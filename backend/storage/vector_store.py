# storage/vector_store.py
import json
import threading
import time
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.config import get_settings

# Local embeddings: BGE-small in-process (needs torch + sentence-transformers)
EMBEDDING_DIM  = 384
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
# BGE query prefix - boosts retrieval accuracy for question-type queries
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# Hosted embeddings: Pinecone Inference (llama-text-embed-v2 takes 2048-token inputs,
# up to 96 per request, and truncates the end of longer ones)
HOSTED_DIM = 1024
HOSTED_BATCH = 48
HOSTED_RETRIES = 6

# Pinecone allows 40KB of metadata per vector; this keeps most diffs within reach of the LLM
METADATA_TEXT_CHARS = 4000

_model = None
_model_lock = threading.Lock()
_pc = None
_pc_lock = threading.Lock()


def _hosted() -> bool:
    return get_settings().embedding_provider == "pinecone"


def embedding_dim() -> int:
    return HOSTED_DIM if _hosted() else EMBEDDING_DIM


def _get_model():
    # Loaded on first use so the API starts fast; ~130MB, cached by sentence-transformers
    global _model
    with _model_lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer(EMBEDDING_MODEL)
        return _model


def _pinecone():
    global _pc
    with _pc_lock:
        if _pc is None:
            from pinecone import Pinecone
            _pc = Pinecone(api_key=get_settings().pinecone_api_key)
        return _pc


def _hosted_embed(texts: list[str], input_type: str) -> list:
    from pinecone.exceptions import PineconeApiException
    for attempt in range(HOSTED_RETRIES):
        try:
            res = _pinecone().inference.embed(
                model=get_settings().embedding_model,
                inputs=texts,
                parameters={"input_type": input_type, "truncate": "END", "dimension": HOSTED_DIM},
            )
            return [list(e["values"]) for e in res]
        except PineconeApiException as e:
            # Starter plan has a tokens-per-minute cap; back off and retry
            if getattr(e, "status", None) != 429 or attempt == HOSTED_RETRIES - 1:
                raise
            time.sleep(min(60, 5 * 2 ** attempt))


def _embed_query(text: str) -> list:
    if _hosted():
        return _hosted_embed([text[:8000]], "query")[0]
    return _get_model().encode(
        BGE_QUERY_PREFIX + text[:512],
        normalize_embeddings=True
    ).tolist()


def _embed_docs(texts: list[str]) -> list:
    if _hosted():
        out = []
        for i in range(0, len(texts), HOSTED_BATCH):
            out.extend(_hosted_embed(texts[i:i + HOSTED_BATCH], "passage"))
        return out
    return _get_model().encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32
    ).tolist()


# ── Backends ───────────────────────────────────────────────────────
class _PineconeBackend:
    def __init__(self, index_name: str):
        from pinecone import ServerlessSpec
        pc = _pinecone()
        dim = embedding_dim()
        if index_name not in [i.name for i in pc.list_indexes()]:
            pc.create_index(
                name=index_name,
                dimension=dim,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
            while not pc.describe_index(index_name).status["ready"]:
                time.sleep(1)
        elif (existing := pc.describe_index(index_name).dimension) != dim:
            # Vectors from different embedding models can't share an index
            raise RuntimeError(
                f"Pinecone index '{index_name}' holds {existing}-dim vectors but the "
                f"'{get_settings().embedding_provider}' embeddings are {dim}-dim. "
                "Set PINECONE_INDEX to a new index name.")
        self.index = pc.Index(index_name)

    def existing_ids(self, ids: list[str], namespace: str) -> set[str]:
        found = set()
        for i in range(0, len(ids), 1000):
            resp = self.index.fetch(ids=ids[i:i+1000], namespace=namespace)
            found.update(resp.vectors.keys())
        return found

    def upsert(self, vectors: list[dict], namespace: str):
        self.index.upsert(vectors=vectors, namespace=namespace)

    def query(self, vector: list, top_k: int, namespace: str, flt: dict | None) -> list[tuple[float, dict]]:
        kwargs = {"vector": vector, "top_k": top_k, "namespace": namespace, "include_metadata": True}
        if flt:
            kwargs["filter"] = {k: {"$eq": v} for k, v in flt.items()}
        return [(m.score, dict(m.metadata or {})) for m in self.index.query(**kwargs).matches]

    def delete_namespace(self, namespace: str):
        from pinecone.exceptions import NotFoundException
        try:
            self.index.delete(delete_all=True, namespace=namespace)
        except NotFoundException:
            pass  # already gone


class _LocalBackend:
    """File-backed cosine search for local dev and tests — no Pinecone key needed."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, namespace: str) -> Path:
        return self.root / f"{namespace}.json"

    def _load(self, namespace: str) -> dict:
        p = self._path(namespace)
        return json.loads(p.read_text()) if p.exists() else {}

    def existing_ids(self, ids: list[str], namespace: str) -> set[str]:
        return set(ids) & set(self._load(namespace))

    def upsert(self, vectors: list[dict], namespace: str):
        with self._lock:
            data = self._load(namespace)
            for v in vectors:
                data[v["id"]] = {"values": v["values"], "metadata": v["metadata"]}
            self._path(namespace).write_text(json.dumps(data))

    def query(self, vector: list, top_k: int, namespace: str, flt: dict | None) -> list[tuple[float, dict]]:
        scored = []
        for item in self._load(namespace).values():
            meta = item["metadata"]
            if flt and any(meta.get(k) != v for k, v in flt.items()):
                continue
            # Vectors are normalised, so the dot product is the cosine similarity
            scored.append((sum(a * b for a, b in zip(vector, item["values"])), meta))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]

    def delete_namespace(self, namespace: str):
        self._path(namespace).unlink(missing_ok=True)


_backend = None
_backend_lock = threading.Lock()


def _get_backend():
    global _backend
    with _backend_lock:
        if _backend is None:
            settings = get_settings()
            if settings.pinecone_api_key:
                _backend = _PineconeBackend(settings.pinecone_index)
            else:
                _backend = _LocalBackend(settings.data_dir / "vectors")
        return _backend


class VectorStore:
    def __init__(self, namespace: str):
        self.namespace = namespace.replace("/", "_").replace("-", "_")
        self.backend   = _get_backend()

    def ingest(self, chunks: list[dict], batch_size: int = 50, overwrite: bool = False):
        # overwrite=True re-upserts existing ids, e.g. after chunks gain PR data
        existing_ids = set()
        if not overwrite:
            existing_ids = self.backend.existing_ids([c["id"] for c in chunks], self.namespace)

        new = [c for c in chunks if c["id"] not in existing_ids]
        for i in range(0, len(new), batch_size):
            batch  = new[i:i+batch_size]
            embeds = _embed_docs([c["text"] for c in batch])
            vectors = [
                {
                    "id":     chunk["id"],
                    "values": emb,
                    "metadata": {
                        "sha":       chunk["metadata"]["sha"],
                        "author":    chunk["metadata"]["author"],
                        "timestamp": chunk["metadata"]["timestamp"],
                        "files":     chunk["metadata"]["files"][:500],
                        "has_pr":    bool(chunk["metadata"]["has_pr"]),
                        "pr_number": chunk["metadata"].get("pr_number", 0),
                        "text":      chunk["text"][:METADATA_TEXT_CHARS],
                    }
                }
                for chunk, emb in zip(batch, embeds)
            ]
            self.backend.upsert(vectors, self.namespace)

    # Hybrid search (dense + BM25 rerank)
    def search(self, question: str, top_k: int = 5,
               filters: dict = None) -> list[dict]:
        """
        1. Dense retrieval (fetch top_k * 4 candidates)
        2. BM25 keyword re-rank on those candidates
        3. Combine: final_score = 0.6 * dense + 0.4 * bm25_normalised
        4. Return top_k
        """
        candidate_k = min(max(top_k * 4, 20), 200)
        candidates  = self.backend.query(_embed_query(question), candidate_k, self.namespace, filters)
        if not candidates:
            return []

        # Build BM25 on the candidate texts
        tokenised = [meta.get("text", "").lower().split() for _, meta in candidates]
        bm25      = BM25Okapi(tokenised)
        bm25_raw  = bm25.get_scores(question.lower().split())

        # Normalise BM25 scores to [0, 1]
        bm25_max  = max(bm25_raw) if max(bm25_raw) > 0 else 1
        bm25_norm = [s / bm25_max for s in bm25_raw]

        # Combine scores
        ALPHA = 0.6   # weight for dense; 0.4 for BM25
        combined = [(ALPHA * dense + (1 - ALPHA) * bm25_norm[i], meta)
                    for i, (dense, meta) in enumerate(candidates)]
        combined.sort(key=lambda x: x[0], reverse=True)

        return [
            {
                "text": meta.get("text", ""),
                "metadata": {
                    "sha":       meta.get("sha", ""),
                    "author":    meta.get("author", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "files":     meta.get("files", ""),
                    "has_pr":    meta.get("has_pr", False),
                    "pr_number": int(meta.get("pr_number", 0) or 0),
                },
                "score": round(score, 3),
            }
            for score, meta in combined[:top_k]
        ]

    def delete_namespace(self):
        self.backend.delete_namespace(self.namespace)
