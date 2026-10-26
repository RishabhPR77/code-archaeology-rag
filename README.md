# Code Archaeologist

**Ask why any code was written, and get a grounded, cited answer from the repository's own history.**

Code Archaeologist turns a GitHub repository's commits, diffs, pull requests and code reviews into a searchable memory. Ask a question in plain English and it retrieves the commits that matter, then has a large language model answer **only from that evidence**, citing the commits it used.

You bring your own model: connect an **Anthropic, OpenAI, Google Gemini, Groq or OpenRouter** key and pick any model from that provider's live catalogue.

![Landing page](docs/screenshots/landing.jpg)

The landing page plays an animated walkthrough of the whole flow: connect a model, ingest a repository, ask why, explore the history.

![Animated walkthrough](docs/screenshots/walkthrough.jpg)

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
| **Accounts** | Email and password sign-up with a 6-digit email code, plus **Continue with Google** and **Continue with GitHub**. Every repository, key and answer is private to its owner. |
| **Private repositories** | Through a GitHub App, users pick which of their repositories to share. Access is read-only and can be changed on GitHub at any time. |

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
      API[FastAPI<br/>API + built React app]
      API --> DB[(PostgreSQL / SQLite<br/>users, encrypted keys,<br/>repos, chunks, answers)]
      API --> JOB[Ingest worker<br/>background task]
      JOB --> GH[(GitHub<br/>clone + PR API)]
      JOB --> EMB[Embeddings<br/>BGE-small locally or<br/>Pinecone hosted]
      EMB --> VEC[(Pinecone<br/>one namespace per repo)]
      API --> VEC
      API --> LLM[[User's LLM provider<br/>Anthropic · OpenAI · Gemini · Groq · OpenRouter]]
    end
    UI --> API
```

**Ingestion**, a background job with live progress in the UI:

1. **Clone.** A shallow clone into a temporary folder that is deleted afterwards.
2. **Extract.** For each commit: SHA, message, author, date, files, line counts and the diff (truncated on line boundaries).
3. **Enrich.** Merged PRs within the commit window are fetched along with their descriptions, labels, review comments and review summaries. They are linked to commits by merge SHA, with a fuzzy fallback for squash merges.
4. **Chunk.** One chunk per commit. The text combines a classified intent (`BUG FIX`, `FEATURE`, `REFACTOR`, ...), the metadata, the PR context and the diff.
5. **Embed and index.** Chunks are embedded with `BAAI/bge-small-en-v1.5` in-process, or with Pinecone's hosted `llama-text-embed-v2` in production, and stored in a namespace unique to that repository and user.

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
| Retrieval | Pinecone serverless and hosted embeddings, or sentence-transformers (BGE-small) locally; rank-bm25 |
| LLM SDKs | `anthropic`, `openai` (also used for Groq and OpenRouter), `google-genai` |
| Delivery | One Docker container on Render (FastAPI serves the API and the built frontend) |

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
| `FRONTEND_URL` | Render's URL, else `http://localhost:5173` | Public URL of the app, used for OAuth redirects and CORS |
| `DATABASE_URL` | SQLite in `backend/data/` | For example `postgresql+psycopg://user:pass@host:5432/db` |
| `PINECONE_API_KEY` | *empty* | Empty means the local vector store |
| `PINECONE_INDEX` | `code-archaeologist` | Created automatically with the right dimension for the embedding provider |
| `EMBEDDING_PROVIDER` | `local` | `local` runs BGE-small in-process (about 550 MB RAM; install `requirements-local.txt`). `pinecone` uses Pinecone's hosted embeddings and needs `PINECONE_API_KEY`. |
| `EMBEDDING_MODEL` | `llama-text-embed-v2` | Hosted embedding model, used when `EMBEDDING_PROVIDER=pinecone` |
| `GITHUB_TOKEN` | *empty* | Raises the GitHub API limit for PR fetching. Users who sign in with GitHub use their own token. |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | *empty* | Enable **Sign in with GitHub** |
| `ADMIN_EMAILS` | *empty* | Comma-separated accounts that bypass usage limits |
| `MAX_COMMITS` | `100` | Commits per repository |
| `MAX_REPOS_PER_USER` | `5` | Repositories a user can keep |
| `MAX_INGESTS_PER_DAY` | `5` | Ingests per user per rolling 24 hours. Deleting a repository doesn't reset it. |
| `REPO_TTL_HOURS` | `72` | Repositories and their vectors are deleted after this long. `0` keeps them forever. |
| `MAX_CONCURRENT_INGESTS` | `2` | Parallel ingest jobs |

The limits exist because ingestion uses the server's own resources (CPU embeddings, Pinecone, the GitHub API). Answers use the user's key, so they are not rate-limited.

### Sign-in options

All three are optional and turn on when their settings are present. Below, `APP_URL` means your public URL, for example `https://code-archaeologist-a9ms.onrender.com`, or `http://localhost:5173` in development. On Render, add each value in the service's **Environment** tab. Locally, put them in `backend/.env`.

**Continue with GitHub (GitHub App).** One GitHub App handles sign-in and gives read-only access to the repositories each user chooses, private ones included. An OAuth App can't do that without the `repo` scope, which also grants write access.

1. Open <https://github.com/settings/apps/new>.
2. Fill in the basics:
   - **Homepage URL:** `APP_URL`
   - **Callback URL:** `APP_URL/api/auth/github/callback`
   - Keep **Expire user authorization tokens** checked.
   - Leave **Request user authorization (OAuth) during installation** unchecked.
   - **Setup URL:** `APP_URL/app/settings?github=installed`, with **Redirect on update** checked.
   - **Webhook:** uncheck **Active**.
3. Set the permissions:
   - **Repository permissions:** Contents → Read-only, Pull requests → Read-only. Metadata is read-only automatically.
   - **Account permissions:** Email addresses → Read-only.
4. Set **Where can this GitHub App be installed?** to **Any account**, then click **Create GitHub App**.
5. On the app's page, copy the **Client ID** and click **Generate a new client secret**. The slug is the last part of the app's public URL, `github.com/apps/<slug>`.
6. Set `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET` and `GITHUB_APP_SLUG`.

Users sign in, or connect GitHub from Settings, then pick repositories on GitHub. Those repositories appear under **New repository → Your GitHub**. Private repositories are cloned with the user's token passed through git's environment, so it never appears in URLs or logs. Their history is stored like any other ingested repository and deleted after `REPO_TTL_HOURS`.

**Continue with Google.**

1. In [Google Cloud Console](https://console.cloud.google.com/), create a project, then open **Google Auth Platform**.
2. Under **Branding**, set the app name and support email.
3. Under **Audience**, choose **External** and click **Publish app**. The basic `openid email profile` scopes need no review.
4. Under **Clients → Create client**, choose **Web application**:
   - **Authorized JavaScript origin:** `APP_URL`
   - **Authorized redirect URI:** `APP_URL/api/auth/google/callback`
5. Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`.

**Email codes at sign-up.** New email-and-password accounts must enter a 6-digit code before using the app; Google and GitHub sign-ins are already verified. Codes are stored only as an HMAC. Each code expires after 10 minutes and allows 5 attempts, and resends are limited to one per minute and five per hour. Accounts created before verification existed stay verified.

Render's free plan blocks outgoing SMTP, so codes go through [Brevo](https://www.brevo.com/)'s HTTP API, which is free for 300 emails a day:

1. Create a Brevo account.
2. Under **Senders, domains & dedicated IPs → Senders**, add the address to send from and confirm it.
3. Under **SMTP & API → API keys**, generate a key.
4. Set `EMAIL_DELIVERY=brevo`, `BREVO_API_KEY` and `EMAIL_FROM` (the confirmed sender).

Without a domain of your own, codes come from a free address such as Gmail and are more likely to land in spam. The verify page tells users to check there. For development, `EMAIL_DELIVERY=console` prints codes in the server log.

## Deployment

### Free: Render + Neon + Pinecone

The root [`Dockerfile`](Dockerfile) builds one slim container in which FastAPI serves both the API and the React app. It sets `EMBEDDING_PROVIDER=pinecone`, so embeddings come from Pinecone's hosted `llama-text-embed-v2` model instead of a local model. With no PyTorch in the image, the API fits Render's free 512 MB instance. Everything that must survive restarts lives outside the container: **Neon** (free Postgres) for data and **Pinecone** for vectors.

| Piece | Free tier |
|---|---|
| [Render](https://render.com/docs/free) web service | 512 MB RAM and 0.1 CPU; sleeps after 15 idle minutes and takes about a minute to wake |
| [Neon](https://neon.com/pricing) Postgres | 0.5 GB storage; scales to zero when idle |
| [Pinecone](https://www.pinecone.io/pricing/) Starter | vector storage plus 5M hosted embedding tokens per month (one 100-commit ingest is roughly 150k tokens) |

1. **Neon.** Create a project, click **Connect**, turn connection pooling off and copy the `postgresql://…` string.
2. **Push this repository to GitHub**, since Render deploys from it.
3. **Render.** Sign up at [render.com](https://render.com) with GitHub, then choose **New → Blueprint** and pick this repository. Render reads [`render.yaml`](render.yaml) and asks once for five values. Paste them from your `backend/.env`:
   - `SECRET_KEY`
   - `ENCRYPTION_KEY`
   - `DATABASE_URL` (the Neon string)
   - `PINECONE_API_KEY`
   - `GITHUB_TOKEN`

   Click **Apply**. The first build takes about 5 to 10 minutes.
4. **Open** `https://<service-name>.onrender.com`. `FRONTEND_URL` is filled in automatically from Render's `RENDER_EXTERNAL_URL`.

Every push to `main` redeploys automatically. On first use the app creates the `code-archaeologist-llama` Pinecone index (1024 dimensions). It is separate from the 384-dimension index used by local embeddings, because the two kinds of vectors can't share an index.

To turn on **Continue with GitHub**, **Continue with Google** or **email codes**, follow [Sign-in options](#sign-in-options) with `APP_URL` set to your `onrender.com` address, and add the values in the service's **Environment** tab. Render redeploys when you save.

### Running it in production

- Render serves the site over HTTPS. Keep `ENVIRONMENT=production` so session cookies are marked `Secure`.
- Back up the database **and** `ENCRYPTION_KEY` together: without the key, saved API keys and GitHub tokens can't be decrypted.
- Run **one API worker**. Ingest jobs, the ingest limit and the login rate limiter live in the process; scaling out would need a job queue (such as RQ or Celery) and a shared limiter (such as Redis).
- Schema migrations run automatically on every start.

## Security

- **API keys** are verified with the provider, encrypted at rest with Fernet and only ever decrypted server-side for a call. They are never returned to the browser; the UI sees a short hint such as `sk-a…9f2c`, and only for long keys.
- **Sessions** are signed JWTs in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production). They are never readable by JavaScript.
- **Passwords** are hashed with bcrypt. Sign-in, sign-up and code checks are rate-limited per IP.
- **OAuth** flows use `state` plus PKCE. A Google or GitHub sign-in that claims an email address whose password account was never verified removes that unverified password, which blocks account pre-hijacking.
- **GitHub access** is a GitHub App with read-only permissions on the repositories each user picks. Tokens are encrypted at rest and refreshed before they expire.
- **Isolation.** Every repository, vector namespace, key and saved answer belongs to one user. Other users get a `404`.
- **Model output** is rendered as Markdown without raw HTML, so content from commits or models can't inject markup.
- **Provider errors** never surface as `401`, so a bad API key can't be mistaken for an expired session.
- **Responses** carry `X-Content-Type-Options: nosniff` and a strict referrer policy.

## API

The interactive OpenAPI docs are available at `/api/docs` in development.

| Method and path | Description |
|---|---|
| `POST /api/auth/register` · `/login` · `/logout` | Email and password auth |
| `GET /api/auth/me` | Current user and usage limits |
| `POST /api/auth/verify-email` · `POST /api/auth/resend-code` | Sign-up email code |
| `GET /api/auth/github/login` → `/callback` · `GET /api/auth/google/login` → `/callback` | GitHub App and Google sign-in (PKCE) |
| `GET /api/github/status` · `GET /api/github/repos` · `DELETE /api/github` | GitHub connection and the repositories a user shared |
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

There are 72 tests:

- **Auth:** sessions, cookie flags, rate limiting and admin handling.
- **Accounts:** email codes (hashing, expiry, attempt and resend limits), GitHub App sign-in, linking and token refresh, Google sign-in, pre-hijack protection, private-repo cloning, the Brevo request format and the startup check of the Brevo sender. All HTTP is mocked.
- **Migrations:** a database created before migrations existed is stamped and upgraded in place.
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
│   │   ├── main.py              # FastAPI app, startup checks, expiry cleanup, serves the built frontend
│   │   ├── config.py            # Settings (env vars)
│   │   ├── db.py · models.py    # SQLAlchemy engine and tables
│   │   ├── security.py          # bcrypt, JWT sessions, Fernet key encryption
│   │   ├── deps.py · schemas.py # auth dependencies, rate limiter, request/response models
│   │   ├── llm/                 # one adapter per provider + live model registry
│   │   ├── routers/             # auth, github, providers, repos
│   │   └── services/            # ingest jobs, RAG prompts, OAuth, GitHub, email codes, usage limits
│   ├── ingestion/               # git_loader, github_enricher, chunker
│   ├── storage/vector_store.py  # local or hosted embeddings, Pinecone or local store, hybrid search
│   ├── retrieval/analytics.py   # hot files, co-change, authors, PRs, timelines
│   ├── migrations/              # Alembic schema migrations (run on every start)
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/               # Landing (with the animated walkthrough), Auth, Verify email,
│       │                        # Dashboard, Settings, Privacy, Terms, repo/* tabs
│       ├── components/          # UI kit, product walkthrough, model picker, markdown, dialogs
│       ├── layouts/AppLayout.tsx
│       └── lib/                 # API client, types, queries, theme
├── docs/screenshots/            # images used in this README
├── Dockerfile                   # single production image (built by Render)
└── render.yaml                  # Render Blueprint
```

## Limitations and roadmap

- Private repositories need the GitHub App set up (see [Sign-in options](#sign-in-options)); otherwise only public repositories can be ingested.
- PR context needs the GitHub API. Without a token, anonymous limits (60 requests per hour) may skip PRs; the app says so and **Re-sync** retries.
- Answer quality depends on commit and PR quality. Descriptive history produces much better answers than a log of "update" commits.
- Answers arrive in one piece. Token streaming is a natural next step.
- Ingestion runs in-process. A job queue would allow multiple API workers.
