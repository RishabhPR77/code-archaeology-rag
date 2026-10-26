"""Email codes, GitHub App sign-in/linking/repo access, Google sign-in — HTTP fully mocked."""
import json
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal
from app.models import EmailVerification, User, utcnow
from app.security import SESSION_COOKIE, decrypt_secret
from app.services import github, mailer, oauth
from app.services import ingest as ingest_service
from ingestion.github_enricher import FetchResult
from tests.conftest import register


# ── Fake GitHub / Google / Brevo ──────────────────────────────────
class FakeWeb:
    def __init__(self):
        self.calls, self.emails = [], []
        self.github_user = {"id": 42, "login": "octo", "name": "Octo Cat", "avatar_url": "https://a/octo.png"}
        self.github_email = "octo@example.com"
        self.google_user = {"sub": "g-123", "email": "ada@example.com", "email_verified": True,
                            "name": "Ada", "picture": "https://a/ada.png"}
        self.access = "ghu_A"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url, auth = str(request.url), request.headers.get("authorization", "")
        self.calls.append((request.method, url))
        form = parse_qs(request.content.decode()) if request.method == "POST" else {}
        if url == github.TOKEN_URL:
            if form.get("grant_type") == ["refresh_token"]:
                if form.get("refresh_token") != ["ghr_R"]:
                    return httpx.Response(200, json={"error": "bad_refresh_token"})
                self.access = "ghu_B"
                return httpx.Response(200, json={"access_token": "ghu_B", "expires_in": 28800,
                                                 "refresh_token": "ghr_R2", "refresh_token_expires_in": 15897600})
            if form.get("code") != ["good"] or not form.get("code_verifier"):
                return httpx.Response(200, json={"error": "bad_verification_code"})
            return httpx.Response(200, json={"access_token": "ghu_A", "expires_in": 28800,
                                             "refresh_token": "ghr_R", "refresh_token_expires_in": 15897600})
        if url.startswith(github.API):
            if auth != f"Bearer {self.access}":
                return httpx.Response(401, json={"message": "Bad credentials"})
            path = url.removeprefix(github.API).split("?")[0]
            if path == "/user":
                return httpx.Response(200, json=self.github_user)
            if path == "/user/emails":
                return httpx.Response(200, json=[{"email": self.github_email, "primary": True, "verified": True}])
            if path == "/user/installations":
                return httpx.Response(200, json={"installations": [{
                    "id": 7, "account": {"login": "octo"}, "repository_selection": "selected",
                    "html_url": "https://github.com/settings/installations/7"}]})
            if path == "/user/installations/7/repositories":
                return httpx.Response(200, json={"repositories": [
                    {"full_name": "octo/secret", "private": True, "html_url": "https://github.com/octo/secret",
                     "description": "Private stuff", "pushed_at": "2026-10-01T00:00:00Z", "default_branch": "main"},
                    {"full_name": "octo/open", "private": False, "html_url": "https://github.com/octo/open",
                     "description": None, "pushed_at": "2026-10-20T00:00:00Z", "default_branch": "main"}]})
        if url.startswith("https://oauth2.googleapis.com/token"):
            ok = form.get("code") == ["good"] and form.get("code_verifier")
            return httpx.Response(200, json={"access_token": "g_at"} if ok else {"error": "invalid_grant"})
        if url.startswith("https://openidconnect.googleapis.com"):
            return httpx.Response(200, json=self.google_user)
        if url == mailer.BREVO_SEND:
            self.emails.append({"headers": dict(request.headers), "body": json.loads(request.content)})
            return httpx.Response(201, json={"messageId": "<1@brevo>"})
        return httpx.Response(404, json={"message": f"unmocked {url}"})


@pytest.fixture
def web(monkeypatch):
    fake = FakeWeb()
    monkeypatch.setattr(oauth, "http", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    s = get_settings()
    for k, v in {"github_client_id": "Iv1.test", "github_client_secret": "gh-secret", "github_app_slug": "code-arch",
                 "google_client_id": "g.apps.googleusercontent.com", "google_client_secret": "g-secret"}.items():
        monkeypatch.setattr(s, k, v)
    return fake


@pytest.fixture
def codes(monkeypatch):
    """Turn on email verification and capture the codes that would be emailed."""
    sent = []
    monkeypatch.setattr(get_settings(), "email_delivery", "console")
    monkeypatch.setattr(mailer, "send_verification_code", lambda to, code, minutes: sent.append((to, code)))
    return sent


def oauth_round_trip(client, provider, code="good"):
    start = client.get(f"/api/auth/{provider}/login", follow_redirects=False)
    assert start.status_code == 302
    q = parse_qs(urlsplit(start.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and len(q["code_challenge"][0]) == 43
    return client.get(f"/api/auth/{provider}/callback", params={"code": code, "state": q["state"][0]},
                      follow_redirects=False)


def _user(email):
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


# ── Email verification ────────────────────────────────────────────
def test_sign_up_requires_the_emailed_code(client, codes):
    me = register(client, email="new@example.com")
    assert me["user"]["email_verified"] is False
    assert 55 <= me["user"]["code_resend_in"] <= 60                # a code was just sent
    assert codes and codes[0][0] == "new@example.com" and len(codes[0][1]) == 6
    assert client.get("/api/providers").status_code == 403          # gated until verified
    assert client.get("/api/auth/me").status_code == 200            # but can see who they are

    wrong = "000000" if codes[0][1] != "000000" else "111111"
    r = client.post("/api/auth/verify-email", json={"code": wrong})
    assert r.status_code == 400 and "4 attempts left" in r.json()["detail"]
    r = client.post("/api/auth/verify-email", json={"code": codes[0][1]})
    assert r.status_code == 200 and r.json()["user"]["email_verified"] is True
    assert client.get("/api/providers").status_code == 200


def test_code_is_stored_hashed_and_expires(client, codes):
    register(client, email="new@example.com")
    with SessionLocal() as db:
        rec = db.get(EmailVerification, _user("new@example.com").id)
        assert codes[0][1] not in rec.code_hash
        rec.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
    r = client.post("/api/auth/verify-email", json={"code": codes[0][1]})
    assert r.status_code == 400 and "expired" in r.json()["detail"]


def test_wrong_code_limit_and_resend_rules(client, codes):
    register(client, email="new@example.com")
    for _ in range(5):
        client.post("/api/auth/verify-email", json={"code": "999999" if codes[0][1] != "999999" else "888888"})
    r = client.post("/api/auth/verify-email", json={"code": codes[0][1]})
    assert r.status_code == 400 and "Too many" in r.json()["detail"]   # even the right code is dead now

    assert client.post("/api/auth/resend-code").status_code == 429      # 60s cooldown
    uid = _user("new@example.com").id
    with SessionLocal() as db:
        db.get(EmailVerification, uid).last_sent_at = utcnow() - timedelta(minutes=2)
        db.commit()
    assert client.get("/api/auth/me").json()["user"]["code_resend_in"] == 0   # reload shows no wait
    for _ in range(4):
        with SessionLocal() as db:
            db.get(EmailVerification, uid).last_sent_at = utcnow() - timedelta(minutes=2)
            db.commit()
        assert client.post("/api/auth/resend-code").status_code == 204
    with SessionLocal() as db:
        db.get(EmailVerification, uid).last_sent_at = utcnow() - timedelta(minutes=2)
        db.commit()
    r = client.post("/api/auth/resend-code")
    assert r.status_code == 429 and "an hour" in r.json()["detail"]     # 5 sends per hour
    assert client.post("/api/auth/verify-email", json={"code": codes[-1][1]}).status_code == 200


def test_unclaimed_sign_up_does_not_lock_out_the_real_owner(client, codes):
    register(client, email="victim@example.com", password="squatter-pass-1")
    client.post("/api/auth/logout")
    me = register(client, email="victim@example.com", password="owners-real-pass")
    assert me["user"]["email_verified"] is False
    client.post("/api/auth/verify-email", json={"code": codes[-1][1]})
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "victim@example.com",
                                                "password": "squatter-pass-1"}).status_code == 401
    r = client.post("/api/auth/register", json={"email": "victim@example.com", "password": "another-pass"})
    assert r.status_code == 409                                        # verified accounts are protected


def test_brevo_request_shape(client, web, monkeypatch):
    s = get_settings()
    for k, v in {"email_delivery": "brevo", "brevo_api_key": "xkeysib-test", "email_from": "me@gmail.com"}.items():
        monkeypatch.setattr(s, k, v)
    register(client, email="new@example.com")
    sent = web.emails[0]
    assert sent["headers"]["api-key"] == "xkeysib-test"
    body = sent["body"]
    assert body["sender"] == {"name": "Code Archaeologist", "email": "me@gmail.com"}
    assert body["to"] == [{"email": "new@example.com"}]
    code = body["subject"].split()[0]
    assert code.isdigit() and len(code) == 6 and code in body["textContent"]


# ── GitHub App ────────────────────────────────────────────────────
def test_github_sign_in_creates_verified_account_and_lists_shared_repos(client, web):
    r = oauth_round_trip(client, "github")
    assert r.status_code == 302 and r.headers["location"].endswith("/app")
    assert client.cookies.get(SESSION_COOKIE)
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == "octo@example.com" and me["email_verified"] and me["github_connected"]

    status = client.get("/api/github/status").json()
    assert status["connected"] and status["installations"][0]["account"] == "octo"
    assert status["install_url"] == "https://github.com/apps/code-arch/installations/new"
    repos = client.get("/api/github/repos").json()
    assert [(r["full_name"], r["private"]) for r in repos] == [("octo/open", False), ("octo/secret", True)]

    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.github_id == 42))
        assert decrypt_secret(u.github_token_enc) == "ghu_A" and "ghu_A" not in u.github_token_enc


def test_expired_github_token_is_refreshed(client, web):
    oauth_round_trip(client, "github")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.github_id == 42))
        u.github_token_expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/github/repos").status_code == 200
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.github_id == 42))
        assert decrypt_secret(u.github_token_enc) == "ghu_B" and decrypt_secret(u.github_refresh_enc) == "ghr_R2"


def test_dead_refresh_token_asks_to_reconnect(client, web):
    oauth_round_trip(client, "github")
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.github_id == 42))
        u.github_token_expires_at = utcnow() - timedelta(minutes=1)
        u.github_refresh_expires_at = utcnow() - timedelta(days=1)
        db.commit()
    r = client.get("/api/github/repos")
    assert r.status_code == 409 and "connect GitHub again" in r.json()["detail"]
    assert client.get("/api/auth/me").json()["user"]["github_connected"] is False


def test_connect_github_to_an_existing_account(client, web):
    register(client, email="me@example.com")
    r = oauth_round_trip(client, "github")
    assert r.headers["location"].endswith("/app/settings?github=connected")
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == "me@example.com" and me["github_login"] == "octo"

    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    r = oauth_round_trip(client, "github")
    assert r.headers["location"].endswith("/app/settings?github=taken")


def test_github_rejects_forged_state_and_bad_codes(client, web):
    client.get("/api/auth/github/login", follow_redirects=False)
    r = client.get("/api/auth/github/callback", params={"code": "good", "state": "forged"}, follow_redirects=False)
    assert r.headers["location"].endswith("/login?error=github_state")
    r = oauth_round_trip(client, "github", code="bad")
    assert r.headers["location"].endswith("/login?error=github_token")
    assert not client.cookies.get(SESSION_COOKIE)


def test_disconnect_github(client, web):
    oauth_round_trip(client, "github")
    assert client.delete("/api/github").status_code == 204
    assert client.get("/api/auth/me").json()["user"]["github_connected"] is False


# ── Google ────────────────────────────────────────────────────────
def test_google_sign_in(client, web):
    r = oauth_round_trip(client, "google")
    assert r.headers["location"].endswith("/app")
    me = client.get("/api/auth/me").json()["user"]
    assert me["email"] == "ada@example.com" and me["google_linked"] and me["email_verified"]
    # Signing in again finds the same account by Google's stable id
    client.post("/api/auth/logout")
    oauth_round_trip(client, "google")
    with SessionLocal() as db:
        assert db.query(User).count() == 1


def test_google_claims_an_unverified_squatted_account(client, web, codes):
    register(client, email="ada@example.com", password="squatter-pass-1")
    client.post("/api/auth/logout")
    oauth_round_trip(client, "google")
    me = client.get("/api/auth/me").json()["user"]
    assert me["email_verified"] and me["has_password"] is False      # squatter's password is gone
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "ada@example.com",
                                                "password": "squatter-pass-1"}).status_code == 401


def test_google_requires_a_verified_email(client, web):
    web.google_user["email_verified"] = False
    r = oauth_round_trip(client, "google")
    assert r.headers["location"].endswith("/login?error=google_unverified")


# ── Private repositories ──────────────────────────────────────────
def test_private_repo_clones_with_token_in_env_not_url(client, web, monkeypatch):
    from tests.test_repos import COMMITS
    oauth_round_trip(client, "github")
    seen = {}
    monkeypatch.setattr(github, "repo_visibility", lambda full_name, token: "private" if token == "ghu_A" else "missing")
    monkeypatch.setattr(ingest_service.git.Repo, "clone_from",
                        lambda url, path, **kw: seen.update(url=url, env=kw.get("env")))
    monkeypatch.setattr(ingest_service, "load_commits", lambda path, max_count: COMMITS)
    def fake_fetch_prs(*a, **k):
        seen["pr_token"] = k.get("token")
        return FetchResult(prs=[], warnings=[])
    monkeypatch.setattr(ingest_service, "fetch_prs", fake_fetch_prs)
    r = client.post("/api/repos", json={"url": "https://github.com/octo/secret", "max_commits": 50})
    assert r.status_code == 202 and r.json()["is_private"] is True
    assert client.get(f"/api/repos/{r.json()['id']}").json()["status"] == "ready"
    assert seen["url"] == "https://github.com/octo/secret"            # no credentials in the URL
    assert "ghu_A" not in json.dumps(seen["url"])
    assert seen["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert seen["env"]["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert seen["pr_token"] == "ghu_A"


def test_unknown_repo_gets_a_helpful_404(user_client, monkeypatch):
    monkeypatch.setattr(github, "repo_visibility", lambda full_name, token: "missing")
    r = user_client.post("/api/repos", json={"url": "https://github.com/someone/private-thing", "max_commits": 50})
    assert r.status_code == 404 and "connect GitHub" in r.json()["detail"]


def test_private_repo_without_github_fails_with_instructions(client, web, monkeypatch):
    oauth_round_trip(client, "github")
    monkeypatch.setattr(github, "repo_visibility", lambda full_name, token: "private")
    monkeypatch.setattr(ingest_service.git.Repo, "clone_from", lambda *a, **k: pytest.fail("must not clone"))
    client.delete("/api/github")   # e.g. the user disconnected GitHub
    r = client.post("/api/repos", json={"url": "https://github.com/octo/secret", "max_commits": 50})
    repo = client.get(f"/api/repos/{r.json()['id']}").json()
    assert repo["status"] == "failed" and "Connect GitHub" in repo["error"]


def test_git_auth_env_encodes_token():
    env = github.git_auth_env("ghu_secret")
    import base64
    encoded = env["GIT_CONFIG_VALUE_0"].split()[-1]
    assert base64.b64decode(encoded).decode() == "x-access-token:ghu_secret"
    assert env["GIT_TERMINAL_PROMPT"] == "0"
