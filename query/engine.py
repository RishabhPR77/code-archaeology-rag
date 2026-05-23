# query/engine.py
import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from storage.vector_store import VectorStore

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def build_prompt(question: str, chunks: list[dict]) -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        block = f"""
--- Source {i} (similarity: {chunk['score']}) ---
Author: {meta['author']}
Date: {meta['timestamp']}
Files: {meta['files']}
Has PR: {meta['has_pr']}

{chunk['text'][:1500]}
""".strip()
        context_blocks.append(block)

    context = "\n\n".join(context_blocks)
    return f"""You are Code Archaeologist — an expert at explaining why code changes were made.

Answer using ONLY the commits provided. If not enough information exists, say so clearly.
Always mention which commit your answer is based on (author + files).
Be specific and technical.

QUESTION:
{question}

RETRIEVED COMMITS:
{context}

ANSWER:"""


def _is_pr_listing_question(question: str) -> bool:
    """Detect if user is asking to list/count all PRs."""
    q = question.lower()
    return any(w in q for w in ["all pull request", "all pr", "list pull", "list pr",
                                  "how many pr", "how many pull", "closed pull", "closed pr",
                                  "all closed", "every pull", "every pr"])


def ask(question: str, top_k: int = 8,
        filters: dict = None,
        collection_name: str = "commit_chunks",
        mode: str = "Detailed") -> dict:

    # For PR listing questions — fetch ALL PR-linked commits from Pinecone
    if _is_pr_listing_question(question):
        store  = VectorStore(collection_name=collection_name)
        chunks = store.search(question, top_k=100, filters={"has_pr": True})
    else:
        store  = VectorStore(collection_name=collection_name)
        chunks = store.search(question, top_k=top_k, filters=filters)

    if not chunks:
        return {
            "question": question,
            "answer":   "No relevant commits found.",
            "sources":  []
        }

    prompt = build_prompt(question, chunks)

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You are Code Archaeologist, an expert at explaining why code changes were made."
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=1000,
    )

    return {
        "question": question,
        "answer":   response.choices[0].message.content.strip(),
        "sources":  [
            {
                "author":    c["metadata"]["author"],
                "timestamp": c["metadata"]["timestamp"],
                "files":     c["metadata"]["files"],
                "score":     c["score"],
                "has_pr":    c["metadata"]["has_pr"],
            }
            for c in chunks
        ]
    }


def timeline_ask(filename: str,
                 chunks_path: str = "./data/raw/chunks.json") -> dict:
    import json
    from retrieval.graph import CommitGraph

    graph = CommitGraph(chunks_path=chunks_path)
    timeline = graph.file_timeline(filename)

    if not timeline:
        return {
            "file":     filename,
            "answer":   f"No commits found touching {filename}",
            "timeline": []
        }

    timeline_text = ""
    for i, entry in enumerate(timeline, 1):
        timeline_text += f"""
[{i}] {entry['timestamp'][:10]} — {entry['author']}
     {entry['message'][:120]}
""".strip() + "\n\n"

    prompt = f"""You are Code Archaeologist. Summarize how '{filename}' evolved 
over time based on these commits. What changed, in what order, 
what themes or patterns do you see?

TIMELINE:
{timeline_text}

SUMMARY:"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=1000,
    )

    return {
        "file":     filename,
        "answer":   response.choices[0].message.content.strip(),
        "timeline": timeline
    }