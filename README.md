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
- [Accuracy](#accuracy)
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
| **Ask** | Chat-style Q&A over the history, with Detailed, Summary and Bullets modes. Every answer lists its source commits (SHA, author, date, files, relevance) and links each cited SHA to GitHub. Questions are kept in chats: start a **New chat** any time, and switch between or delete past chats. Follow-ups such as “who reviewed it?” understand the chat's last three exchanges. Answers **stream in** as the model writes them, and **Stop** ends one early. |
| **File timeline** | Pick any file or folder from a searchable list and trace every commit that touched it, with an LLM summary of the phases of change, a monthly activity chart and the full chronology. |
| **Bug origins** | Every bug-fix commit traced back to the commits that most likely introduced the bug, using `git blame` on the lines the fix changed (the SZZ method). Shows how long each bug lived and which commits sit behind several fixes. No LLM needed. |
| **Who broke it?** | Describe a bug or paste an error, and get the three most likely culprit commits. They're ranked by how well they match the report (hybrid search), whether they changed files it names (stack-trace paths included), and a risk signal from the type of change and Bug origins. Your model explains each suspect and suggests how to confirm it. Suspects, not proof. |
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
   **Bug origins** are traced here while the clone exists: for each bug-fix commit, `git blame` on its parent shows which commits last wrote the lines the fix changed. Docs, tests, blank lines and comments are skipped.
3. **Enrich.** Merged PRs within the commit window are fetched along with their descriptions, labels, review comments and review summaries. They are linked to commits by merge SHA, with a fuzzy fallback for squash merges.
4. **Chunk.** One chunk per commit. The text combines a classified intent (`BUG FIX`, `FEATURE`, `REFACTOR`, ...), the metadata, the PR context and the diff.
5. **Embed and index.** Chunks are embedded with `BAAI/bge-small-en-v1.5` in-process, or with Pinecone's hosted `llama-text-embed-v2` in production, and stored in a namespace unique to that repository and user.

**Answering:**

1. **Follow-ups.** In a chat with earlier messages, the model first rewrites the question into a standalone one (“who reviewed it?” becomes “who reviewed the OAuth login change in a1b2c3d?”). That is what gets searched, and the answer prompt includes the last three exchanges as context. The UI shows what was searched.
2. **Hybrid retrieval.** Up to 200 commits are fetched by meaning (dense vectors) and also scored by keywords (BM25, with code split into words, so `ctx.ensure_object()` matches "ensure object"). The two rankings are merged by position with reciprocal rank fusion, so neither side's score scale can drown out the other, and a keyword match counts three times a meaning match. Exact identifiers such as function names and file paths are found as reliably as concepts; the [accuracy check](#accuracy) measures how well it works.
3. **Grounded prompt.** The model must answer only from the retrieved commits, cite SHAs and say when the evidence is insufficient.
4. **Generation.** The user's active provider and model write the answer, which streams to the browser as server-sent events: first the commits that were found, then the answer piece by piece. All five providers stream through their official SDKs. It is rendered as Markdown with no raw HTML allowed, and only a complete answer is saved to the chat: one that fails halfway or is stopped is not.

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
| `GET /api/repos/{id}/overview` · `hotfiles` · `cochange` · `authors` · `pulls` · `commits` · `files` · `origins` | Analytics, including bug origins |
| `POST /api/repos/{id}/ask` | Ask a question; `conversation_id` continues a chat, leaving it out starts a new one |
| `POST /api/repos/{id}/ask/stream` | The same, as server-sent events: `sources` (what was found), `delta` (each new piece of the answer), then `done` (the saved exchange) or `error`. Setup problems, such as no model connected, are normal JSON errors |
| `GET /api/repos/{id}/chats` · `GET`/`DELETE /api/repos/{id}/chats/{chat_id}` | List chats, read one, delete one |
| `POST /api/repos/{id}/timeline` | File evolution summary |
| `POST /api/repos/{id}/suspects` | Rank likely culprit commits for a bug report (`description`, optional `since` date) |

## Testing

```bash
cd backend
python -m pytest
```

There are 127 tests. GitHub Actions runs them, plus the frontend type-check and build, on every push to `main` and every pull request ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). The tests replace the embedding model with a small stand-in, so CI installs only `requirements.txt`, without torch.

- **Auth:** sessions, cookie flags, rate limiting and admin handling.
- **Accounts:** email codes (hashing, expiry, attempt and resend limits), GitHub App sign-in, linking and token refresh, Google sign-in, pre-hijack protection, private-repo cloning, the Brevo request format and the startup check of the Brevo sender. All HTTP is mocked.
- **Migrations:** a database created before migrations existed is stamped and upgraded in place, and questions asked before chats existed are grouped into one chat per repository.
- **Keys:** encryption, never echoing a key back, and per-user isolation.
- **Ingestion and analytics:** the full ingest-to-answer flow, chats (grouping, privacy, deletion), follow-up questions (rewritten with only the last three exchanges), streamed answers (event order, follow-ups, a provider failing halfway saves nothing), limits, expiry cleanup and deletion of vectors.
- **Bug origins:** a real git repository built in the test traces a fix to the commit that introduced the bug, skips docs, tests and add-only fixes, and reports lines older than a shallow clone.
- **Who broke it?:** file names and stack-trace paths are read from a report, paths match on their last folders, the three signals combine as documented, unrelated commits are left out, the `since` date filters, and commits behind earlier bugs rank higher.
- **Search:** code is split into words, common words are skipped, the two rankings merge by position, and keywords find a commit the embedding ranked low.
- **Accuracy check:** the helpers that turn a repository's history into questions remove the answer's own PR text from the index and only use bug fixes from before each report.
- **Provider adapters:** all five adapters run their **real SDKs against mocked HTTP**, with response bodies shaped like each provider's official API reference. This pins down exactly what is sent (for example, no `temperature` for Anthropic and OpenAI) and how responses and errors are parsed. Streaming is tested the same way, with event streams in each provider's documented format, including errors that arrive halfway through an answer.

For the frontend, run a type-check and production build:

```bash
cd frontend
npm run build
```

## Accuracy

How often does search find the right commit, and does Who broke it? point at the right culprit? [`backend/evals/run_eval.py`](backend/evals/run_eval.py) measures both on real repositories, using questions and answers taken from their own history, so nothing is labelled by hand:

- **Search:** each merged pull request becomes a question (its title, or the first real sentence of its description), and the answer is the commit it belongs to. That PR text is removed from the index first, and the title is also cut from the commit message, so the answer can't simply match itself.
- **Who broke it?:** each bug fix that Bug origins traced becomes a report (the fix's commit message), and the traced commit is the answer. Only commits and fixes from before the fix count.

Latest run: the last 200 commits of `pallets/click`, `pallets/flask` and `encode/httpx`, with local BGE-small embeddings. Full tables are in [`backend/evals/RESULTS.md`](backend/evals/RESULTS.md).

| Search | Questions | Right commit first | In the top 3 | In the top 8 | MRR |
|---|---:|---:|---:|---:|---:|
| PR description questions, before | 263 | 38% | 47% | 55% | 0.43 |
| PR description questions, now | 263 | **49%** | **67%** | **78%** | **0.59** |
| PR title questions, before | 320 | 41% | 56% | 69% | 0.50 |
| PR title questions, now | 320 | **53%** | **70%** | **84%** | **0.63** |

| Who broke it? | Reports | Cause first | In the top 3 | In the top 10 |
|---|---:|---:|---:|---:|
| Before | 13 | 31% | 31% | 38% |
| Now | 13 | 31% | **46%** | **69%** |
| Baseline: newest commit first | 13 | 15% | 15% | 31% |

What it shows:

- **What was wrong.** Search used to add 0.6 × the dense score to 0.4 × the keyword score. Dense scores among the candidates bunch together (a spread of about 0.08), while keyword scores divided by the best one spread across almost the whole 0 to 1 range, so in practice keywords decided the order. Words were also split on spaces, so `echo()` never matched "echo". The result was worse than dense search alone.
- **The fix.** Rank fusion merges the two rankings by position, keywords are matched over every commit instead of only the top 32 by meaning, code is split into words, and a keyword match counts three times a meaning match. It beats the old search for both question types in every repository, and beats dense search alone on every measure.
- **How the weight was chosen.** Weights from 1 to 10 were tried on click and flask, and 3 did best. On httpx, which wasn't used to choose it, weight 3 also beat weight 1 (the right commit in the top 8 for 76% of description questions instead of 70%), so the gain isn't luck. Stemming and giving the commit message extra weight were tried too and made no reliable difference, so they were left out.
- **Who broke it? gains from the better search:** the traced cause is in the top 3 for 6 of 13 reports instead of 4. 13 cases are still too few to tune its weights, and a one-line fix message is much less to go on than a real bug report.
- **The absolute numbers are pessimistic.** The PR text is removed from the index, and the local model reads only about 512 tokens of each commit (the live model reads about 2048). The comparisons between searches are the reliable part. They haven't been repeated with the live site's embedding model yet.

### What good looks like

- **Found in the top 8** is the share of questions where the right commit is among the 8 that the Ask tab gives the model. It's the number that matters most: if the right commit isn't there, the model can't use it.
- **Right commit first** is the share where it's the very first source.
- **MRR** (mean reciprocal rank) averages 1 ÷ the answer's position: 1 for first, 0.5 for second, 0.33 for third, 0 when it's missing. One number that rewards ranking the answer high.

Rules of thumb for this test, which is harder than everyday use because the PR text is removed:

| Rating | Found in the top 8 | Right commit first | MRR |
|---|---:|---:|---:|
| Weak | under 60% | under 35% | under 0.45 |
| OK | 60–75% | 35–50% | 0.45–0.60 |
| Good | 75–85% | 50–60% | 0.60–0.70 |
| Very good | 85–92% | 60–70% | 0.70–0.80 |
| Excellent | over 92% | over 70% | over 0.80 |

On the number that matters most, search went from weak (55% in the top 8) to good (78–84%). Putting the right commit first (49–53%, MRR 0.59–0.63) is between OK and good, which is where a reranker would help most. For Who broke it?, which shows three suspects, good means the cause is in the top 3 for about half of real bug reports and very good means 60% or more, measured on at least 50 reports (with 13, one report moves the number by 8 points).

Next steps toward very good:

1. **Rerank the top results** with a model that reads the question and each commit together (a cross-encoder). Pinecone hosts one (`bge-reranker-v2-m3`), but its free plan allows about 500 rerank requests a month, so search would need to fall back when they run out.
2. **Repeat the check with the live embedding model**, which reads four times more of each commit.
3. **Test Who broke it? on real bug reports**, using the GitHub issue each fix closes, over more commits so there are at least 50 cases. This needs a GitHub token for the extra API requests.

Run it yourself (needs `requirements-local.txt` for the embedding model; about 20 minutes the first time and 10 after that, and it never touches Pinecone, the database or `GITHUB_TOKEN`):

```bash
cd backend
python -m evals.run_eval
```

To check search with the live site's embedding model instead, add `--hosted`. It uses `PINECONE_API_KEY` from `backend/.env`, works in a separate throwaway index that is deleted at the end (the production index is never touched), and checks search only, writing `evals/RESULTS-hosted.md`. One run embeds about 600 commits, roughly 0.6M of the 5M embedding tokens Pinecone's free plan allows each month. Each search downloads the text of 200 commits, so on a slow connection it can take up to an hour.

```bash
python -m evals.run_eval --hosted
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
│   ├── ingestion/               # git_loader, github_enricher, chunker, bug_origins
│   ├── storage/vector_store.py  # local or hosted embeddings, Pinecone or local store, hybrid search
│   ├── retrieval/               # analytics (hot files, co-change, authors, PRs, timelines), suspects
│   ├── evals/                   # accuracy check for search and Who broke it? (RESULTS.md)
│   ├── migrations/              # Alembic schema migrations (run on every start)
│   └── tests/
├── frontend/
│   └── src/
│       ├── pages/               # Landing (with the animated walkthrough), Auth, Verify email,
│       │                        # Dashboard, Settings, Privacy, Terms, repo/* tabs
│       ├── components/          # UI kit, product walkthrough, model picker, markdown, dialogs
│       ├── layouts/AppLayout.tsx
│       └── lib/                 # API client, types, queries, theme
├── .github/workflows/ci.yml     # tests and frontend build on every push and pull request
├── docs/screenshots/            # images used in this README
├── Dockerfile                   # single production image (built by Render)
└── render.yaml                  # Render Blueprint
```

## Limitations and roadmap

- Private repositories need the GitHub App set up (see [Sign-in options](#sign-in-options)); otherwise only public repositories can be ingested.
- PR context needs the GitHub API. Without a token, anonymous limits (60 requests per hour) may skip PRs; the app says so and **Re-sync** retries.
- Answer quality depends on commit and PR quality. Descriptive history produces much better answers than a log of "update" commits.
- Ingestion runs in-process. A job queue would allow multiple API workers.
