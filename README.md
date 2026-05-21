# 🏺 Code Archaeologist

> **Understand any GitHub repository's history in plain English.**  
> Ask questions about why code was changed, trace file evolution, discover hot spots and author contributions — all powered by RAG + LLM.

**Live Demo → [code-archaeology-rag.streamlit.app](https://code-archaeology-rag.streamlit.app)**

---

## What It Does

Most developers understand *what* code does. Code Archaeologist answers *why* it changed.

Paste any public GitHub repository URL, and the system extracts every commit, embeds them semantically, and lets you query the entire history using natural language — powered by hybrid vector + keyword search and a production-grade LLM.

---

## Features

| Tab | What it does |
|---|---|
| **Ingest** | Clone any public GitHub repo, embed all commits into Pinecone, persist forever |
| **Ask** | Natural language Q&A over commit history with 8 suggested questions, 3 answer modes, and conversation history |
| **Timeline** | Select any file → get an AI-generated narrative of how it evolved commit by commit |
| **Hot Files** | Ranked list of most frequently changed files — pinpoints unstable areas |
| **Co-Change** | File pairs that always change together — reveals hidden coupling |
| **Authors** | Per-author breakdown of commits and which files they owned |

---

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| UI | Streamlit | Fast to iterate, clean dark theme |
| Embeddings | `BAAI/bge-small-en-v1.5` | Better retrieval quality than MiniLM for Q&A tasks |
| Vector Store | Pinecone (Serverless) | Persistent cloud storage, survives deployments |
| Hybrid Search | Pinecone dense + BM25 (rank-bm25) | Semantic + keyword, best of both worlds |
| LLM | Llama 3.3 70B via Groq | Fast inference, free tier, excellent reasoning |
| Git Ingestion | GitPython | Extracts commits, diffs, file stats |
| PR Enrichment | PyGithub | Links commits to PRs, reviews, labels |
| Chunking | Custom per-commit chunker | Intent label + PR context + diff per chunk |

---

## Architecture

```
GitHub Repo URL
      │
      ▼
┌─────────────────────────────────┐
│         Ingestion Pipeline       │
│                                  │
│  GitPython → CommitRecords       │
│  PyGithub  → PRRecords           │
│  Chunker   → [FEATURE] / [FIX]   │
│             labeled text chunks  │
│  BGE-small → 384-dim embeddings  │
│  Pinecone  → persistent storage  │
└─────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────┐
│         Query Pipeline           │
│                                  │
│  User question                   │
│  → BGE embed (with query prefix) │
│  → Pinecone dense search (4×k)   │
│  → BM25 re-rank candidates       │
│  → 60% dense + 40% BM25 score    │
│  → Top-k chunks to Groq LLM      │
│  → Answer with commit citations  │
└─────────────────────────────────┘
```

---

## Running Locally

**1. Clone the repo**
```bash
git clone https://github.com/RishabhPR77/code-archaeology-rag.git
cd code-archaeology-rag
```

**2. Install dependencies**
```bash
pip install -r requirements.txt
```

**3. Create `.env`**
```
GROQ_API_KEY=your_groq_key
GITHUB_TOKEN=your_github_token
PINECONE_API_KEY=your_pinecone_key
```

**4. Run**
```bash
streamlit run app.py
```

---

## Getting API Keys (all free)

| Key | Where |
|---|---|
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer Settings → Personal Access Tokens |
| `PINECONE_API_KEY` | [app.pinecone.io](https://app.pinecone.io) |

---

## How Retrieval Works

Standard RAG uses only dense vector search. Code Archaeologist uses **hybrid search**:

1. Embed the question with BGE-small (with retrieval-optimized query prefix)
2. Fetch top 32 candidates from Pinecone using cosine similarity
3. Re-rank those 32 using BM25 keyword scoring on the same candidates
4. Final score = **0.6 × dense + 0.4 × BM25**
5. Top 8 results sent to Llama 3.3 70B with a structured prompt

This means queries with specific filenames, function names, or SHAs work just as well as semantic queries like *"why was authentication refactored?"*

---

## Ingestion Time Estimates

| Commits | Estimated Time |
|---|---|
| 50 | ~2 min |
| 300 | ~6 min |
| 1000 | ~20 min |

*First run downloads the BGE model (~130MB). Subsequent runs skip this.*

---

## Project Structure

```
code-archaeology-rag/
├── app.py                    # Streamlit UI — all pages
├── main.py                   # CLI entry point for local use
├── ingestion/
│   ├── git_loader.py         # Clone repo, extract CommitRecords
│   ├── chunker.py            # Build labeled text chunks per commit
│   └── github_enricher.py   # Fetch PRs, reviews, labels from GitHub API
├── storage/
│   └── vector_store.py       # Pinecone client, BGE embeddings, hybrid search
├── query/
│   └── engine.py             # Prompt builder, Groq LLM calls, timeline analysis
├── retrieval/
│   └── graph.py              # CommitGraph for timeline, hot files, co-change, authors
└── requirements.txt
```

---

## Example Questions

- *"Why was the authentication module refactored?"*
- *"Which bugs were fixed most frequently and by whom?"*
- *"What new features were added in the last month?"*
- *"Which files are most error-prone based on fix commits?"*
- *"Summarize what each author worked on."*

---

## Built By

**Rishabh Patidar** — [GitHub](https://github.com/RishabhPR77)

---

*Code Archaeologist — because every commit tells a story.*