# app/services/rag.py
"""Retrieval-augmented answers over commit history, provider-agnostic."""
from collections.abc import Callable

from retrieval import analytics
from storage.vector_store import VectorStore

SYSTEM_PROMPT = """You are Code Archaeologist — an expert at explaining why code changes were made.

Answer using ONLY the commits provided. If they don't contain enough information, say so plainly.
Cite the commits you rely on by short SHA in backticks (for example `a1b2c3d`), and mention authors or files when useful.
Be specific and technical. Format the answer in Markdown."""

MODE_INSTRUCTIONS = {
    "detailed": "",
    "summary":  "Answer in 2-3 sentences only.",
    "bullets":  "Answer as a concise bullet point list.",
}

PR_LISTING_TOP_K = 60

# (system, prompt) -> answer text
Generate = Callable[[str, str], str]


def _is_pr_listing_question(question: str) -> bool:
    """Detect if user is asking to list/count all PRs."""
    q = question.lower()
    return any(w in q for w in ["all pull request", "all pr", "list pull", "list pr",
                                  "how many pr", "how many pull", "closed pull", "closed pr",
                                  "all closed", "every pull", "every pr"])


def build_prompt(question: str, chunks: list[dict], mode: str, chars_per_chunk: int) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        blocks.append(f"""--- Source {i} · commit {meta['sha']} (relevance {chunk['score']}) ---
Author: {meta['author']}
Date: {meta['timestamp'][:10]}
Files: {meta['files']}
Has PR: {meta['has_pr']}

{chunk['text'][:chars_per_chunk]}""")
    instruction = MODE_INSTRUCTIONS.get(mode, "")
    return (f"QUESTION:\n{question}\n\n"
            + (f"FORMAT: {instruction}\n\n" if instruction else "")
            + "RETRIEVED COMMITS:\n" + "\n\n".join(blocks))


def _source(chunk: dict) -> dict:
    meta = chunk["metadata"]
    first = chunk["text"].split("\n")[0]
    return {
        "sha":       meta["sha"],
        "author":    meta["author"],
        "timestamp": meta["timestamp"],
        "files":     [f.strip() for f in meta["files"].split(", ") if f.strip()],
        "score":     chunk["score"],
        "has_pr":    meta["has_pr"],
        "pr_number": meta.get("pr_number") or None,
        "message":   first.split("]: ", 1)[1] if "]: " in first else first,
    }


def ask(question: str, namespace: str, generate: Generate,
        mode: str = "detailed", only_pr: bool = False, top_k: int = 8) -> dict:
    store = VectorStore(namespace)
    # For PR listing questions — pull many PR-linked commits, each trimmed
    if _is_pr_listing_question(question):
        chunks, per_chunk = store.search(question, top_k=PR_LISTING_TOP_K, filters={"has_pr": True}), 500
    else:
        chunks, per_chunk = store.search(question, top_k=top_k,
                                         filters={"has_pr": True} if only_pr else None), 2500

    if not chunks:
        return {"answer": "No relevant commits were found for this question.", "sources": []}

    answer = generate(SYSTEM_PROMPT, build_prompt(question, chunks, mode, per_chunk))
    return {"answer": answer, "sources": [_source(c) for c in chunks]}


def timeline(filename: str, chunks: list[dict], generate: Generate) -> dict:
    entries = analytics.file_timeline(chunks, filename)
    if not entries:
        return {"answer": None, "entries": []}

    lines = [f"[{i}] {e['timestamp'][:10]} · `{e['sha']}` · {e['author']} · {e['type']}\n    {e['message'][:160]}"
             for i, e in enumerate(entries, 1)]
    prompt = (f"Summarize how files matching '{filename}' evolved over time based on these commits.\n"
              "Cover the major phases of change in order, who drove them, and any recurring themes "
              "(bug clusters, refactors, feature growth). Cite commits by short SHA.\n\n"
              "TIMELINE:\n" + "\n".join(lines))
    return {"answer": generate(SYSTEM_PROMPT, prompt), "entries": entries}
