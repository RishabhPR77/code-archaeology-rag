# app/main.py
import asyncio
import base64
import hashlib
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager, suppress

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import account, admin, analytics, auth, chats, github, oauth_login, providers, repos
from app.db import SessionLocal
from app.deps import prune_rate_limits
from app.services import audit, ingest, mailer, rotation

log = logging.getLogger(__name__)
CLEANUP_INTERVAL = 15 * 60
SLOW_REQUEST = 3.0   # seconds; a streamed answer counts only until its headers are sent


def _configure_logging():
    """Uvicorn only sets up its own loggers; give the app's an INFO handler in the same style."""
    app_log = logging.getLogger("app")
    if not app_log.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-9s %(name)s: %(message)s"))
        app_log.addHandler(handler)
        app_log.setLevel(logging.INFO)
        app_log.propagate = False


def _prune_events():
    with SessionLocal() as db:
        audit.prune(db)


async def _cleanup_loop():
    while True:
        try:
            removed = await asyncio.to_thread(ingest.cleanup_expired)
            if removed:
                log.info("Removed %d expired repositories", removed)
            await asyncio.to_thread(prune_rate_limits)
            await asyncio.to_thread(_prune_events)
        except Exception:
            log.exception("Expired-repo cleanup failed")
        await asyncio.sleep(CLEANUP_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ingest.resume_interrupted()
    rotation.reencrypt_stored_secrets()
    sender_check = None
    if get_settings().email_delivery == "brevo":
        # Off the startup path: a slow or failing Brevo call only produces a log line.
        # Holding the reference keeps the task from being garbage-collected mid-run.
        sender_check = asyncio.create_task(asyncio.to_thread(mailer.check_sender))
    task = asyncio.create_task(_cleanup_loop())
    yield
    if sender_check is not None:
        sender_check.cancel()
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def create_app() -> FastAPI:
    _configure_logging()
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_name} API", version="2.0.0", lifespan=lifespan,
                  docs_url=None if settings.is_production else "/api/docs",
                  redoc_url=None, openapi_url=None if settings.is_production else "/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    allowed_origins = {o.rstrip("/") for o in settings.cors_origin_list}

    @app.middleware("http")
    async def same_origin_writes(request: Request, call_next):
        """Refuse changes sent from another site's page. SameSite cookies already stop most of these
        (CSRF); checking the Origin header as well means one browser quirk can't undo it."""
        origin = request.headers.get("origin")
        if (request.method not in ("GET", "HEAD", "OPTIONS") and request.url.path.startswith("/api/")
                and origin and origin.rstrip("/") not in allowed_origins):
            return JSONResponse({"detail": "Requests from other sites aren't allowed."}, status_code=403)
        return await call_next(request)

    @app.middleware("http")
    async def request_log(request: Request, call_next):
        """Give every request an ID (sent back as X-Request-ID) and log the slow or failing ones,
        so a user's error report can be matched to the server log."""
        request_id = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("Request %s %s %s failed", request_id, request.method, request.url.path)
            raise
        took = time.perf_counter() - started
        if response.status_code >= 500 or took > SLOW_REQUEST:
            log.warning("Request %s %s %s -> %s in %.1fs", request_id, request.method, request.url.path,
                        response.status_code, took)
        response.headers["X-Request-ID"] = request_id
        return response
    app.include_router(auth.router)
    app.include_router(account.router)
    app.include_router(oauth_login.router)
    app.include_router(github.router)
    app.include_router(providers.router)
    app.include_router(repos.router)
    app.include_router(analytics.router)
    app.include_router(chats.router)
    app.include_router(admin.router)

    # HEAD too: uptime monitors (often used to keep free hosts awake) send HEAD by default
    @app.api_route("/api/health", methods=["GET", "HEAD"], tags=["meta"])
    def health():
        return {"status": "ok"}

    if settings.static_dir:
        _serve_frontend(app, settings.static_dir)
    return app


_INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL)


def content_security_policy(index_html: str) -> str:
    """Which sources the browser may load. Scripts: only this site's bundle, plus each inline script in
    index.html allowed by the hash of its exact text, so injected script can't run."""
    hashes = [base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode()
              for m in _INLINE_SCRIPT.finditer(index_html)]
    return "; ".join([
        "default-src 'self'",
        "script-src " + " ".join(["'self'", *(f"'sha256-{h}'" for h in hashes)]),
        "style-src 'self' 'unsafe-inline'",   # React, charts and toasts set inline styles
        "img-src 'self' data: https://github.com https://avatars.githubusercontent.com https://*.googleusercontent.com",
        "font-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",             # no other site may embed the app (clickjacking)
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


def _serve_frontend(app: FastAPI, static_dir: Path):
    """Serve the built React app from the API itself — one origin, one port."""
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR={static_dir} has no index.html — build the frontend first")

    csp = content_security_policy(index.read_text(encoding="utf-8"))
    production = get_settings().is_production

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", csp)
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if production:   # the live site is HTTPS only; tell browsers never to use plain HTTP for it
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Hashed asset names, so they can be cached forever
    app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        file = (root / path).resolve()
        if path and file.is_file() and file.is_relative_to(root):
            return FileResponse(file)
        # Client-side routes all load the app shell
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
