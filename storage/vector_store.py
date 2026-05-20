# storage/vector_store.py
import os

from dotenv import load_dotenv
load_dotenv()

import time
import chromadb
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embedding(text: str) -> list:
    return model.encode(text[:512], normalize_embeddings=True).tolist()

class VectorStore:
    def __init__(self, collection_name: str = "commit_chunks"):
        self.client = chromadb.PersistentClient(
            path=os.getenv("CHROMA_PATH", "./data/chroma_db")
        )
        # Each repo gets its own collection
        safe_name = collection_name.replace("/", "_").replace("-", "_")
        self.collection = self.client.get_or_create_collection(
            name=safe_name,
            metadata={"hnsw:space": "cosine"}
        )

    def ingest(self, chunks: list[dict], batch_size: int = 50):
        existing = set(self.collection.get(include=[])["ids"])
        new = [c for c in chunks if c["id"] not in existing]

        if not new:
            print("All chunks already ingested, skipping.")
            return

        for i in range(0, len(new), batch_size):
            batch     = new[i:i+batch_size]
            docs      = [c["text"]     for c in batch]
            ids       = [c["id"]       for c in batch]
            metas     = [c["metadata"] for c in batch]

            embeddings = model.encode(
                docs,
                normalize_embeddings=True,
                show_progress_bar=False
            ).tolist()

            self.collection.upsert(
                ids=ids, documents=docs,
                embeddings=embeddings, metadatas=metas
            )
            print(f"  Batch {i//batch_size+1} done ({len(batch)} chunks)")

        print(f"Total in store: {self.collection.count()}")

    def search(self, question: str, top_k: int = 5,
               filters: dict = None) -> list[dict]:
        embedding = get_embedding(question)
        kwargs = {
            "query_embeddings": [embedding],
            "n_results":        top_k,
            "include":          ["documents", "metadatas", "distances"]
        }
        if filters:
            kwargs["where"] = filters

        raw = self.collection.query(**kwargs)
        return [
            {
                "text":     doc,
                "metadata": meta,
                "score":    round(1 - dist, 3)
            }
            for doc, meta, dist in zip(
                raw["documents"][0],
                raw["metadatas"][0],
                raw["distances"][0]
            )
        ]

    @property
    def count(self):
        return self.collection.count()