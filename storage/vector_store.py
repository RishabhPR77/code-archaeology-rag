# storage/vector_store.py
import os
import time
import math
from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer
from rank_bm25 import BM25Okapi

# BGE-small: better semantic quality, same 384 dims as MiniLM → no index change
model = SentenceTransformer("BAAI/bge-small-en-v1.5")

PINECONE_INDEX = "code-archaeologist"
EMBEDDING_DIM  = 384
# BGE query prefix — boosts retrieval accuracy for question-type queries
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def _embed_query(text: str) -> list:
    return model.encode(
        BGE_QUERY_PREFIX + text[:512],
        normalize_embeddings=True
    ).tolist()

def _embed_docs(texts: list[str]) -> list:
    return model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32
    ).tolist()

def _get_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    if PINECONE_INDEX not in [i.name for i in pc.list_indexes()]:
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        while not pc.describe_index(PINECONE_INDEX).status["ready"]:
            time.sleep(1)
    return pc.Index(PINECONE_INDEX)


class VectorStore:
    def __init__(self, collection_name: str = "commit_chunks"):
        self.namespace = collection_name.replace("/", "_").replace("-", "_")
        self.index     = _get_index()

    # ── Ingest ─────────────────────────────────────────────────────
    def ingest(self, chunks: list[dict], batch_size: int = 50):
        all_ids = [c["id"] for c in chunks]
        existing_ids = set()
        for i in range(0, len(all_ids), 1000):
            resp = self.index.fetch(ids=all_ids[i:i+1000], namespace=self.namespace)
            existing_ids.update(resp.vectors.keys())

        new = [c for c in chunks if c["id"] not in existing_ids]
        if not new:
            print("All chunks already ingested, skipping.")
            return

        for i in range(0, len(new), batch_size):
            batch  = new[i:i+batch_size]
            texts  = [c["text"] for c in batch]
            embeds = _embed_docs(texts)

            vectors = []
            for chunk, emb in zip(batch, embeds):
                vectors.append({
                    "id":     chunk["id"],
                    "values": emb,
                    "metadata": {
                        "sha":       chunk["metadata"]["sha"],
                        "author":    chunk["metadata"]["author"],
                        "timestamp": chunk["metadata"]["timestamp"],
                        "files":     chunk["metadata"]["files"][:500],
                        "has_pr":    bool(chunk["metadata"]["has_pr"]),
                        "text":      chunk["text"][:1200],
                    }
                })

            self.index.upsert(vectors=vectors, namespace=self.namespace)
            print(f"  Batch {i//batch_size+1} done ({len(batch)} chunks)")

        ns = self.index.describe_index_stats().namespaces.get(self.namespace)
        print(f"Total in namespace '{self.namespace}': {ns.vector_count if ns else 0}")

    # ── Hybrid search (dense Pinecone + BM25 rerank) ───────────────
    def search(self, question: str, top_k: int = 5,
               filters: dict = None) -> list[dict]:
        """
        1. Dense retrieval from Pinecone (fetch top_k * 4 candidates)
        2. BM25 keyword re-rank on those candidates
        3. Combine: final_score = 0.6 * dense + 0.4 * bm25_normalised
        4. Return top_k
        """
        candidate_k = min(top_k * 4, 50)
        query_vec   = _embed_query(question)

        kwargs = {
            "vector":           query_vec,
            "top_k":            candidate_k,
            "namespace":        self.namespace,
            "include_metadata": True,
        }
        if filters:
            kwargs["filter"] = {k: {"$eq": v} for k, v in filters.items()}

        resp       = self.index.query(**kwargs)
        candidates = resp.matches

        if not candidates:
            return []

        # Build BM25 on the candidate texts
        texts     = [m.metadata.get("text", "") for m in candidates]
        tokenised = [t.lower().split() for t in texts]
        bm25      = BM25Okapi(tokenised)
        bm25_raw  = bm25.get_scores(question.lower().split())

        # Normalise BM25 scores to [0, 1]
        bm25_max = max(bm25_raw) if max(bm25_raw) > 0 else 1
        bm25_norm = [s / bm25_max for s in bm25_raw]

        # Combine scores
        ALPHA = 0.6   # weight for dense; 0.4 for BM25
        combined = []
        for i, match in enumerate(candidates):
            score = ALPHA * match.score + (1 - ALPHA) * bm25_norm[i]
            combined.append((score, match))

        combined.sort(key=lambda x: x[0], reverse=True)
        top = combined[:top_k]

        return [
            {
                "text": match.metadata.get("text", ""),
                "metadata": {
                    "sha":       match.metadata.get("sha", ""),
                    "author":    match.metadata.get("author", ""),
                    "timestamp": match.metadata.get("timestamp", ""),
                    "files":     match.metadata.get("files", ""),
                    "has_pr":    match.metadata.get("has_pr", False),
                },
                "score": round(score, 3),
            }
            for score, match in top
        ]

    def delete_namespace(self):
        self.index.delete(delete_all=True, namespace=self.namespace)

    @property
    def count(self):
        ns = self.index.describe_index_stats().namespaces.get(self.namespace)
        return ns.vector_count if ns else 0