# storage/vector_store.py
import os
import time
from dotenv import load_dotenv
load_dotenv()

from pinecone import Pinecone, ServerlessSpec
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

PINECONE_INDEX  = "code-archaeologist"   # single index, repos = namespaces
EMBEDDING_DIM   = 384                    # all-MiniLM-L6-v2 output size

def _get_index():
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    if PINECONE_INDEX not in [i.name for i in pc.list_indexes()]:
        pc.create_index(
            name=PINECONE_INDEX,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
        # wait until ready
        while not pc.describe_index(PINECONE_INDEX).status["ready"]:
            time.sleep(1)
    return pc.Index(PINECONE_INDEX)

class VectorStore:
    def __init__(self, collection_name: str = "commit_chunks"):
        # Each repo is stored in its own namespace
        self.namespace = collection_name.replace("/", "_").replace("-", "_")
        self.index     = _get_index()

    def ingest(self, chunks: list[dict], batch_size: int = 50):
        # Check which IDs already exist
        existing_ids = set()
        all_ids = [c["id"] for c in chunks]
        # Pinecone fetch supports up to 1000 ids at a time
        for i in range(0, len(all_ids), 1000):
            batch_ids = all_ids[i:i+1000]
            resp = self.index.fetch(ids=batch_ids, namespace=self.namespace)
            existing_ids.update(resp.vectors.keys())

        new = [c for c in chunks if c["id"] not in existing_ids]
        if not new:
            print("All chunks already ingested, skipping.")
            return

        for i in range(0, len(new), batch_size):
            batch = new[i:i+batch_size]
            texts = [c["text"] for c in batch]
            embeddings = model.encode(
                texts, normalize_embeddings=True, show_progress_bar=False
            ).tolist()

            vectors = []
            for chunk, emb in zip(batch, embeddings):
                # Pinecone metadata values must be str/int/float/bool/list
                meta = {
                    "sha":       chunk["metadata"]["sha"],
                    "author":    chunk["metadata"]["author"],
                    "timestamp": chunk["metadata"]["timestamp"],
                    "files":     chunk["metadata"]["files"][:500],
                    "has_pr":    bool(chunk["metadata"]["has_pr"]),
                    "text":      chunk["text"][:1000],
                }
                vectors.append({
                    "id":     chunk["id"],
                    "values": emb,
                    "metadata": meta,
                })

            self.index.upsert(vectors=vectors, namespace=self.namespace)
            print(f"  Batch {i//batch_size+1} done ({len(batch)} chunks)")

        stats = self.index.describe_index_stats()
        ns    = stats.namespaces.get(self.namespace)
        print(f"Total in namespace '{self.namespace}': {ns.vector_count if ns else 0}")

    def search(self, question: str, top_k: int = 5,
               filters: dict = None) -> list[dict]:
        embedding = model.encode(
            question[:512], normalize_embeddings=True
        ).tolist()

        kwargs = {
            "vector":          embedding,
            "top_k":           top_k,
            "namespace":       self.namespace,
            "include_metadata": True,
        }
        # Map ChromaDB-style filter {"has_pr": True} → Pinecone filter
        if filters:
            pf = {}
            for k, v in filters.items():
                pf[k] = {"$eq": v}
            kwargs["filter"] = pf

        resp = self.index.query(**kwargs)

        return [
            {
                "text":     match.metadata.get("text", ""),
                "metadata": {
                    "sha":       match.metadata.get("sha", ""),
                    "author":    match.metadata.get("author", ""),
                    "timestamp": match.metadata.get("timestamp", ""),
                    "files":     match.metadata.get("files", ""),
                    "has_pr":    match.metadata.get("has_pr", False),
                },
                "score": round(match.score, 3),
            }
            for match in resp.matches
        ]

    def delete_namespace(self):
        """Delete all vectors for this repo namespace."""
        self.index.delete(delete_all=True, namespace=self.namespace)

    @property
    def count(self):
        stats = self.index.describe_index_stats()
        ns    = stats.namespaces.get(self.namespace)
        return ns.vector_count if ns else 0