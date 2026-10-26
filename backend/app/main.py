# app/main.py
import asyncio
import logging
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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

    @app.get("/api/health", tags=["meta"])
    def health():
        return {"status": "ok"}

    return app


app = create_app()
