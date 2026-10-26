# Code Archaeologist

**Ask why any code was written, and get a grounded, cited answer from the repository's own history.**

Code Archaeologist turns a GitHub repository's commits, diffs, pull requests and code reviews into a searchable memory. Ask a question in plain English and it retrieves the commits that matter, then has a large language model answer **only from that evidence**, citing the commits it used.

You bring your own model: connect an **Anthropic, OpenAI, Google Gemini, Groq or OpenRouter** key and pick any model from that provider's live catalogue.

![Landing page](docs/screenshots/landing.jpg)

---

## Contents

- [Why](#why)
- [Features](#features)
- [Bring your own model](#bring-your-own-model)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Security](#security)
- [API](#api)
- [Testing](#testing)
- [Project structure](#project-structure)
- [Limitations and roadmap](#limitations-and-roadmap)

---

## Why

Every developer has opened an old file and wondered *why is it written like this?* The author may have left, there are no docs, and the commit message says "fix bug". The reasoning is buried in Git history, PR descriptions and review threads: technically available, but practically out of reach.

Code Archaeologist makes that history answerable:

- *"Why was the authentication system refactored?"*
- *"What bugs were fixed in the session module, and what caused them?"*
- *"Which files are most tightly coupled?"*
- *"How did `sessions.py` evolve, and who drove each change?"*

## Features

| | |
|---|---|
| **Ask** | Chat-style Q&A over the history, with Detailed, Summary and Bullets modes. Every answer lists its source commits (SHA, author, date, files, relevance) and links each cited SHA to GitHub. History is saved per repository. |
| **File timeline** | Traces every commit that touched a file, with an LLM summary of the phases of change, a monthly activity chart and the full chronology. |
| **Overview** | Commits, contributors, files touched, lines added and removed, linked PRs, weekly activity and a breakdown of change types. |
| **Hot files** | The files that change most often, which is where complexity and risk concentrate. |
| **Co-change** | File pairs that are usually modified together, revealing coupling that static analysis misses. |
| **Authors** | Who built what: commit share, activity span, lines changed and the files each person owns. |
| **Pull requests** | Merged PRs linked to the ingested commits, with labels. Their descriptions and reviews feed every answer. |
| **Commits** | A searchable, filterable commit log with type classification. |
| **Accounts** | Email and password sign-up, plus optional **Sign in with GitHub**. Every repository, key and answer is private to its owner. |

![Repository overview](docs/screenshots/overview.jpg)

## Bring your own model

Answers always use **the signed-in user's own API key**. The server never pays for LLM calls.

Model lists are **not hardcoded**. When a user saves a key, the backend calls that provider's official list-models endpoint with it. That both verifies the key and returns exactly the models it can use, so new releases appear in the picker the day they ship.

| Provider | How models are discovered | How answers are generated |
|---|---|---|
| **Anthropic** | `GET /v1/models?lifecycle=active`: only active models, with `display_name`, context window and max output | Messages API. No `temperature` (several current models always use adaptive thinking); `max_tokens` is capped at the model's own limit |
| **OpenAI** | `GET /v1/models`, filtered to text models: image, realtime/voice, transcription, TTS, embedding and moderation families are excluded, as are models past their `shutdown_date` | Responses API, which OpenAI recommends for its reasoning models. Uses `instructions` and `max_output_tokens`, with `store=false` |
| **Google Gemini** | `models.list`, keeping models whose `supportedGenerationMethods` include `generateContent`, minus media and agent models | `generate_content` via the official `google-genai` SDK. Thinking tokens count toward `max_output_tokens`, so the budget is generous |
| **Groq** | `GET /openai/v1/models`, keeping `active` models and dropping speech, TTS and guard models | OpenAI-compatible chat with `max_completion_tokens` (`max_tokens` is deprecated) |
| **OpenRouter** | `GET /api/v1/key` to verify the key, then `GET /api/v1/models?output_modalities=text` | OpenAI-compatible chat. `temperature` is sent only when the model lists it in `supported_parameters` |

Users can connect several providers and switch the active one at any time.

![Model providers](docs/screenshots/providers.jpg)

## Architecture

```mermaid
flowchart LR
    subgraph Browser
      UI[React + Vite SPA]
    end
    subgraph Server
      NG[nginx<br/>static files + /api proxy] --> API[FastAPI]
      API --> DB[(PostgreSQL / SQLite<br/>users, encrypted keys,<br/>repos, chunks, answers)]
      API --> JOB[Ingest worker<br/>background task]
      JOB --> GH[(GitHub<br/>clone + PR API)]
      JOB --> EMB[BGE-small embeddings<br/>local CPU]
      EMB --> VEC[(Pinecone<br/>one namespace per repo)]
      API --> VEC
      API --> LLM[[User's LLM provider<br/>Anthropic · OpenAI · Gemini · Groq · OpenRouter]]
    end
    UI --> NG
```

**Ingestion**, a background job with live progress in the UI:

1. **Clone.** A shallow clone into a temporary folder that is deleted afterwards.
2. **Extract.** For each commit: SHA, message, author, date, files, line counts and the diff (truncated on line boundaries).
3. **Enrich.** Merged PRs within the commit window are fetched along with their descriptions, labels, review comments and review summaries. They are linked to commits by merge SHA, with a fuzzy fallback for squash merges.
4. **Chunk.** One chunk per commit. The text combines a classified intent (`BUG FIX`, `FEATURE`, `REFACTOR`, ...), the metadata, the PR context and the diff.
5. **Embed and index.** `BAAI/bge-small-en-v1.5` embeddings are stored in a namespace unique to that repository and user.

**Answering:**

1. **Hybrid retrieval.** Dense vector search pulls candidates, which are re-ranked with BM25 keyword scores (60% dense, 40% BM25). Exact identifiers such as function names and file paths are found as reliably as concepts.
2. **Grounded prompt.** The model must answer only from the retrieved commits, cite SHAs and say when the evidence is insufficient.
3. **Generation.** The user's active provider and model generate the answer. It is rendered as Markdown with no raw HTML allowed and stored in the repository's history.

The analytics pages (overview, hot files, co-change, authors, PRs, commits) are computed directly from the stored chunks, with no LLM or vector calls.

## Tech stack

| Layer | Choice |
|---|---|
| Frontend | React 19, Vite 8, TypeScript, Tailwind CSS 4, TanStack Query, React Router, Recharts, react-markdown |
| API | FastAPI, Pydantic v2, SQLAlchemy 2 |
| Auth | bcrypt password hashing, HS256 JWT in an httpOnly cookie, GitHub OAuth |
| Secrets | Fernet (AES-128-CBC + HMAC) encryption of users' API keys at rest |
| Database | PostgreSQL in production, SQLite for local development |
| Git and GitHub | GitPython, PyGithub |
| Retrieval | sentence-transformers (BGE-small), Pinecone serverless, rank-bm25 |
| LLM SDKs | `anthropic`, `openai` (also used for Groq and OpenRouter), `google-genai` |
| Delivery | Docker, nginx, docker compose |

## Getting started

### Prerequisites

- Python 3.12+
- Node.js 22+
- Git
- An API key from any one of the five supported providers. It is entered in the app, not in config.

### 1. Backend

```bash
cd backend
python -m venv .venv
```

Activate the environment (Windows: `.venv\Scripts\activate`; macOS and Linux: `source .venv/bin/activate`), then:

```bash
pip install -r requirements-dev.txt
```

```bash
cp .env.example .env
```

Generate the two required secrets and paste them into `backend/.env`:

```bash
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))"
```

```bash
python -c "from cryptography.fernet import Fernet; print('ENCRYPTION_KEY=' + Fernet.generate_key().decode())"
```

Run the API on <http://localhost:8000> (interactive docs at `/api/docs`):

```bash
uvicorn app.main:app --reload --port 8000
```

With no `PINECONE_API_KEY` set, a local file-backed vector store is used, so the app runs fully offline apart from GitHub and your chosen LLM provider.

### 2. Frontend

```bash
cd frontend
npm ci
```

```bash
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to the backend, so the session cookie stays first-party.

### 3. First run

1. Create an account.
2. In **Settings**, paste a provider key. It is verified against the provider, then encrypted.
3. Pick a model from the live list.
4. Click **New repository**, paste a public GitHub URL (for example `https://github.com/pallets/flask`) and start asking.

## Configuration

All settings are environment variables, read from `backend/.env`. See [`backend/.env.example`](backend/.env.example).

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *required* | Signs session tokens (at least 32 characters) |
| `ENCRYPTION_KEY` | *required* | Fernet key that encrypts users' API keys. **Changing it makes saved keys unreadable.** |
| `ENVIRONMENT` | `development` | `production` enables Secure cookies and hides `/api/docs` |
| `FRONTEND_URL` | `http://localhost:5173` | Public URL of the app, used for OAuth redirects and CORS |
| `DATABASE_URL` | SQLite in `backend/data/` | For example `postgresql+psycopg://user:pass@host:5432/db` |
| `PINECONE_API_KEY` | *empty* | Empty means the local vector store |
| `PINECONE_INDEX` | `code-archaeologist` | Created automatically (384-dim, cosine) |
| `GITHUB_TOKEN` | *empty* | Raises the GitHub API limit for PR fetching. Users who sign in with GitHub use their own token. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | *empty* | Enable **Sign in with GitHub** |
| `ADMIN_EMAILS` | *empty* | Comma-separated accounts that bypass usage limits |
| `MAX_COMMITS` | `100` | Commits per repository |
| `MAX_REPOS_PER_USER` | `5` | Repositories a user can keep |
| `MAX_INGESTS_PER_DAY` | `5` | Ingests per user per rolling 24 hours. Deleting a repository doesn't reset it. |
| `REPO_TTL_HOURS` | `72` | Repositories and their vectors are deleted after this long. `0` keeps them forever. |
| `MAX_CONCURRENT_INGESTS` | `2` | Parallel ingest jobs |

The limits exist because ingestion uses the server's own resources (CPU embeddings, Pinecone, the GitHub API). Answers use the user's key, so they are not rate-limited.

### Sign in with GitHub

1. Create an OAuth app at <https://github.com/settings/developers>.
2. Set **Authorization callback URL** to `{FRONTEND_URL}/api/auth/github/callback`, for example `http://localhost:5173/api/auth/github/callback`.
3. Put the client ID and secret in `backend/.env` and restart the API. The button appears on the sign-in pages.

The app requests the `read:user user:email` scopes. A GitHub account with a verified email that matches an existing account is linked to it.

## Deployment

The repository includes a production-style stack: PostgreSQL, the FastAPI API and nginx serving the built React app, with the API proxied under the same origin.

1. Create `backend/.env` from the example and fill in `SECRET_KEY` and `ENCRYPTION_KEY`.
2. Build and start the stack:

```bash
docker compose up --build -d
```

The app is served at <http://localhost:8080>.

**Production checklist**

- Serve over HTTPS and set `ENVIRONMENT=production` so cookies are marked `Secure`.
- Set `PUBLIC_URL` (used for `FRONTEND_URL` in compose) to the public origin, and use it for the GitHub OAuth callback.
- Use a strong `POSTGRES_PASSWORD`, and back up the database **and** `ENCRYPTION_KEY` together.
- Set `PINECONE_API_KEY` so vectors survive container restarts, and `GITHUB_TOKEN` for reliable PR fetching.
- Run **one API worker** per instance. Ingest jobs, the ingest semaphore and the login rate limiter are in-process; to scale out, move jobs to a queue such as RQ or Celery and the limiter to Redis.

The API image installs CPU-only PyTorch and bakes the embedding model in, so the first ingest doesn't download it.

## Security

- **API keys** are verified with the provider, encrypted at rest with Fernet and only ever decrypted server-side for a call. They are never returned to the browser; the UI sees a short hint such as `sk-a…9f2c`, and only for long keys.
- **Sessions** are signed JWTs in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production). They are never readable by JavaScript.
- **Passwords** are hashed with bcrypt. Sign-in and sign-up are rate-limited per IP.
- **Isolation.** Every repository, vector namespace, key and saved answer belongs to one user. Other users get a `404`.
- **Model output** is rendered as Markdown without raw HTML, so content from commits or models can't inject markup.
- **Provider errors** never surface as `401`, so a bad API key can't be mistaken for an expired session.
- **nginx** sends `X-Content-Type-Options`, `X-Frame-Options: DENY` and a strict referrer policy.

## API

The interactive OpenAPI docs are available at `/api/docs` in development.

| Method and path | Description |
|---|---|
| `POST /api/auth/register` · `/login` · `/logout` | Email and password auth |
| `GET /api/auth/me` | Current user and usage limits |
| `GET /api/auth/github/login` → `/callback` | GitHub OAuth |
| `GET /api/providers` | The five providers and this user's status for each |
| `PUT /api/providers/{id}/key` | Verify and save a key; returns the live model list |
| `GET /api/providers/{id}/models` | Live model list (`?refresh=true` bypasses the 10-minute cache) |
| `PUT /api/providers/{id}/model` · `PUT /api/providers/active` | Choose a model or the active provider |
| `POST /api/repos` · `GET /api/repos/{id}` · `POST /api/repos/{id}/resync` · `DELETE /api/repos/{id}` | Ingest and manage repositories (status is polled) |
| `GET /api/repos/{id}/overview` · `hotfiles` · `cochange` · `authors` · `pulls` · `commits` · `files` | Analytics |
| `POST /api/repos/{id}/ask` · `GET`/`DELETE /api/repos/{id}/queries` | Q&A and its history |
| `POST /api/repos/{id}/timeline` | File evolution summary |

## Testing

```bash
cd backend
python -m pytest
```

There are 37 tests:

- **Auth:** sessions, cookie flags, rate limiting and admin handling.
- **Keys:** encryption, never echoing a key back, and per-user isolation.
- **Ingestion and analytics:** the full ingest-to-answer flow, limits, expiry cleanup and deletion of vectors.
- **Provider adapters:** all five adapters run their **real SDKs against mocked HTTP**, with response bodies shaped like each provider's official API reference. This pins down exactly what is sent (for example, no `temperature` for Anthropic and OpenAI) and how responses and errors are parsed.

For the frontend, run a type-check and production build:

```bash
cd frontend
npm run build
```

## Project structure

```
code-archaeology-rag/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, expiry cleanup loop
│   │   ├── config.py            # Settings (env vars)
│   │   ├── db.py · models.py    # SQLAlchemy engine and tables
│   │   ├── security.py          # bcrypt, JWT sessions, Fernet key encryption
│   │   ├── deps.py · schemas.py # auth dependencies, rate limiter, request/response models
│   │   ├── llm/                 # one adapter per provider + live model registry
│   │   ├── routers/             # auth, providers, repos
│   │   └── services/            # ingest jobs, RAG prompts, usage limits
│   ├── ingestion/               # git_loader, github_enricher, chunker
│   ├── storage/vector_store.py  # BGE embeddings, Pinecone or local store, hybrid search
│   ├── retrieval/analytics.py   # hot files, co-change, authors, PRs, timelines
│   ├── tests/
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/               # Landing, Auth, Dashboard, Settings, repo/* tabs
│   │   ├── components/          # UI kit, model picker, markdown, dialogs
│   │   ├── layouts/AppLayout.tsx
│   │   └── lib/                 # API client, types, queries, theme
│   ├── nginx.conf
│   └── Dockerfile
└── docker-compose.yml
```

## Limitations and roadmap

- Only **public** GitHub repositories are supported.
- PR context needs the GitHub API. Without a token, anonymous limits (60 requests per hour) may skip PRs; the app says so and **Re-sync** retries.
- Answer quality depends on commit and PR quality. Descriptive history produces much better answers than a log of "update" commits.
- Answers arrive in one piece. Token streaming is a natural next step.
- Ingestion runs in-process. A job queue would allow multiple API workers.
