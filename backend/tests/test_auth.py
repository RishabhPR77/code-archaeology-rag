from app.security import SESSION_COOKIE
from tests.conftest import register


def test_register_sets_session_and_me_works(client):
    me = register(client)
    assert me["user"]["email"] == "dev@example.com"
    assert me["user"]["has_password"] is True
    assert client.cookies.get(SESSION_COOKIE)
    assert client.get("/api/auth/me").json()["user"]["email"] == "dev@example.com"


def test_session_cookie_is_httponly_and_lax(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_duplicate_email_rejected_case_insensitively(client):
    register(client, email="dev@example.com")
    r = client.post("/api/auth/register", json={"email": "DEV@example.com", "password": "password123"})
    assert r.status_code == 409


def test_login_logout(client):
    register(client)
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json={"email": "dev@example.com", "password": "nope-nope"}).status_code == 401
    r = client.post("/api/auth/login", json={"email": "dev@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_tampered_session_rejected(client):
    register(client)
    client.cookies.set(SESSION_COOKIE, client.cookies.get(SESSION_COOKIE) + "x")
    assert client.get("/api/auth/me").status_code == 401


def test_short_and_overlong_passwords_rejected(client):
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "x" * 73}).status_code == 422


def test_login_is_rate_limited(client):
    register(client)
    for _ in range(10):
        client.post("/api/auth/login", json={"email": "dev@example.com", "password": "wrong-pass"})
    r = client.post("/api/auth/login", json={"email": "dev@example.com", "password": "correct-horse-battery"})
    assert r.status_code == 429


def test_admin_email_gets_unlimited(client):
    me = register(client, email="admin@example.com")
    assert me["user"]["is_admin"] is True
    assert me["limits"]["unlimited"] is True


def test_github_disabled_without_config(client):
    assert client.get("/api/auth/config").json() == {"github_enabled": False}
    assert client.get("/api/auth/github/login", follow_redirects=False).status_code == 404
