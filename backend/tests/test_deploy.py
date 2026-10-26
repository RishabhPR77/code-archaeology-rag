import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.config import get_settings
from app.db import Base, engine, init_db


def test_pre_migration_database_is_upgraded_in_place():
    """The live DB was built by create_all before Alembic; startup must stamp and upgrade it."""
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
        c.exec_driver_sql("""CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(320) NOT NULL UNIQUE,
            name VARCHAR(120) NOT NULL, password_hash VARCHAR(100), github_id INTEGER UNIQUE,
            github_login VARCHAR(100), github_token_enc TEXT, avatar_url VARCHAR(500), is_admin BOOLEAN NOT NULL,
            active_provider VARCHAR(32), created_at DATETIME NOT NULL)""")
        c.exec_driver_sql("""CREATE TABLE repos (id VARCHAR(32) PRIMARY KEY, user_id INTEGER NOT NULL,
            url VARCHAR(300) NOT NULL, full_name VARCHAR(200) NOT NULL, namespace VARCHAR(200) NOT NULL UNIQUE,
            max_commits INTEGER NOT NULL, status VARCHAR(20) NOT NULL, stage_message VARCHAR(300) NOT NULL,
            error TEXT, warnings TEXT NOT NULL, commit_count INTEGER NOT NULL, pr_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL, ready_at DATETIME, expires_at DATETIME)""")
        c.exec_driver_sql("INSERT INTO users (email, name, is_admin, created_at) "
                          "VALUES ('existing@example.com', 'Existing', 0, '2026-10-01')")
    init_db()
    init_db()  # every later start is a no-op
    with engine.connect() as c:
        assert c.execute(text("select version_num from alembic_version")).scalar() == "0002"
        assert c.execute(text("select email_verified from users")).scalar() == 1   # existing users stay in
    assert "email_verifications" in inspect(engine).get_table_names()
    assert "is_private" in {col["name"] for col in inspect(engine).get_columns("repos")}


@pytest.mark.parametrize("given, expected", [
    ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require", "postgresql+psycopg://u:p@ep-x.neon.tech/db?sslmode=require"),
    ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
    ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
])
def test_hosted_postgres_urls_use_psycopg(monkeypatch, given, expected):
    monkeypatch.setattr(get_settings(), "database_url", given)
    assert get_settings().db_url == expected


def test_single_container_serves_spa(monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<div id=root></div>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path.parent / "secret.txt").write_text("nope")
    monkeypatch.setattr(get_settings(), "static_dir", tmp_path)

    from app.main import create_app
    with TestClient(create_app()) as c:
        assert c.get("/api/health").json() == {"status": "ok"}
        assert c.head("/api/health").status_code == 200                 # uptime monitors use HEAD
        assert c.head("/").status_code == 200
        assert c.head("/app/repos/abc").status_code == 200
        assert c.get("/api/does-not-exist").status_code == 404          # API 404s stay JSON
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        deep = c.get("/app/repos/abc/ask")                                # client-side route
        assert deep.status_code == 200 and "root" in deep.text
        assert deep.headers["cache-control"] == "no-cache"
        assert deep.headers["x-content-type-options"] == "nosniff"
        assert "nope" not in c.get("/../secret.txt").text                 # no path traversal
        assert "nope" not in c.get("/%2e%2e/secret.txt").text
