# app/services/rag.py
"""Retrieval-augmented answers over commit history, provider-agnostic."""
import re
from collections.abc import Callable

from retrieval import analytics, suspects as suspect_ranking
from storage.vector_store import VectorStore

SYSTEM_PROMPT = """You are Code Archaeologist — an expert at explaining why code changes were made.

Answer using ONLY the commits provided. If they don't contain enough information, say so plainly.
Cite the commits you rely on by short SHA in backticks (for example `a1b2c3d`), and mention authors or files when useful.
Earlier messages in the conversation only tell you what the question refers to; every factual claim must still come from the retrieved commits.
Be specific and technical. Format the answer in Markdown."""

REWRITE_PROMPT = """You rewrite follow-up questions about a code repository's history into standalone questions.
Use the conversation to replace pronouns and vague references (it, that change, the bug, he) with the specific
commits, files, features or people they refer to. Keep the user's intent and keep it short.
If the question already stands on its own, return it unchanged.
Reply with only the rewritten question."""

SUSPECTS_PROMPT = """You help a developer find which commit most likely introduced a bug.
Use ONLY the commits provided. For each suspect, explain in two or three sentences how its change could cause
the reported problem, or say plainly that it probably didn't. Then name the most likely suspect and why.
These are suspects, not proof: finish with one concrete way to confirm, such as running git bisect between two
named commits or testing the commit just before the suspect.
Cite commits by short SHA in backticks. Format the answer in Markdown."""

# How much of the chat a follow-up sees: enough to resolve “it”, small enough to stay cheap
HISTORY_TURNS = 3
HISTORY_ANSWER_CHARS = 1500
REWRITE_ANSWER_CHARS = 600

MODE_INSTRUCTIONS = {
    "detailed": "",
    "summary":  "Answer in 2-3 sentences only.",
    "bullets":  "Answer as a concise bullet point list.",
}

PR_LISTING_TOP_K = 60

# (system, prompt) -> answer text
Generate = Callable[[str, str], str]
# (question, answer) pairs from the same chat, oldest first
History = list[tuple[str, str]]


def _is_pr_listing_question(question: str) -> bool:
    """Detect if user is asking to list/count all PRs."""
    q = question.lower()
    return any(w in q for w in ["all pull request", "all pr", "list pull", "list pr",
                                  "how many pr", "how many pull", "closed pull", "closed pr",
                                  "all closed", "every pull", "every pr"])


def _conversation(history: History, answer_chars: int) -> str:
    return "\n\n".join(f"Q: {q}\nA: {a[:answer_chars]}" for q, a in history)


def _clean_rewrite(text: str, fallback: str) -> str:
    """The first real line of the model's reply, without quotes or a label; the original question if empty."""
    for line in text.strip().splitlines():
        line = line.strip().strip('"“”').strip()
        line = re.sub(r"^(standalone|rewritten)?\s*question\s*:\s*", "", line, flags=re.IGNORECASE).strip()
        if line:
            return line[:500]
    return fallback


def standalone_question(question: str, history: History, generate: Generate) -> str:
    """Turn a follow-up like "who reviewed it?" into a question that can be searched on its own."""
    if not history:
        return question
    prompt = (f"CONVERSATION:\n{_conversation(history, REWRITE_ANSWER_CHARS)}\n\n"
              f"FOLLOW-UP QUESTION:\n{question}")
    return _clean_rewrite(generate(REWRITE_PROMPT, prompt), question)


def build_prompt(question: str, chunks: list[dict], mode: str, chars_per_chunk: int,
                 history: History = (), search_query: str | None = None) -> str:
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
    context = (f"CONVERSATION SO FAR (context only):\n{_conversation(history, HISTORY_ANSWER_CHARS)}\n\n"
               if history else "")
    searched = (f"(The history was searched for: {search_query})\n\n"
                if search_query and search_query != question else "")
    return (context + f"QUESTION:\n{question}\n\n" + searched
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


def ask(question: str, namespace: str, generate: Generate, mode: str = "detailed",
        only_pr: bool = False, top_k: int = 8, history: History | None = None) -> dict:
    history = (history or [])[-HISTORY_TURNS:]
    # Follow-ups are searched as standalone questions; the first question in a chat is used as-is
    query = standalone_question(question, history, generate)
    store = VectorStore(namespace)
    # For PR listing questions — pull many PR-linked commits, each trimmed
    if _is_pr_listing_question(query):
        chunks, per_chunk = store.search(query, top_k=PR_LISTING_TOP_K, filters={"has_pr": True}), 500
    else:
        chunks, per_chunk = store.search(query, top_k=top_k,
                                         filters={"has_pr": True} if only_pr else None), 2500

    if not chunks:
        return {"answer": "No relevant commits were found for this question.", "sources": [], "search_query": query}

    answer = generate(SYSTEM_PROMPT, build_prompt(question, chunks, mode, per_chunk, history, query))
    return {"answer": answer, "sources": [_source(c) for c in chunks], "search_query": query}


def timeline(filename: str, chunks: list[dict], generate: Generate, match: str = "contains") -> dict:
    entries = analytics.file_timeline(chunks, filename, match)
    if not entries:
        return {"answer": None, "entries": []}

    lines = [f"[{i}] {e['timestamp'][:10]} · `{e['sha']}` · {e['author']} · {e['type']}\n    {e['message'][:160]}"
             for i, e in enumerate(entries, 1)]
    subject = {"exact": f"the file '{filename}'",
               "folder": f"the files in the folder '{filename.strip('/')}'"}.get(match, f"files matching '{filename}'")
    prompt = (f"Summarize how {subject} evolved over time based on these commits.\n"
              "Cover the major phases of change in order, who drove them, and any recurring themes "
              "(bug clusters, refactors, feature growth). Cite commits by short SHA.\n\n"
              "TIMELINE:\n" + "\n".join(lines))
    return {"answer": generate(SYSTEM_PROMPT, prompt), "entries": entries}


def find_suspects(description: str, namespace: str, chunks: list[dict], origins: list[dict] | None,
                  since: str | None, generate: Generate | None) -> dict:
    """Rank likely culprit commits for a bug report; the model explains them when one is connected."""
    hits = VectorStore(namespace).search(description, top_k=30)
    scores = {h["metadata"]["sha"]: h["score"] for h in hits}
    found, mentioned = suspect_ranking.rank_suspects(description, chunks, scores,
                                                     suspect_ranking.origin_counts(origins), since)
    answer = None
    if found and generate:
        texts = {c["metadata"]["sha"]: c["text"] for c in chunks}
        blocks = [f"--- Suspect {i} · commit {s['sha']} (score {s['score']}) ---\n"
                  f"Flagged because: {'; '.join(s['reasons'])}\n\n{texts.get(s['sha'], '')[:2500]}"
                  for i, s in enumerate(found, 1)]
        prompt = (f"BUG REPORT:\n{description}\n\n"
                  + (f"Only commits on or after {since} were considered.\n\n" if since else "")
                  + "SUSPECT COMMITS:\n" + "\n\n".join(blocks))
        answer = generate(SUSPECTS_PROMPT, prompt)
    return {"suspects": found, "mentioned_files": mentioned, "answer": answer}

