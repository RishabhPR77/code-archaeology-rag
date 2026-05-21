import os
from dotenv import load_dotenv
load_dotenv()

from groq import Groq
from storage.vector_store import VectorStore

groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))


def build_prompt(question: str, chunks: list[dict], mode_instruction: str = "") -> str:
    context_blocks = []
    for i, chunk in enumerate(chunks, 1):
        meta  = chunk["metadata"]
        score = chunk["score"]
        has_pr = "Yes" if meta["has_pr"] else "No"
        block = (
            f"--- Commit {i} (relevance: {score}) ---\n"
            f"Author : {meta['author']}\n"
            f"Date   : {meta['timestamp'][:10]}\n"
            f"Files  : {meta['files']}\n"
            f"Has PR : {has_pr}\n\n"
            f"{chunk['text'][:1800]}"
        )
        context_blocks.append(block)

    context = "\n\n".join(context_blocks)

    return f"""You are Code Archaeologist — an expert software historian who explains \
why code changes were made, not just what changed.

Rules:
- Answer using ONLY the commits provided below.
- Always cite which commit(s) your answer draws from (author + date + files).
- Be specific and technical — name functions, modules, patterns when visible.
- If the commits don't contain enough information, say so clearly.
- Do not hallucinate details not present in the commits.
{("- " + mode_instruction) if mode_instruction else ""}

QUESTION:
{question}

COMMITS:
{context}

ANSWER:"""


def ask(question: str, top_k: int = 8,
        filters: dict = None,
        collection_name: str = "commit_chunks",
        mode: str = "Detailed") -> dict:

    store  = VectorStore(collection_name=collection_name)
    chunks = store.search(question, top_k=top_k, filters=filters)

    if not chunks:
        return {"question": question, "answer": "No relevant commits found.", "sources": []}

    mode_instruction = {
        "Quick summary":  "Answer in 2-3 sentences only. Be concise.",
        "Bullet points":  "Answer as a bullet point list. Each point = one key insight.",
        "Detailed":       "",
    }.get(mode, "")

    prompt = build_prompt(question, chunks, mode_instruction)

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role":    "system",
                "content": (
                    "You are Code Archaeologist — a precise, technical expert who explains "
                    "the history and reasoning behind code changes. You cite specific commits, "
                    "authors, and files in your answers."
                )
            },
            {"role": "user", "content": prompt}
        ],
        temperature=0.15,
        max_tokens=1200,
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

    graph    = CommitGraph(chunks_path=chunks_path)
    timeline = graph.file_timeline(filename)

    if not timeline:
        return {"file": filename, "answer": f"No commits found touching {filename}", "timeline": []}

    timeline_text = "\n".join(
        f"[{i}] {e['timestamp'][:10]}  {e['author']:<20}  {e['message'][:100]}"
        for i, e in enumerate(timeline, 1)
    )

    prompt = f"""You are Code Archaeologist. Based on the commit timeline below, explain how \
'{filename}' evolved over time.

Cover:
1. What the file started as and what it became
2. The major phases of change (e.g., initial build → bug fixes → refactor)
3. Which authors drove which changes and why
4. Any recurring themes (e.g., repeated bug fixes in the same area = instability)

TIMELINE ({len(timeline)} commits):
{timeline_text}

ANALYSIS:"""

    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1200,
    )

    return {
        "file":     filename,
        "answer":   response.choices[0].message.content.strip(),
        "timeline": timeline
    }