# app/config.py
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve paths from the backend folder so the API runs from any working directory
BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    app_name: str = "Code Archaeologist"
    environment: Literal["development", "production"] = "development"

    # Secrets — both required. See .env.example for how to generate them.
    secret_key: str = Field(min_length=32)        # signs session JWTs
    encryption_key: str = Field(min_length=44)    # Fernet key that encrypts user API keys

    data_dir: Path = BACKEND_DIR / "data"
    database_url: str = ""                        # empty -> SQLite file in data_dir
    static_dir: Path | None = None                # built React app to serve (single-container deploys)

    # Where the React app lives — used for OAuth redirects and CORS.
    # Empty -> Render's RENDER_EXTERNAL_URL if present, else the Vite dev server.
    frontend_url: str = ""
    render_external_url: str = ""                 # set by Render on every service
    cors_origins: str = ""                        # comma-separated extra origins
    session_ttl_hours: int = 24 * 7

    # Server-owned infrastructure (users only bring their LLM key)
    pinecone_api_key: str = ""                    # empty -> local vector store (dev/tests)
    pinecone_index: str = "code-archaeologist"
    github_token: str = ""                        # fallback for PR fetching

    # "local" runs BGE-small in-process (~550 MB RAM, needs torch);
    # "pinecone" uses Pinecone's hosted embeddings so the API fits 512 MB hosts
    embedding_provider: Literal["local", "pinecone"] = "local"
    embedding_model: str = "llama-text-embed-v2"  # used when embedding_provider=pinecone

    # GitHub OAuth app — both empty disables "Sign in with GitHub"
    github_client_id: str = ""
    github_client_secret: str = ""

    # Usage limits (admins bypass them)
    admin_emails: str = ""                        # comma-separated
    max_commits: int = 100
    max_repos_per_user: int = 5
    max_ingests_per_day: int = 5
    repo_ttl_hours: int = 72                      # 0 keeps repos forever
    max_concurrent_ingests: int = 2

    @model_validator(mode="after")
    def _derive(self):
        if not self.frontend_url:
            self.frontend_url = self.render_external_url or "http://localhost:5173"
        self.frontend_url = self.frontend_url.rstrip("/")
        if self.embedding_provider == "pinecone" and not self.pinecone_api_key:
            raise ValueError("EMBEDDING_PROVIDER=pinecone needs PINECONE_API_KEY")
        return self

    @property
    def db_url(self) -> str:
        url = self.database_url
        if not url:
            return f"sqlite:///{(self.data_dir / 'app.db').as_posix()}"
        # Hosted Postgres (Neon, Supabase...) hands out driverless URLs; use psycopg 3
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def github_oauth_enabled(self) -> bool:
        return bool(self.github_client_id and self.github_client_secret)

    @property
    def admin_email_set(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        extra = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return [self.frontend_url, *extra]


@lru_cache
def get_settings() -> Settings:
    return Settings()
