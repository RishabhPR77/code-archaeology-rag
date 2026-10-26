import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


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
        assert c.get("/api/does-not-exist").status_code == 404          # API 404s stay JSON
        assert c.get("/assets/app.js").text == "console.log(1)"
        assert c.get("/favicon.svg").text == "<svg/>"
        deep = c.get("/app/repos/abc/ask")                                # client-side route
        assert deep.status_code == 200 and "root" in deep.text
        assert deep.headers["cache-control"] == "no-cache"
        assert deep.headers["x-content-type-options"] == "nosniff"
        assert "nope" not in c.get("/../secret.txt").text                 # no path traversal
        assert "nope" not in c.get("/%2e%2e/secret.txt").text
