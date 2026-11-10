# Code Archaeologist

[![CI](https://github.com/RishabhPR77/code-archaeology-rag/actions/workflows/ci.yml/badge.svg)](https://github.com/RishabhPR77/code-archaeology-rag/actions/workflows/ci.yml)

**Ask why any code was written, and get a grounded, cited answer from the repository's own history.**

Code Archaeologist turns a GitHub repository's commits, diffs, pull requests and code reviews into a searchable memory. Ask a question in plain English and it retrieves the commits that matter, then has a large language model answer **only from that evidence**, citing the commits it used.

You bring your own model: connect an **Anthropic, OpenAI, Google Gemini, Groq or OpenRouter** key and pick any model from that provider's live catalogue.

**Live:** [code-archaeologist-a9ms.onrender.com](https://code-archaeologist-a9ms.onrender.com). **Try the live demo** there to explore a sample repository, its saved chats and Who broke it? without signing up. It runs on free hosting, so the first visit after a quiet spell can take a minute to wake up.

### At a glance

- **Measured search quality.** On 583 questions taken from three open-source repositories, the right commit is among the 8 the model reads for **81–89%** of them, up from 65–79% before the search was rebuilt. An automatic [accuracy check](#accuracy) found the bug that was holding it back.
- **Answers stream in** word by word, with a **Stop** button that keeps what was written.
- **Finds what broke.** Bug origins traces each bug fix back to the commit that introduced it, and **Who broke it?** ranks likely culprits for a new bug report. On 49 real bug reports from Flask, Click and HTTPX, the commit that caused the bug is in its top 3 for **57%**, nine times as often as checking the newest commits, and in the range of published research for the same task.
- **Built to run for free and safely:** five LLM providers with each user's own encrypted key, GitHub and Google sign-in with optional two-step verification, 204 tests, linters and dependency scans in GitHub Actions CI, deployed on Render, Neon and Pinecone.

![Asking pallets/flask why app.query was added: it searches the history, finds the commits, and the answer streams in with citations](docs/screenshots/ask-streaming.gif)

*On the live site, asking [pallets/flask](https://github.com/pallets/flask) why `app.query` was added: it searches the history, finds the commits, and the answer streams in, citing the commits it used.*

![The landing page, with Try the live demo and Start for free](docs/screenshots/landing.jpg)

**Try the live demo** opens a sample repository (pallets/flask) with no sign-up. Further down, the landing page plays an animated walkthrough of the whole flow, from signing up to signing out: connect a model, ingest a repository, ask why, find what broke, explore the history.

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
| **Ask** | Chat-style Q&A over the history, with Detailed, Summary and Bullets modes. Every answer lists its source commits (SHA, author, date, files, relevance) and links each cited SHA to GitHub. Questions are kept in chats: start a **New chat** any time, and switch between or delete past chats. Follow-ups such as “who reviewed it?” understand the chat's last three exchanges. Answers **stream in** as the model writes them, and **Stop** ends one early while keeping what was written, marked as stopped. |
| **File timeline** | Pick any file or folder from a searchable list and trace every commit that touched it, with a monthly activity chart and the full chronology, plus a summary of the phases of change when a model is connected. |
| **Bug origins** | Every bug-fix commit traced back to the commits that most likely introduced the bug, using `git blame` on the lines the fix changed (the SZZ method). Shows how long each bug lived and which commits sit behind several fixes. No LLM needed. |
| **Who broke it?** | Describe a bug or paste an error, and get the three most likely culprit commits. They're ranked by how well they match the report (hybrid search), whether their diff changed code it names (`follow_redirects`, `URL.join`), whether they touched files it names (stack-trace paths included), how big the change was, its type, whether Bug origins traced an earlier bug to it, and a small nudge for recent changes. Changes to only docs or tests are left out. Every suspect lists the reasons it was flagged, and your model explains them and suggests how to confirm one. Suspects, not proof. |
| **Overview** | Commits, contributors, files touched, lines added and removed, linked PRs, weekly activity and a breakdown of change types. |
| **Hot files** | The files that change most often, which is where complexity and risk concentrate. |
| **Co-change** | File pairs that are usually modified together, revealing coupling that static analysis misses. |
| **Authors** | Who built what: commit share, activity span, lines changed and the files each person owns. |
| **Pull requests** | Merged PRs linked to the ingested commits, with labels. Their descriptions and reviews feed every answer. |
| **Commits** | A searchable, filterable commit log with type classification. |
| **Any slice of history** | Ingest the latest commits, or a range further back, such as commits 500 to 700. Drag it on a slider over the whole history or type it in, and the dialog shows the first and last commit of the range (date and message) before you start. |
| **Repositories and profile** | The dashboard lists your repositories as cards with live ingest progress, and deletes one in a click. Your profile shows your details, how you sign in, and your activity: repositories, commits indexed, questions asked and your latest questions, each one link away from its chat. |
| **Live demo** | Anyone can open a sample repository without signing up. It's a shared, read-only account: visitors browse the analytics and saved chats, rank suspects and trace files, but every change is refused by the server, and searches are rate-limited per visitor. An admin picks the repository from its page (**Use as public demo**) and can stop sharing it from Settings. |
| **Accounts** | Email and password sign-up with a 6-digit email code, plus **Continue with Google** and **Continue with GitHub**. Forgot password, change password, optional **two-step sign-in** with an authenticator app and recovery codes, a **security activity** log, and **delete account**. Every repository, key and answer is private to its owner. |
| **Private repositories** | Through a GitHub App, users pick which of their repositories to share. Access is read-only and can be changed on GitHub at any time. |

![Repository overview](docs/screenshots/overview.jpg)

![An answer's source commits, each with its SHA, author, date, pull request, files and relevance](docs/screenshots/answer-sources.jpg)

*Every answer lists the commits it was built from, each linked to GitHub.*

![Bug origins for the last 500 commits of pallets/flask: 81 bug fixes, 53 traced to a likely cause, a median of 161 days from cause to fix, and the commits behind several fixes](docs/screenshots/bug-origins.jpg)

*Bug origins traces each fix back to the commit that most likely caused it, and flags commits that needed several fixes.*

![Who broke it? in the live demo, ranking suspect commits for a session-cookie bug, each with a score and the reasons it was flagged](docs/screenshots/who-broke-it.jpg)

*In the live demo, a report about the session cookie with `SESSION_COOKIE_PARTITIONED` and a stack-trace line. The suspects changed the code and the file it names, and the second is the commit that added that setting.*

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
2. **Hybrid retrieval.** Up to 200 commits are fetched by meaning (dense vectors). Pinecone returns only their IDs and scores; the text comes from the copy of each commit already saved in Postgres, which saves downloading about half a megabyte per question. The same commits are also scored by keywords (BM25, with code split into words, so `ctx.ensure_object()` matches "ensure object"). The two rankings are merged by position with reciprocal rank fusion, so neither side's score scale can drown out the other. Keywords get the weight that measured best for the embedding model: on the live site, with Pinecone's model, a keyword match counts the same as a meaning match; with the weaker local model it counts three times as much. Exact identifiers such as function names and file paths are found as reliably as concepts; the [accuracy check](#accuracy) measures how well it works.
3. **Grounded prompt.** The model must answer only from the retrieved commits, cite SHAs and say when the evidence is insufficient.
4. **Generation.** The user's active provider and model write the answer, which streams to the browser as server-sent events: first the commits that were found, then the answer piece by piece. All five providers stream through their official SDKs. It is rendered as Markdown with no raw HTML allowed, and a complete answer is saved to the chat. If you press Stop, the text written so far is saved too, marked as stopped; an answer that fails halfway is not saved.

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
- **Sessions** are signed JWTs in an `httpOnly`, `SameSite=Lax` cookie (`Secure` in production). They are never readable by JavaScript. Each token carries the account's session version, so **Sign out everywhere** (Settings) ends every session on every device at once, which a plain JWT can't do.
- **Passwords** are hashed with bcrypt, and the most common passwords are refused. Sign-in always runs the bcrypt check, even for unknown emails, so timing reveals nothing.
- **No account enumeration.** Sign-up, "resend code" and "forgot password" reply the same way whether or not an email has an account; the owner is told by email instead, and login has one error message.
- **Two-step sign-in** (optional): a TOTP code from an authenticator app after the password, Google or GitHub, with ten single-use recovery codes. A code can't be replayed, and the half-signed-in token can never act as a session.
- **Password reset and changes** use a 6-digit emailed code; resetting or changing the password ends every other session, and each sensitive change sends an alert email. A **security activity** log shows sign-ins, failed attempts and changes, with shortened IP addresses.
- **Rate limits** live in the database (keys are hashed, so no raw IPs or emails are stored), so they survive restarts and would be shared by several servers. Wrong passwords are also limited per account, from any IP. The visitor's IP comes from the header the host's proxy sets, never from `X-Forwarded-For`, which visitors can fake to dodge per-IP limits.
- **Key rotation.** Session tokens name the key that signed them, and stored secrets use MultiFernet, so `SECRET_KEY` and `ENCRYPTION_KEY` can be changed without signing anyone out; secrets are re-encrypted on start-up.
- **Fair use.** Searches (Ask and Who broke it?) are capped per account per hour, since each one uses the server's embedding allowance; the demo has tighter per-visitor and overall caps.
- **OAuth** flows use `state` plus PKCE. A Google or GitHub sign-in that claims an email address whose password account was never verified removes that unverified password, which blocks account pre-hijacking.
- **GitHub access** is a GitHub App with read-only permissions on the repositories each user picks. Tokens are encrypted at rest and refreshed before they expire.
- **Isolation.** Every repository, vector namespace, key and saved answer belongs to one user. Other users get a `404`.
- **Model output** is rendered as Markdown without raw HTML, so content from commits or models can't inject markup.
- **Provider errors** never surface as `401`, so a bad API key can't be mistaken for an expired session.
- **Responses** carry a Content-Security-Policy that only lets the site's own scripts run (the one inline script in `index.html` is allowed by the hash of its exact text, computed at startup), `X-Frame-Options: DENY` and `frame-ancestors 'none'` against clickjacking, HSTS in production, `X-Content-Type-Options: nosniff` and a strict referrer policy. Changes sent from another site's page are refused by an Origin check, on top of `SameSite` cookies.
- **Dependencies** are scanned on every push (pip-audit and npm audit), and Dependabot opens weekly update pull requests.

## API

The interactive OpenAPI docs are available at `/api/docs` in development.

| Method and path | Description |
|---|---|
| `POST /api/auth/register` · `/login` · `/logout` · `/logout-everywhere` | Email and password auth; sign out here, or on every device |
| `GET /api/auth/me` · `PATCH /api/auth/me` | Current user and usage limits; change the display name |
| `GET /api/auth/profile` | Activity for the profile page: repositories, commits indexed, questions, chats and the latest questions |
| `POST /api/auth/verify-email` · `POST /api/auth/resend-code` | Sign-up email code |
| `POST /api/auth/demo` | Open the read-only demo without an account (`GET /api/auth/config` says whether one is available) |
| `GET /api/auth/github/login` → `/callback` · `GET /api/auth/google/login` → `/callback` | GitHub App and Google sign-in (PKCE) |
| `GET /api/github/status` · `GET /api/github/repos` · `DELETE /api/github` | GitHub connection and the repositories a user shared |
| `GET /api/providers` | The five providers and this user's status for each |
| `PUT /api/providers/{id}/key` | Verify and save a key; returns the live model list |
| `GET /api/providers/{id}/models` | Live model list (`?refresh=true` bypasses the 10-minute cache) |
| `PUT /api/providers/{id}/model` · `PUT /api/providers/active` | Choose a model or the active provider |
| `POST /api/repos` · `GET /api/repos/{id}` · `POST /api/repos/{id}/resync` · `DELETE /api/repos/{id}` | Ingest and manage repositories (status is polled); `skip_commits` starts the window further back, so `max_commits` 200 with `skip_commits` 499 ingests commits 500 to 699 |
| `GET /api/repos/range-preview` | For a URL and a range: how many commits the repository has, and the commits at each end of the range |
| `GET /api/repos/{id}/overview` · `hotfiles` · `cochange` · `authors` · `pulls` · `commits` · `files` · `origins` | Analytics, including bug origins |
| `POST /api/repos/{id}/ask` | Ask a question; `conversation_id` continues a chat, leaving it out starts a new one |
| `POST /api/repos/{id}/ask/stream` | The same, as server-sent events: `sources` (what was found), `delta` (each new piece of the answer), then `done` (the saved exchange) or `error`. Setup problems, such as no model connected, are normal JSON errors |
| `POST /api/repos/{id}/ask/stopped` | Keep an answer the user stopped part-way: the page sends the text written so far and it's saved to the chat marked as stopped (if the answer had already finished, the complete one is kept instead) |
| `GET /api/repos/{id}/chats` · `GET`/`DELETE /api/repos/{id}/chats/{chat_id}` · `DELETE /api/repos/{id}/queries` | List chats, read one, delete one, or delete them all |
| `POST /api/repos/{id}/timeline` | Every commit that touched a file or folder, with a summary when a model is connected |
| `POST /api/repos/{id}/suspects` | Rank likely culprit commits for a bug report (`description`, optional `since` date) |
| `POST /api/repos/{id}/make-demo` · `GET /api/admin/demo` · `DELETE /api/admin/demo/{id}` | Admins: share a repository, with its chats, in the public demo; list or stop sharing |

## Testing

```bash
cd backend
python -m pytest
```

There are 194 backend tests and 10 frontend tests. GitHub Actions lints the backend with ruff (rules in [`backend/ruff.toml`](backend/ruff.toml)) and runs pytest, lints the frontend with ESLint and runs its Vitest component tests, type-checks and builds it, and scans both for known vulnerabilities, on every push to `main` and every pull request ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)). The tests replace the embedding model with a small stand-in, so CI installs only `requirements.txt`, without torch.

- **Auth:** sessions, cookie flags, rate limiting, admin handling, and signing out everywhere ending sessions on other devices.
- **Account security:** two-step sign-in (codes, replay, recovery codes, Google sign-in), identical replies for registered and unknown emails, password reset and change ending other sessions, weak passwords refused, key rotation for sessions and stored secrets, per-account limits on wrong passwords from many IPs, `X-Forwarded-For` ignored, cross-site writes refused, the activity log, account deletion, and ingests resuming after a restart.
- **Frontend:** password rules and the confirm field, model output never rendering HTML, and the two-step sign-in screen.
- **Commit ranges:** a range clones deep enough to reach it, reads exactly that window, keeps it on re-sync, and can't reach back further than 5,000 commits; pull requests newer than the range don't use up the pull request budget; the preview reads the commit count from GitHub's paging and stops at the oldest commit.
- **Profile:** activity counts and the latest questions, renaming, and blank names refused.
- **Demo:** only admins can share, and only public, ready repositories; visitors see the shared repository and its chats, every write is refused (including adding a key or deleting a chat), searches are capped per visitor, the demo account can't be signed into or claimed, and signing in with GitHub from the demo makes a real account instead of linking GitHub to the shared one.
- **Accounts:** email codes (hashing, expiry, attempt and resend limits), GitHub App sign-in, linking and token refresh, Google sign-in, pre-hijack protection, private-repo cloning, the Brevo request format and the startup check of the Brevo sender. All HTTP is mocked.
- **Security headers:** the website is served with a Content-Security-Policy whose script hashes match the inline scripts actually served, and with clickjacking protection.
- **Fair use and speed:** searches are capped per account, and a repository's history is parsed once and reused until it's re-synced.
- **Migrations:** a database created before migrations existed is stamped and upgraded in place, and questions asked before chats existed are grouped into one chat per repository.
- **Keys:** encryption, never echoing a key back, and per-user isolation.
- **Ingestion and analytics:** the full ingest-to-answer flow, chats (grouping, privacy, deletion), follow-up questions (rewritten with only the last three exchanges), streamed answers (event order, follow-ups, a provider failing halfway saves nothing, stopped answers are kept and never duplicated), limits, expiry cleanup and deletion of vectors.
- **Bug origins:** a real git repository built in the test traces a fix to the commit that introduced the bug, skips docs, tests and add-only fixes, and reports lines older than a shallow clone.
- **Who broke it?:** file names and stack-trace paths are read from a report and only real files count (not links or `module.attr`), code names are read from a report but links aren't, a commit that changed the code a report names or a larger change ranks higher, docs-only and unrelated commits are left out, the `since` date filters, and commits behind earlier bugs rank higher.
- **Search:** code is split into words, common words are skipped, the two rankings merge by position, and keywords find a commit the embedding ranked low.
- **Accuracy check:** the helpers that turn a repository's history into questions remove the answer's own PR text from the index and only use bug fixes from before each report, and find the GitHub issue a fix closes.
- **Provider adapters:** all five adapters run their **real SDKs against mocked HTTP**, with response bodies shaped like each provider's official API reference. This pins down exactly what is sent (for example, no `temperature` for Anthropic and OpenAI) and how responses and errors are parsed. Streaming is tested the same way, with event streams in each provider's documented format, including errors that arrive halfway through an answer.

For the frontend, run a type-check and production build:

```bash
cd frontend
npm run build
```

## Accuracy

How often does search find the right commit, and does Who broke it? point at the right culprit? Two scripts in [`backend/evals/`](backend/evals) measure both on real repositories, using questions and answers taken from their own history, so nothing is labelled by hand:

- **Search:** each merged pull request becomes a question (its title, or the first real sentence of its description), and the answer is the commit it belongs to. That PR text is removed from the index first, and the title is also cut from the commit message, so the answer can't simply match itself.
- **Who broke it?:** a fix is a commit whose pull request or message closes a GitHub issue. Bug origins traces what it changed back to the commit that last wrote those lines, which is the answer, and the report is the issue itself, its title and description as a user would paste them. Each case is ranked as of when the issue was opened, so only commits and fixes from before it count.

Latest run: the last 200 commits of `pallets/click`, `pallets/flask` and `encode/httpx`, with local BGE-small embeddings. Full tables are in [`backend/evals/RESULTS.md`](backend/evals/RESULTS.md).

| Search | Questions | Right commit first | In the top 3 | In the top 8 | MRR |
|---|---:|---:|---:|---:|---:|
| PR description questions, before | 263 | 38% | 47% | 55% | 0.43 |
| PR description questions, now | 263 | **49%** | **67%** | **78%** | **0.59** |
| PR title questions, before | 320 | 41% | 56% | 69% | 0.50 |
| PR title questions, now | 320 | **53%** | **70%** | **84%** | **0.63** |

What it shows:

- **What was wrong.** Search used to add 0.6 × the dense score to 0.4 × the keyword score. Dense scores among the candidates bunch together (a spread of about 0.08), while keyword scores divided by the best one spread across almost the whole 0 to 1 range, so in practice keywords decided the order. Words were also split on spaces, so `echo()` never matched "echo". The result was worse than dense search alone.
- **The fix.** Rank fusion merges the two rankings by position, keywords are matched over every commit instead of only the top 32 by meaning, code is split into words, and (with this local model) a keyword match counts three times a meaning match. It beats the old search for both question types in every repository, and beats dense search alone on every measure.
- **How the weight was chosen.** Weights from 1 to 10 were tried on click and flask, and 3 did best. On httpx, which wasn't used to choose it, weight 3 also beat weight 1 (the right commit in the top 8 for 76% of description questions instead of 70%), so the gain isn't luck. Stemming and giving the commit message extra weight were tried too and made no reliable difference, so they were left out.
- **The absolute numbers are pessimistic.** The PR text is removed from the index, and the local model reads only about 512 tokens of each commit. The comparisons between searches are the reliable part.

**With the live site's embedding model** (`run_eval --hosted`, Pinecone's llama-text-embed-v2, which reads about 2,048 tokens of each commit; full tables in [`backend/evals/RESULTS-hosted.md`](backend/evals/RESULTS-hosted.md)):

| Search, live model | Right commit first | In the top 3 | In the top 8 | MRR |
|---|---:|---:|---:|---:|
| PR description questions, before | 40% | 50% | 65% | 0.47 |
| PR description questions, now (keyword weight 1) | **54%** | **71%** | **81%** | **0.64** |
| PR title questions, before | 46% | 64% | 79% | 0.56 |
| PR title questions, now (keyword weight 1) | **59%** | **79%** | **89%** | **0.70** |

The live site does better than the local check suggested: the right commit is among the 8 sources for 81–89% of questions. The stronger model also shifts the best keyword weight: with it, dense search alone is much better than with the local model, and a keyword weight of 1 beat 3 on every measure (3 gave 81% / 87% in the top 8, MRR 0.62 / 0.66). So the weight now follows the model: 1 with Pinecone's embeddings, 3 with the local ones.

### Who broke it? on real bug reports

[`backend/evals/bug_reports.py`](backend/evals/bug_reports.py), on the last 1,000 commits of the same three repositories. Full tables, including each signal switched off in turn, are in [`backend/evals/RESULTS-bug-reports.md`](backend/evals/RESULTS-bug-reports.md).

| Who broke it?, 49 real bug reports | Cause first | In the top 3 | In the top 10 | MRR |
|---|---:|---:|---:|---:|
| The app now | **35%** | **57%** | **61%** | **0.46** |
| The app before (search, files named, type of change, earlier bugs) | 27% | 43% | 55% | 0.36 |
| Description match only | 24% | 35% | 53% | 0.32 |
| Baseline: newest commit first | 2% | 6% | 10% | 0.04 |

Across all 123 issues, bug reports or not, the cause is first for 22% and in the top 3 for 43% (35% before).

- **First, the test was fixed.** In 43 of 166 traced issues, tracing pointed at a commit made after the issue was opened, which can't be the cause, so the earlier version of this test was grading against wrong answers. Each case is now ranked as of when its issue was opened, and those cases are left out. Many issues that a pull request closes are also feature requests, where "who broke it" has no answer, so results are reported for the 49 real bug reports (labelled as a bug, closed by a fix, or with a traceback) and for every issue.
- **Then the ranking.** Looking at the misses showed what was going wrong. Most "file names" in reports were links or `module.attr` names, which diluted the file signal. Commits behind earlier bugs were under-weighted. And large changes kept turning out to be the cause, which matches defect-prediction research. So only real file names count now, the diff is checked for code the report names, larger changes and recent ones get a boost, and commits that only changed docs or tests are left out. Each signal adds something: switching off the change size alone drops the top 3 from 57% to 49%.
- **Checked on unseen data.** The new signals were chosen by tuning on two repositories and testing on the third, in turn. Change size and a small recency boost helped in every split. Weights that only did better on the data they were tuned on were dropped.
- **How it compares.** [Locus](https://cse.hkust.edu.hk/faculty/scc/publ/ase16-Locus-preprint.pdf) (ASE 2016), a research tool for the same task (ranking commits from a bug report's text), reported the cause in the top 5 for 41% and the top 10 for 51% of 709 bug reports from six Java projects, with an MRR of 0.26. Here it's 46% in the top 5 and 56% in the top 10 across all 123 issues (MRR 0.34), and higher on real bug reports. The projects and sizes differ, and this test ranks among at most 1,000 recent commits, so it's not a head-to-head result, but it puts these numbers in the same range as published work.
- **What it means in use.** For a bit over half of real bug reports, the cause is among the three suspects shown. 49 cases is a small sample, so the top-3 figure could be several points either way.

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

On the number that matters most, search went from weak (55% in the top 8) to good (78–84%). Putting the right commit first (49–53%, MRR 0.59–0.63) is between OK and good, which is where a reranker would help most. For Who broke it?, which shows three suspects, good means the cause is in the top 3 for about half of real bug reports and very good means 60% or more. On 49 real bug reports it's at 57%, good and close to very good.

Next steps toward very good:

1. **Rerank the top results** with a model that reads the question and each commit together (a cross-encoder). Pinecone hosts one (`bge-reranker-v2-m3`), but its free plan allows about 500 rerank requests a month, so search would need to fall back when they run out.
2. **Help Who broke it? with the stronger model and a reranker too.** Its description match uses the same search, so both should lift it.
3. **Test Who broke it? on more projects.** 49 bug reports is enough to show the ranking works, but more would make the number firmer.

Run it yourself (needs `requirements-local.txt` for the embedding model; about 20 minutes the first time and 10 after that, and it never touches Pinecone, the database or `GITHUB_TOKEN`):

```bash
cd backend
python -m evals.run_eval
```

To check search with the live site's embedding model instead, add `--hosted`. It uses `PINECONE_API_KEY` from `backend/.env`, works in a separate throwaway index that is deleted at the end (the production index is never touched), and checks search only, writing `evals/RESULTS-hosted.md`. One run embeds about 600 commits, roughly 0.6M of the 5M embedding tokens Pinecone's free plan allows each month. Searches fetch only commit IDs and scores from Pinecone, so most of the time goes to embedding the commits.

```bash
python -m evals.run_eval --hosted
```

Who broke it? on real bug reports (local embeddings; reads public pull requests and issues from GitHub, using `GITHUB_TOKEN` from `backend/.env` when it's set, and caches them; about 40 minutes the first time):

```bash
python -m evals.bug_reports
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
