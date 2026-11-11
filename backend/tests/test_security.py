"""Two-step sign-in, password changes, key rotation, rate limits, visitor IPs, the activity log,
account deletion, cross-site requests and resuming ingests."""
import time

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import deps, security
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import ProviderCredential, RateLimitHit, Repo, SecurityEvent, User
from app.security import SESSION_COOKIE, TWO_FACTOR_COOKIE
from app.services import ingest, rotation
from tests.conftest import register

PASSWORD = "correct-horse-battery"


def _user(email="dev@example.com") -> User:
    with SessionLocal() as db:
        return db.scalar(select(User).where(User.email == email))


def _login(client, email="dev@example.com", password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _code(secret: str, offset_steps: int = 0) -> str:
    return pyotp.TOTP(secret).at(time.time() + 30 * offset_steps)


def _turn_on_two_factor(client) -> tuple[str, list[str]]:
    setup = client.post("/api/auth/2fa/setup").json()
    assert setup["qr_svg"].startswith("data:image/svg+xml") and setup["uri"].startswith("otpauth://totp/")
    r = client.post("/api/auth/2fa/enable", json={"code": _code(setup["secret"])})
    assert r.status_code == 200, r.text
    return setup["secret"], r.json()["codes"]


# ── Two-step sign-in ──────────────────────────────────────────────
def test_two_step_sign_in_needs_the_authenticator_code(user_client):
    secret, recovery = _turn_on_two_factor(user_client)
    assert len(recovery) == 10 and all(len(c) == 9 and c[4] == "-" for c in recovery)
    me = user_client.get("/api/auth/me").json()["user"]
    assert me["two_factor_enabled"] is True and me["recovery_codes_left"] == 10
    user_client.post("/api/auth/logout")

    r = _login(user_client)
    assert r.status_code == 200 and r.json() == {"two_factor_required": True}
    assert not user_client.cookies.get(SESSION_COOKIE)                  # the password alone isn't a session
    assert user_client.cookies.get(TWO_FACTOR_COOKIE)
    assert user_client.get("/api/auth/me").status_code == 401
    assert user_client.post("/api/auth/2fa/verify", json={"code": "000000"}).status_code == 400

    # Codes the setup already used can't be replayed, so ask for the next one
    r = user_client.post("/api/auth/2fa/verify", json={"code": _code(secret, 1)})
    assert r.status_code == 200 and r.json()["user"]["email"] == "dev@example.com"
    assert user_client.get("/api/auth/me").status_code == 200


def test_a_code_cannot_be_used_twice(user_client):
    secret, _ = _turn_on_two_factor(user_client)
    user_client.post("/api/auth/logout")
    _login(user_client)
    code = _code(secret, 1)
    assert user_client.post("/api/auth/2fa/verify", json={"code": code}).status_code == 200
    user_client.post("/api/auth/logout")
    _login(user_client)
    assert user_client.post("/api/auth/2fa/verify", json={"code": code}).status_code == 400


def test_recovery_codes_work_once(user_client):
    _, recovery = _turn_on_two_factor(user_client)
    user_client.post("/api/auth/logout")
    _login(user_client)
    assert user_client.post("/api/auth/2fa/verify", json={"code": recovery[0].upper()}).status_code == 200
    assert user_client.get("/api/auth/me").json()["user"]["recovery_codes_left"] == 9
    user_client.post("/api/auth/logout")
    _login(user_client)
    assert user_client.post("/api/auth/2fa/verify", json={"code": recovery[0]}).status_code == 400


def test_the_half_signed_in_token_is_not_a_session(user_client):
    _turn_on_two_factor(user_client)
    user_client.post("/api/auth/logout")
    _login(user_client)
    pending = user_client.cookies.get(TWO_FACTOR_COOKIE)
    user_client.cookies.set(SESSION_COOKIE, pending)
    assert user_client.get("/api/auth/me").status_code == 401


def test_turning_two_step_off_needs_a_code(user_client):
    secret, _ = _turn_on_two_factor(user_client)
    assert user_client.post("/api/auth/2fa/disable", json={"code": "123456"}).status_code == 400
    r = user_client.post("/api/auth/2fa/disable", json={"code": _code(secret, 1)})
    assert r.status_code == 200 and r.json()["user"]["two_factor_enabled"] is False
    user_client.post("/api/auth/logout")
    assert "user" in _login(user_client).json()                         # straight in again


def test_google_sign_in_also_asks_for_the_code(client, monkeypatch):
    from tests.test_accounts import FakeWeb, oauth_round_trip
    import httpx
    from app.services import oauth
    fake = FakeWeb()
    monkeypatch.setattr(oauth, "http", lambda: httpx.Client(transport=httpx.MockTransport(fake)))
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", "g.apps.googleusercontent.com")
    monkeypatch.setattr(s, "google_client_secret", "g-secret")
    oauth_round_trip(client, "google")
    secret, _ = _turn_on_two_factor(client)
    client.post("/api/auth/logout")
    r = oauth_round_trip(client, "google")
    assert r.headers["location"].endswith("/two-factor") and not client.cookies.get(SESSION_COOKIE)
    assert client.post("/api/auth/2fa/verify", json={"code": _code(secret, 1)}).status_code == 200


# ── Passwords ─────────────────────────────────────────────────────
def test_change_password_signs_out_other_devices(user_client):
    with TestClient(app) as laptop:
        _login(laptop)
        assert user_client.post("/api/auth/password", json={"current_password": "wrong-one-here",
                                                            "new_password": "new-secret-pass-9"}).status_code == 400
        r = user_client.post("/api/auth/password", json={"current_password": PASSWORD,
                                                         "new_password": "new-secret-pass-9"})
        assert r.status_code == 200
        assert user_client.get("/api/auth/me").status_code == 200      # this device stays signed in
        assert laptop.get("/api/auth/me").status_code == 401           # the other one doesn't
    user_client.post("/api/auth/logout")
    assert _login(user_client, password="new-secret-pass-9").status_code == 200


def test_weak_passwords_are_refused(client):
    for weak in ("password123", "12345678", "aaaaaaaa"):
        r = client.post("/api/auth/register", json={"email": "a@example.com", "password": weak})
        assert r.status_code == 422, weak
    r = client.post("/api/auth/register", json={"email": "someone@example.com", "password": "someone@example.com"})
    assert r.status_code == 422


def test_unknown_email_still_runs_the_slow_password_check(monkeypatch):
    calls = []
    real = security.bcrypt.checkpw
    monkeypatch.setattr(security.bcrypt, "checkpw", lambda pw, h: calls.append(1) or real(pw, h))
    assert security.verify_password("anything-at-all", None) is False
    assert calls == [1]


# ── Key rotation ──────────────────────────────────────────────────
def test_signing_key_rotation_keeps_sessions(user_client, monkeypatch):
    s = get_settings()
    old = s.secret_key
    monkeypatch.setattr(s, "secret_key", "a-brand-new-signing-key-that-is-long-enough!!")
    monkeypatch.setattr(s, "secret_key_previous", old)
    assert user_client.get("/api/auth/me").status_code == 200          # signed with the old key, still valid
    monkeypatch.setattr(s, "secret_key_previous", "")
    assert user_client.get("/api/auth/me").status_code == 401          # once the old key is dropped, it isn't


def test_encryption_key_rotation_reencrypts_stored_secrets(user_client, monkeypatch):
    from cryptography.fernet import Fernet
    user_client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    s = get_settings()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(s, "encryption_key_previous", s.encryption_key)
    monkeypatch.setattr(s, "encryption_key", new_key)
    security._fernet.cache_clear()
    try:
        assert rotation.reencrypt_stored_secrets() == 1
        with SessionLocal() as db:
            stored = db.scalar(select(ProviderCredential)).key_enc
        assert Fernet(new_key.encode()).decrypt(stored.encode()).decode() == "good-key-1234"
    finally:
        security._fernet.cache_clear()


# ── Rate limits and visitor addresses ─────────────────────────────
def test_rate_limits_are_stored_hashed_in_the_database(client):
    register(client)
    for _ in range(3):
        _login(client, password="wrong-password-1")
    with SessionLocal() as db:
        keys = db.scalars(select(RateLimitHit.key)).all()
    assert keys and all(len(k) == 64 and "dev@example.com" not in k for k in keys)


def test_wrong_passwords_from_many_addresses_still_lock_the_account(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "client_ip_header", "true-client-ip")
    register(client)
    client.post("/api/auth/logout")
    for i in range(20):
        r = client.post("/api/auth/login", json={"email": "dev@example.com", "password": "wrong-password-1"},
                        headers={"true-client-ip": f"198.51.100.{i}"})
        assert r.status_code == 401
    r = client.post("/api/auth/login", json={"email": "dev@example.com", "password": PASSWORD},
                    headers={"true-client-ip": "198.51.100.200"})
    assert r.status_code == 429 and "wrong passwords" in r.json()["detail"]


def test_client_ip_ignores_x_forwarded_for(monkeypatch):
    from starlette.requests import Request

    def request(headers):
        return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
                        "client": ("10.0.0.5", 1234)})

    assert deps.client_ip(request({"x-forwarded-for": "203.0.113.9"})) == "10.0.0.5"
    monkeypatch.setattr(get_settings(), "client_ip_header", "true-client-ip")
    assert deps.client_ip(request({"true-client-ip": "203.0.113.9"})) == "203.0.113.9"
    assert deps.client_ip(request({"true-client-ip": "not-an-ip"})) == "10.0.0.5"


def test_writes_from_other_sites_are_refused(user_client):
    r = user_client.post("/api/auth/logout", headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = user_client.post("/api/auth/logout", headers={"Origin": get_settings().frontend_url})
    assert r.status_code == 204
    # The site's own page, served from the API's host, even when the frontend URL setting differs
    register(user_client, email="second@example.com")
    r = user_client.post("/api/auth/logout", headers={"Origin": "http://testserver"})
    assert r.status_code == 204


def test_every_response_has_a_request_id(client):
    r = client.get("/api/health")
    assert len(r.headers["x-request-id"]) == 12


# ── Activity and account deletion ─────────────────────────────────
def test_activity_log_records_security_events(client):
    register(client)
    client.post("/api/auth/logout")
    _login(client, password="wrong-password-1")
    client.post("/api/auth/login", json={"email": "dev@example.com", "password": PASSWORD},
                headers={"user-agent": "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36"})
    events = client.get("/api/auth/activity").json()
    kinds = [e["kind"] for e in events]
    assert kinds[:3] == ["sign_in", "sign_in_failed", "account_created"]
    assert events[0]["label"] == "Signed in" and events[0]["detail"] == "with a password"
    assert events[0]["device"] == "Chrome on Windows"


def test_ip_addresses_are_shortened():
    from app.services.audit import short_ip
    assert short_ip("203.0.113.77") == "203.0.113.x"
    assert short_ip("2001:db8:1234:5678::1") == "2001:db8:1234::/48"
    assert short_ip("unknown") == ""


def test_delete_account_removes_everything(user_client, monkeypatch):
    from tests.test_repos import _ready_repo
    deleted = []
    monkeypatch.setattr(ingest, "delete_repo_data", lambda repo: deleted.append(repo.namespace))
    _ready_repo(user_client)
    r = user_client.request("DELETE", "/api/auth/me", json={"confirm_email": "someone-else@example.com"})
    assert r.status_code == 400
    r = user_client.request("DELETE", "/api/auth/me", json={"confirm_email": "DEV@example.com"})
    assert r.status_code == 204 and len(deleted) == 1
    assert user_client.get("/api/auth/me").status_code == 401
    with SessionLocal() as db:
        assert db.query(User).count() == 0 and db.query(Repo).count() == 0
        assert db.query(SecurityEvent).count() == 0


# ── Ingest jobs survive a restart ─────────────────────────────────
@pytest.mark.parametrize("attempts, expected", [(1, "queued"), (3, "failed")])
def test_interrupted_ingests_resume_after_a_restart(user_client, monkeypatch, attempts, expected):
    started = []
    monkeypatch.setattr(ingest, "run_ingest", lambda repo_id: started.append(repo_id))
    with SessionLocal() as db:
        repo = Repo(user_id=_user().id, url="https://github.com/a/b", full_name="a/b", namespace="ns-resume",
                    max_commits=50, status="embedding", ingest_attempts=attempts)
        db.add(repo)
        db.commit()
        repo_id = repo.id
    resumed = ingest.resume_interrupted()
    with SessionLocal() as db:
        assert db.get(Repo, repo_id).status == expected
    assert resumed == ([repo_id] if expected == "queued" else [])
