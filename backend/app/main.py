# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import init_db
from app.routers import auth, providers, repos
from app.services import ingest

log = logging.getLogger(__name__)
CLEANUP_INTERVAL = 15 * 60


async def _cleanup_loop():
    while True:
        try:
            removed = await asyncio.to_thread(ingest.cleanup_expired)
            if removed:
                log.info("Removed %d expired repositories", removed)
        except Exception:
            log.exception("Expired-repo cleanup failed")
        await asyncio.sleep(CLEANUP_INTERVAL)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    ingest.mark_interrupted()
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=f"{settings.app_name} API", version="2.0.0", lifespan=lifespan,
                  docs_url=None if settings.is_production else "/api/docs",
                  redoc_url=None, openapi_url=None if settings.is_production else "/api/openapi.json")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origin_list,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.include_router(auth.router)
    app.include_router(providers.router)
    app.include_router(repos.router)

    # HEAD too: uptime monitors (often used to keep free hosts awake) send HEAD by default
    @app.api_route("/api/health", methods=["GET", "HEAD"], tags=["meta"])
    def health():
        return {"status": "ok"}

    if settings.static_dir:
        _serve_frontend(app, settings.static_dir)
    return app


def _serve_frontend(app: FastAPI, static_dir: Path):
    """Serve the built React app from the API itself — one origin, one port."""
    root = static_dir.resolve()
    index = root / "index.html"
    if not index.is_file():
        raise RuntimeError(f"STATIC_DIR={static_dir} has no index.html — build the frontend first")

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
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
