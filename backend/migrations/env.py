"""Alembic environment. The database URL always comes from the app's settings."""
from alembic import context
from sqlalchemy import engine_from_config, pool

from app import models  # noqa: F401 — registers tables on Base.metadata
from app.config import get_settings
from app.db import Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    # Callers (app startup, tests) may pass a URL explicitly; otherwise use settings
    return config.get_main_option("sqlalchemy.url") or get_settings().db_url


def run_migrations_offline():
    url = _url()
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True,
                      render_as_batch=url.startswith("sqlite"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is not None:
        _run(connection)
        return
    engine = engine_from_config({"sqlalchemy.url": _url()}, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        _run(conn)


def _run(connection):
    # SQLite can't ALTER most things in place; batch mode rebuilds tables instead
    context.configure(connection=connection, target_metadata=target_metadata,
                      render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
