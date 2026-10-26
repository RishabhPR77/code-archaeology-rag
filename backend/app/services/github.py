# app/services/github.py
"""GitHub App user tokens: exchange, refresh, and the repositories a user has shared.

Docs: https://docs.github.com/en/apps/creating-github-apps/authenticating-with-a-github-app/generating-a-user-access-token-for-a-github-app
A user token can only reach repos that both the user and the app's installation can,
and the app only asks for read access.
"""
import base64
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import User, utcnow
from app.schemas import as_utc
from app.security import decrypt_secret, encrypt_secret
from app.services import oauth

API = "https://api.github.com"
TOKEN_URL = "https://github.com/login/oauth/access_token"
API_HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
REFRESH_MARGIN = timedelta(minutes=5)
MAX_REPOS = 500

_refresh_lock = threading.Lock()


class GitHubNotConnected(Exception):
    """The user has no usable GitHub token — they need to (re)connect."""


@dataclass
class Tokens:
    access: str
    access_expires: datetime | None
    refresh: str | None
    refresh_expires: datetime | None


def _parse_tokens(body: dict) -> Tokens:
    if "access_token" not in body:
        raise GitHubNotConnected(body.get("error_description") or body.get("error") or "GitHub refused the token")
    now = utcnow()

    def after(key):
        return now + timedelta(seconds=int(body[key])) if body.get(key) else None

    return Tokens(body["access_token"], after("expires_in"),
                  body.get("refresh_token"), after("refresh_token_expires_in"))


def exchange_code(code: str, verifier: str, redirect_uri: str) -> Tokens:
    s = get_settings()
    with oauth.http() as client:
        body = client.post(TOKEN_URL, headers={"Accept": "application/json"}, data={
            "client_id": s.github_client_id, "client_secret": s.github_client_secret,
            "code": code, "redirect_uri": redirect_uri, "code_verifier": verifier}).json()
    return _parse_tokens(body)


def store_tokens(user: User, tokens: Tokens):
    user.github_token_enc = encrypt_secret(tokens.access)
    user.github_token_expires_at = tokens.access_expires
    user.github_refresh_enc = encrypt_secret(tokens.refresh) if tokens.refresh else None
    user.github_refresh_expires_at = tokens.refresh_expires


def clear_tokens(user: User):
    user.github_token_enc = user.github_refresh_enc = None
    user.github_token_expires_at = user.github_refresh_expires_at = None


def user_token(db: Session, user: User) -> str:
    """A valid access token for this user, refreshing it first if it's about to expire."""
    if not user.github_token_enc:
        raise GitHubNotConnected("GitHub isn't connected")
    expires = as_utc(user.github_token_expires_at)
    if expires is None or expires - REFRESH_MARGIN > utcnow():
        return decrypt_secret(user.github_token_enc)

    with _refresh_lock:
        db.refresh(user)  # another request may have refreshed already
        expires = as_utc(user.github_token_expires_at)
        if expires and expires - REFRESH_MARGIN > utcnow():
            return decrypt_secret(user.github_token_enc)
        refresh_expires = as_utc(user.github_refresh_expires_at)
        if not user.github_refresh_enc or (refresh_expires and refresh_expires <= utcnow()):
            clear_tokens(user)
            db.commit()
            raise GitHubNotConnected("Your GitHub connection expired — connect GitHub again")
        s = get_settings()
        with oauth.http() as client:
            body = client.post(TOKEN_URL, headers={"Accept": "application/json"}, data={
                "client_id": s.github_client_id, "client_secret": s.github_client_secret,
                "grant_type": "refresh_token", "refresh_token": decrypt_secret(user.github_refresh_enc)}).json()
        try:
            tokens = _parse_tokens(body)
        except GitHubNotConnected:
            clear_tokens(user)
            db.commit()
            raise GitHubNotConnected("Your GitHub connection expired — connect GitHub again") from None
        store_tokens(user, tokens)
        db.commit()
        return tokens.access


def _get(client: httpx.Client, token: str | None, path: str, **params) -> httpx.Response:
    headers = dict(API_HEADERS)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return client.get(f"{API}{path}", headers=headers, params=params)


def profile(token: str) -> tuple[dict, str | None]:
    """The signed-in GitHub user and their verified primary email (if the app may read it)."""
    with oauth.http() as client:
        user = _get(client, token, "/user").raise_for_status().json()
        emails = _get(client, token, "/user/emails")
    primary = None
    if emails.status_code == 200:
        primary = next((e["email"] for e in emails.json() if e.get("primary") and e.get("verified")), None)
    return user, primary


def installations(token: str) -> list[dict]:
    with oauth.http() as client:
        r = _get(client, token, "/user/installations", per_page=100)
        if r.status_code == 401:
            raise GitHubNotConnected("GitHub rejected the saved token — connect GitHub again")
        r.raise_for_status()
    return [{"id": i["id"], "account": i["account"]["login"],
             "repository_selection": i["repository_selection"], "manage_url": i.get("html_url")}
            for i in r.json().get("installations", [])]


def shared_repos(token: str) -> list[dict]:
    """Every repo the user has shared with the app, across their installations."""
    repos = []
    with oauth.http() as client:
        for inst in installations(token):
            for page in range(1, MAX_REPOS // 100 + 1):
                r = _get(client, token, f"/user/installations/{inst['id']}/repositories", per_page=100, page=page)
                r.raise_for_status()
                batch = r.json().get("repositories", [])
                repos += [{"full_name": x["full_name"], "private": x["private"], "html_url": x["html_url"],
                           "description": x.get("description"), "updated_at": x.get("pushed_at") or x.get("updated_at"),
                           "default_branch": x.get("default_branch")} for x in batch]
                if len(batch) < 100 or len(repos) >= MAX_REPOS:
                    break
    unique = {r["full_name"]: r for r in repos}
    return sorted(unique.values(), key=lambda r: r["updated_at"] or "", reverse=True)


def repo_visibility(full_name: str, token: str | None) -> str:
    """"public", "private", "missing" (doesn't exist or this token can't see it),
    or "unknown" (rate-limited / GitHub unreachable — don't block on it)."""
    try:
        with oauth.http() as client:
            r = _get(client, token, f"/repos/{full_name}")
    except httpx.HTTPError:
        return "unknown"
    if r.status_code == 200:
        return "private" if r.json().get("private") else "public"
    return "missing" if r.status_code == 404 else "unknown"


def git_auth_env(token: str) -> dict[str, str]:
    """Credentials for `git clone` passed via environment, so the token never appears in
    command lines, error messages or logs (unlike a token embedded in the URL)."""
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {basic}", "GIT_TERMINAL_PROMPT": "0"}
