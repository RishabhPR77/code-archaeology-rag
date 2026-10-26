from types import SimpleNamespace

import pytest

from app.services import ingest
from ingestion.git_loader import CommitRecord
from ingestion.github_enricher import FetchResult, PRRecord


def _commit(sha, msg, author, ts, files):
    return CommitRecord(sha=sha * 8, message=msg, author=author, email=f"{author}@x.io", timestamp=ts,
                        files_changed=files, insertions=10, deletions=2, diff="+ code", parent_shas=[])


COMMITS = [
    _commit("a1b2c3d4e", "fix session cookie expiry bug", "alice", "2026-01-05T10:00:00", ["src/sessions.py"]),
    _commit("b2c3d4e5f", "add oauth login feature", "bob", "2026-01-12T10:00:00", ["src/auth.py", "src/sessions.py"]),
    _commit("c3d4e5f6a", "refactor auth module", "alice", "2026-02-01T10:00:00", ["src/auth.py", "README.md"]),
]
PR = PRRecord(number=42, title="add oauth login feature", body="Adds OAuth so users can sign in.",
              author="bob", merge_commit_sha="b2c3d4e5f" * 8, merged_at="2026-01-12T10:00:00",
              labels=["auth"], linked_issues=[], review_comments=[], review_summaries=[], discussion=[])


@pytest.fixture(autouse=True)
def fake_ingestion(monkeypatch):
    monkeypatch.setattr(ingest.git.Repo, "clone_from", lambda *a, **k: None)
    monkeypatch.setattr(ingest, "load_commits", lambda path, max_count: COMMITS)
    monkeypatch.setattr(ingest, "fetch_prs", lambda *a, **k: FetchResult(prs=[PR], warnings=[]))


def _ready_repo(client):
    r = client.post("/api/repos", json={"url": "https://github.com/pallets/flask", "max_commits": 50})
    assert r.status_code == 202, r.text
    repo = client.get(f"/api/repos/{r.json()['id']}").json()
    assert repo["status"] == "ready", repo
    return repo


def _connect_model(client):
    client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    client.put("/api/providers/anthropic/model", json={"model": "claude-test-1"})


def test_ingest_runs_and_analytics_work(user_client):
    repo = _ready_repo(user_client)
    assert repo["full_name"] == "pallets/flask"
    assert repo["commit_count"] == 3 and repo["pr_count"] == 1
    rid = repo["id"]

    overview = user_client.get(f"/api/repos/{rid}/overview").json()
    assert overview["commits"] == 3 and overview["authors"] == 2 and overview["prs"] == 1

    hot = user_client.get(f"/api/repos/{rid}/hotfiles").json()
    assert {h["file"] for h in hot[:2]} == {"src/sessions.py", "src/auth.py"}

    pairs = user_client.get(f"/api/repos/{rid}/cochange").json()
    assert {"file_a": "src/auth.py", "file_b": "src/sessions.py", "co_changes": 1} in pairs

    authors = user_client.get(f"/api/repos/{rid}/authors").json()
    assert authors[0]["author"] == "alice" and authors[0]["commits"] == 2

    pulls = user_client.get(f"/api/repos/{rid}/pulls").json()
    assert pulls == [{"number": 42, "title": "add oauth login feature", "author": "bob",
                      "merged_at": "2026-01-12T10:00:00", "labels": ["auth"],
                      "commit_sha": "b2c3d4e", "files": ["src/auth.py", "src/sessions.py"]}]

    commits = user_client.get(f"/api/repos/{rid}/commits").json()
    assert [c["type"] for c in commits] == ["refactor", "feat", "fix"]


def test_rejects_non_github_urls(user_client):
    for url in ("https://gitlab.com/a/b", "github.com/a", "file:///etc/passwd", "https://github.com/a/b/c"):
        assert user_client.post("/api/repos", json={"url": url}).status_code == 422, url


def test_ask_requires_model_then_uses_users_provider(user_client):
    rid = _ready_repo(user_client)["id"]
    assert user_client.post(f"/api/repos/{rid}/ask", json={"question": "why oauth?"}).status_code == 409

    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/ask", json={"question": "why was oauth login added?", "mode": "bullets"})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["answer"].startswith("Answer from claude-test-1")
    assert q["provider"] == "anthropic" and q["model"] == "claude-test-1"
    assert q["sources"] and q["sources"][0]["sha"]

    from tests.conftest import FakeProvider
    prompt = FakeProvider.calls[-1]["prompt"]
    assert "Adds OAuth so users can sign in." in prompt      # PR description reaches the LLM
    assert "concise bullet point list" in prompt

    history = user_client.get(f"/api/repos/{rid}/queries").json()
    assert [h["question"] for h in history] == ["why was oauth login added?"]
    assert user_client.delete(f"/api/repos/{rid}/queries").status_code == 204
    assert user_client.get(f"/api/repos/{rid}/queries").json() == []


def test_only_pr_filter(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    q = user_client.post(f"/api/repos/{rid}/ask", json={"question": "what changed in sessions?", "only_pr": True}).json()
    assert q["sources"] and all(s["has_pr"] for s in q["sources"])


def test_timeline(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/timeline", json={"path": "sessions.py"}).json()
    assert [e["sha"] for e in r["entries"]] == ["a1b2c3d", "b2c3d4e"]
    assert r["answer"].startswith("Answer from")
    empty = user_client.post(f"/api/repos/{rid}/timeline", json={"path": "nope.py"}).json()
    assert empty["entries"] == [] and empty["answer"] is None


def test_repos_are_private_per_user(client):
    from tests.conftest import register
    register(client, email="owner@example.com")
    rid = _ready_repo(client)["id"]
    client.post("/api/auth/logout")
    register(client, email="intruder@example.com")
    assert client.get(f"/api/repos/{rid}").status_code == 404
    assert client.delete(f"/api/repos/{rid}").status_code == 404
    assert client.get("/api/repos").json() == []


def test_limits_on_repo_count_and_commits(user_client):
    assert user_client.post("/api/repos", json={"url": "https://github.com/a/b", "max_commits": 500}).status_code == 403
    _ready_repo(user_client)
    _ready_repo(user_client)
    r = user_client.post("/api/repos", json={"url": "https://github.com/a/c", "max_commits": 50})
    assert r.status_code == 403 and "up to 2" in r.json()["detail"]


def test_daily_limit_survives_deletion(user_client):
    for _ in range(3):
        rid = _ready_repo(user_client)["id"]
        user_client.delete(f"/api/repos/{rid}")
    r = user_client.post("/api/repos", json={"url": "https://github.com/a/b", "max_commits": 50})
    assert r.status_code == 429


def test_delete_removes_vectors(user_client):
    from storage.vector_store import VectorStore
    repo = _ready_repo(user_client)
    rid = repo["id"]
    from app.db import SessionLocal
    from app.models import Repo
    with SessionLocal() as db:
        ns = db.get(Repo, rid).namespace
    assert VectorStore(ns).search("oauth", top_k=3)
    assert user_client.delete(f"/api/repos/{rid}").status_code == 204
    assert VectorStore(ns).search("oauth", top_k=3) == []


def test_failed_clone_reports_friendly_error(user_client, monkeypatch):
    def boom(*a, **k):
        raise ingest.git.GitCommandError("clone", 128)
    monkeypatch.setattr(ingest.git.Repo, "clone_from", boom)
    r = user_client.post("/api/repos", json={"url": "https://github.com/no/such-repo", "max_commits": 50})
    repo = user_client.get(f"/api/repos/{r.json()['id']}").json()
    assert repo["status"] == "failed" and "public" in repo["error"]


def test_expired_repos_are_cleaned_up(user_client):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models import Repo, utcnow
    rid = _ready_repo(user_client)["id"]
    with SessionLocal() as db:
        db.get(Repo, rid).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert ingest.cleanup_expired() == 1
    assert user_client.get(f"/api/repos/{rid}").status_code == 404
