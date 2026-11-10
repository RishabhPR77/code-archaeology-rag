"""The public demo: an admin shares a repository, and visitors explore it without signing up, read-only."""
import pytest
from sqlalchemy import select

from app import deps
from app.db import SessionLocal
from app.models import Repo, User
from app.services.demo import DEMO_EMAIL
from tests.conftest import register
from tests.test_accounts import oauth_round_trip, web  # noqa: F401  (web is a fixture)
from tests.test_repos import _connect_model, _ready_repo, fake_ingestion  # noqa: F401  (fake_ingestion is a fixture)


def _share_a_repo(client) -> str:
    """Sign up as the admin, ingest a repo, ask one question, share it, then leave like a visitor would."""
    register(client, email="admin@example.com")
    rid = _ready_repo(client)["id"]
    _connect_model(client)
    assert client.post(f"/api/repos/{rid}/ask", json={"question": "why was oauth login added?"}).status_code == 200
    assert client.post(f"/api/repos/{rid}/make-demo").status_code == 204
    client.cookies.clear()
    return rid


def _visit(client):
    r = client.post("/api/auth/demo")
    assert r.status_code == 200, r.text
    return r.json()["user"]


def test_no_demo_until_an_admin_shares_a_repo(client):
    assert client.get("/api/auth/config").json()["demo_available"] is False
    assert client.post("/api/auth/demo").status_code == 404


def test_visitors_explore_the_shared_repo_and_its_chats(client):
    rid = _share_a_repo(client)
    assert client.get("/api/auth/config").json()["demo_available"] is True

    me = _visit(client)
    assert me["is_demo"] is True and me["active_provider"] is None
    assert [r["id"] for r in client.get("/api/repos").json()] == [rid]
    assert client.get(f"/api/repos/{rid}/overview").json()["commits"] == 3
    chats = client.get(f"/api/repos/{rid}/chats").json()
    assert len(chats) == 1
    messages = client.get(f"/api/repos/{rid}/chats/{chats[0]['id']}").json()
    assert messages[0]["question"] == "why was oauth login added?" and messages[0]["answer"]

    # Who broke it? ranks without a model, and a file's commits are listed without a summary
    r = client.post(f"/api/repos/{rid}/suspects", json={"description": "session cookie expires too early"})
    assert r.status_code == 200 and r.json()["suspects"] and r.json()["answer"] is None
    t = client.post(f"/api/repos/{rid}/timeline", json={"path": "sessions.py"}).json()
    assert [e["sha"] for e in t["entries"]] == ["a1b2c3d", "b2c3d4e"] and t["answer"] is None


@pytest.mark.parametrize("method, path, body", [
    ("post", "/api/repos/{rid}/ask", {"question": "why?"}),
    ("post", "/api/repos/{rid}/ask/stream", {"question": "why?"}),
    ("post", "/api/repos/{rid}/ask/stopped", {"question": "why?", "answer": "Because"}),
    ("delete", "/api/repos/{rid}/chats/{chat}", None),
    ("delete", "/api/repos/{rid}/queries", None),
    ("post", "/api/repos/{rid}/resync", None),
    ("delete", "/api/repos/{rid}", None),
    ("post", "/api/repos/{rid}/make-demo", None),
    ("post", "/api/repos", {"url": "https://github.com/pallets/click", "max_commits": 50}),
    ("put", "/api/providers/anthropic/key", {"api_key": "good-key-1234"}),
    ("delete", "/api/github", None),
    ("patch", "/api/auth/me", {"name": "Someone else"}),
])
def test_the_demo_cannot_change_anything(client, method, path, body):
    rid = _share_a_repo(client)
    _visit(client)
    chat = client.get(f"/api/repos/{rid}/chats").json()[0]["id"]
    r = client.request(method.upper(), path.format(rid=rid, chat=chat), json=body)
    assert r.status_code == 403 and "read-only demo" in r.json()["detail"], r.text
    assert len(client.get(f"/api/repos/{rid}/chats").json()) == 1
    assert client.get(f"/api/repos/{rid}").json()["status"] == "ready"


def test_demo_searches_are_capped_per_visitor(client, monkeypatch):
    rid = _share_a_repo(client)
    _visit(client)
    monkeypatch.setattr(deps.demo_limiter, "limit", 2)
    ask = lambda: client.post(f"/api/repos/{rid}/suspects", json={"description": "cookie bug"})  # noqa: E731
    assert ask().status_code == 200 and ask().status_code == 200
    r = ask()
    assert r.status_code == 429 and "Sign up free" in r.json()["detail"]


def test_the_demo_account_cannot_be_signed_into_or_claimed(client):
    _share_a_repo(client)
    r = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": "correct-horse-battery"})
    assert r.status_code == 401
    r = client.post("/api/auth/register", json={"email": DEMO_EMAIL, "password": "correct-horse-battery"})
    assert r.status_code in (409, 422)


def test_github_sign_in_from_the_demo_makes_a_real_account(client, web):  # noqa: F811
    _share_a_repo(client)
    _visit(client)
    r = oauth_round_trip(client, "github")
    assert r.headers["location"].endswith("/app")       # signed in as a new account, not "connected"
    assert client.get("/api/auth/me").json()["user"]["email"] == "octo@example.com"
    with SessionLocal() as db:
        demo_user = db.scalar(select(User).where(User.is_demo.is_(True)))
        assert demo_user.github_id is None and demo_user.github_token_enc is None


def test_only_admins_share_and_only_public_ready_repos(client):
    register(client)
    rid = _ready_repo(client)["id"]
    assert client.post(f"/api/repos/{rid}/make-demo").status_code == 403
    assert client.get("/api/admin/demo").status_code == 403

    client.cookies.clear()
    register(client, email="admin@example.com")
    rid = _ready_repo(client)["id"]
    with SessionLocal() as db:
        db.get(Repo, rid).is_private = True
        db.commit()
    r = client.post(f"/api/repos/{rid}/make-demo")
    assert r.status_code == 409 and "Private" in r.json()["detail"]
    with SessionLocal() as db:
        repo = db.get(Repo, rid)
        repo.is_private, repo.status = False, "embedding"
        db.commit()
    assert client.post(f"/api/repos/{rid}/make-demo").status_code == 409


def test_admins_can_stop_sharing_and_get_the_repo_back(client):
    rid = _share_a_repo(client)
    client.post("/api/auth/login", json={"email": "admin@example.com", "password": "correct-horse-battery"})
    assert client.get("/api/repos").json() == []
    assert [r["id"] for r in client.get("/api/admin/demo").json()] == [rid]
    with SessionLocal() as db:
        assert db.get(Repo, rid).expires_at is None          # the cleanup never removes the demo

    assert client.delete(f"/api/admin/demo/{rid}").status_code == 204
    assert [r["id"] for r in client.get("/api/repos").json()] == [rid]
    assert len(client.get(f"/api/repos/{rid}/chats").json()) == 1      # with its chats
    assert client.get("/api/admin/demo").json() == []
    assert client.delete(f"/api/admin/demo/{rid}").status_code == 404
    assert client.get("/api/auth/config").json()["demo_available"] is False
