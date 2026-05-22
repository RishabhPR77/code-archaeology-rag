# Code Archaeologist

**Ask why any code was written - and get a grounded answer from the actual Git history.**

🔗 [Live Demo](https://code-archaeology-rag.streamlit.app) &nbsp;·&nbsp; [GitHub](https://github.com/RishabhPR77/code-archaeology-rag)

---

## The Problem

Every developer has opened an old file and thought - *why is this written like this?*

The person who wrote it may have left. There is no documentation. The commit message says "fix bug." The knowledge of why a decision was made is buried in Git history, PR descriptions, and review comments - technically accessible but practically unreachable.

---

## What This Does

Code Archaeologist is a RAG system that answers "why" questions about any GitHub repository.

Paste a public GitHub URL. The system ingests the commit history, embeds it into a vector database, and builds a knowledge graph. Then ask anything in plain English:

- *"Why was the authentication system refactored?"*
- *"What bugs were fixed in the session module?"*
- *"Which files are most tightly coupled?"*
- *"How did sessions.py evolve over the last two years?"*

It retrieves real commits as evidence and uses LLaMA-3.3-70B to synthesize a grounded, cited answer - not a guess.

---

## Demo

> Try it live at [code-archaeology-rag.streamlit.app](https://code-archaeology-rag.streamlit.app)

Suggested repos to try:
- `https://github.com/pallets/flask`
- `https://github.com/tiangolo/fastapi`
- Any public repo you are curious about

---

## Features

**Ask** - question answering over commit history with three modes: Detailed, Quick Summary, and Bullet Points. Suggested questions included. Last 10 answers saved in session history.

**File Timeline** - trace how any file evolved over time. Returns a chronological commit table, a monthly activity chart, and an LLM-generated analysis covering major phases of change, contributing authors, and recurring patterns.

**Hot Files** - ranks files by change frequency. Tells you where the core of a codebase lives and which files are most likely to carry historical complexity.

**Co-Change Analysis** - finds file pairs that are almost always modified together. Reveals hidden dependencies and coupling that static analysis tools miss.

**Author Breakdown** - shows who built what, how many commits each person made, and which files they owned. Answers the question: if this person left, what knowledge would we lose?

**Multi-repo support** - ingest any number of public repos. Switch between them from the Ingest page. Each repo gets its own isolated namespace.

---

## Architecture

```
GitHub Repo URL
      ↓
Git history extraction          GitHub API (PRs, reviews)
      ↓                                  ↓
  git_loader.py              github_enricher.py
      ↓                                  ↓
              chunker.py - builds enriched chunks
                    ↓
         vector_store.py - BGE embeddings + Pinecone
                    ↓
           Hybrid search (dense 60% + BM25 40%)
                    ↓
            query/engine.py - Groq + LLaMA-3.3-70B
                    ↓
            retrieval/graph.py - NetworkX knowledge graph
                    ↓
                 app.py - Streamlit UI
```

---

## Tech Stack

| Layer | Tool | Why |
|---|---|---|
| Git extraction | GitPython | Programmatic access to commits and diffs |
| GitHub API | PyGithub | PR descriptions, review comments, issue links |
| Embeddings | BAAI/bge-small-en-v1.5 | Better retrieval quality, runs locally |
| Vector DB | Pinecone | Cloud-hosted, per-repo namespaces, production-ready |
| Hybrid search | BM25 (rank-bm25) | Handles exact identifiers that semantic search misses |
| Knowledge graph | NetworkX | File-level temporal linking across commits |
| LLM | LLaMA-3.3-70B via Groq | Fast inference, excellent reasoning, free tier |
| UI | Streamlit | Entire stack is Python, no separate API layer needed |

---

## How It Works

### 1. Ingestion Pipeline
When you paste a GitHub URL, the system clones the repo locally and walks through every commit using GitPython. For each commit it extracts the SHA, message, author, timestamp, files changed, insertion/deletion counts, and the actual code diff. Each commit becomes one chunk - a structured object with a rich text field for embedding and a metadata dictionary for filtering.

The text field combines commit message, a classified intent label (BUG FIX / FEATURE / REFACTOR / DOCS / CHORE), author, date, files, and diff. This structure gives the embedding model strong semantic signal about what kind of change was made and why.

### 2. Hybrid Search
Chunks are embedded using `BAAI/bge-small-en-v1.5` with BGE's query prefix for better question-type retrieval and stored in Pinecone under a repo-specific namespace.

At query time the system fetches the top candidates from Pinecone (dense retrieval), then re-ranks them using BM25 (keyword matching), combining both scores at 60/40 weight. This means searches for exact function names and file paths work just as well as conceptual questions.

### 3. RAG Query Engine
Retrieved chunks are injected into a structured prompt that tells LLaMA to answer only from the provided evidence, cite specific commits, and clearly state when there is not enough information. Temperature is set at 0.15 for factual, grounded responses.

### 4. Knowledge Graph
A directed NetworkX graph connects commits that touched the same files, with time flowing forward. This powers the four analysis pages - file timeline, co-change analysis, author breakdown, and hot files - without any additional API calls.

---

## Running Locally

### Prerequisites
- Python 3.10+
- Pinecone account (free tier works)
- Groq API key (free tier works)
- GitHub personal access token

### Setup

```bash
git clone https://github.com/RishabhPR77/code-archaeology-rag
cd code-archaeology-rag
pip install -r requirements.txt
```

Create a `.env` file:

```
GROQ_API_KEY=your_groq_key
PINECONE_API_KEY=your_pinecone_key
GITHUB_TOKEN=your_github_token
```

Run the app:

```bash
streamlit run app.py
```

Go to `http://localhost:8501`, paste any public GitHub URL on the Ingest page, and start asking questions.

---

## Project Structure

```
code-archaeology-rag/
├── app.py                      # Streamlit UI - all 6 pages
├── ingestion/
│   ├── git_loader.py           # CommitRecord extraction via GitPython
│   ├── github_enricher.py      # PR and review data via PyGithub
│   └── chunker.py              # Chunk builder with intent classification
├── storage/
│   └── vector_store.py         # BGE embeddings + Pinecone + BM25 hybrid search
├── retrieval/
│   └── graph.py                # NetworkX knowledge graph + 4 analysis types
├── query/
│   └── engine.py               # RAG pipeline - ask() and timeline_ask()
├── data/
│   ├── repos.json              # Registry of ingested repos
│   └── raw/                    # Per-repo chunk JSON files
└── requirements.txt
```

---

## Limitations

- Only public GitHub repositories are supported
- PR data requires the GitHub API, which may be rate-limited or blocked on some networks. The system works without it but answer quality is lower since PR descriptions carry most of the "why" context
- Ingestion time scales with commit count - 300 commits takes about 3 minutes, 1000 commits about 10 minutes
- Answer quality depends on commit message quality. Repos with descriptive messages produce much better answers than repos where every commit says "update" or "fix"

---

## What Makes This Different

Most RAG projects are "chat with your PDF." This project is different because:

The data source is live Git history - something every real software company has. The system retrieves developer **intent** not just file content. It solves a pain point every developer feels immediately - staring at old code with no context. And it combines semantic search, keyword matching, and temporal graph analysis in a single pipeline rather than relying on any one technique alone.

---
