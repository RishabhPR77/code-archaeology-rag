# app/db.py
from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import BACKEND_DIR, get_settings

# The schema create_all produced before migrations existed
BASELINE_REVISION = "0001"


class Base(DeclarativeBase):
    pass


def _make_engine():
    settings = get_settings()
    url = settings.db_url
    if url.startswith("sqlite"):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(conn, _):
            cur = conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")   # readers don't block the ingest writer
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

        return engine
    # connect_timeout bounds each address attempt, so a dead IPv6 route falls back to IPv4
    # instead of hanging; pre-ping replaces connections Neon closed while scaled to zero
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def _alembic(connection):
    from alembic.config import Config
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def init_db():
    """Bring the schema up to date. Safe to run on every start."""
    from alembic import command
    from sqlalchemy import inspect

    with engine.begin() as conn:
        cfg = _alembic(conn)
        tables = set(inspect(conn).get_table_names())
        if "users" in tables and "alembic_version" not in tables:
            # Created by create_all before migrations existed — that is the baseline
            command.stamp(cfg, BASELINE_REVISION)
        command.upgrade(cfg, "head")


def stamp_head():
    """Mark a schema built with create_all (tests) as current."""
    from alembic import command
    with engine.begin() as conn:
        command.stamp(_alembic(conn), "head")
