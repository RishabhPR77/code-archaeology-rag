# app/routers/oauth_login.py
"""Continue with GitHub (a GitHub App) and Continue with Google: OAuth with state and PKCE."""
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import User
from app.services import audit, github, oauth, sessions
from app.services.users import sync_admin_flag

router = APIRouter(prefix="/api/auth", tags=["auth"])

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def _claim_unverified(user: User):
    """A verified identity provider vouched for this email. If the account was never
    verified, whoever set its password didn't prove they own the address — drop it."""
    if not user.email_verified:
        user.password_hash = None
    user.email_verified = True


def _done(resp: RedirectResponse) -> RedirectResponse:
    resp.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth")
    return resp


# ── GitHub App ─────────────────────────────────────────────────────
@router.get("/github/login")
def github_login():
    settings = get_settings()
    if not settings.github_oauth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GitHub sign-in is not configured")
    return oauth.start_flow("github", GITHUB_AUTHORIZE, {
        "client_id": settings.github_client_id, "redirect_uri": oauth.callback_url("github"),
        "allow_signup": "true"})


@router.get("/github/callback")
def github_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    settings = get_settings()
    if error or not code:
        return oauth.fail("github_denied")
    verifier = oauth.finish_flow(request, "github", state)
    if not verifier:
        return oauth.fail("github_state")
    try:
        tokens = github.exchange_code(code, verifier, oauth.callback_url("github"))
        profile, primary = github.profile(tokens.access)
    except github.GitHubNotConnected:
        return oauth.fail("github_token")
    except (httpx.HTTPError, ValueError):
        return oauth.fail("github_unavailable")

    owner = db.scalar(select(User).where(User.github_id == profile["id"]))
    current = sessions.session_user(request, db)
    if current is not None and current.is_demo:
        current = None   # leaving the demo for a real account, never linking GitHub to the shared one
    if current is not None:
        # Signed in already: this connects GitHub to the current account
        if owner is not None and owner.id != current.id:
            return _done(RedirectResponse(f"{settings.frontend_url}/app/settings?github=taken", status_code=302))
        user = current
    else:
        user = owner
        if user is None and primary:
            # GitHub verified this address, so it's safe to link an existing account
            user = db.scalar(select(User).where(User.email == primary.lower(), User.is_demo.is_(False)))
            if user is not None:
                _claim_unverified(user)
        if user is None:
            if not primary:
                return oauth.fail("github_no_email")
            user = User(email=primary.lower(), name=profile.get("name") or profile["login"], email_verified=True)
            db.add(user)
            db.flush()
            audit.record(db, user, "account_created", request, "With GitHub")

    newly_linked = user.github_id != profile["id"]
    user.github_id = profile["id"]
    user.github_login = profile["login"]
    user.avatar_url = user.avatar_url or profile.get("avatar_url")
    github.store_tokens(user, tokens)
    sync_admin_flag(user)
    db.commit()
    if newly_linked:
        audit.record(db, user, "github_connected", request, f"@{profile['login']}")

    if current is not None:
        resp = RedirectResponse(f"{settings.frontend_url}/app/settings?github=connected", status_code=302)
        sessions.start(resp, user)
        return _done(resp)
    return _done(sessions.sign_in_redirect(db, request, user, "github", "/app"))


# ── Google ─────────────────────────────────────────────────────────
@router.get("/google/login")
def google_login():
    settings = get_settings()
    if not settings.google_oauth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Google sign-in is not configured")
    return oauth.start_flow("google", GOOGLE_AUTHORIZE, {
        "client_id": settings.google_client_id, "redirect_uri": oauth.callback_url("google"),
        "response_type": "code", "scope": "openid email profile", "prompt": "select_account"})


@router.get("/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    settings = get_settings()
    if error or not code:
        return oauth.fail("google_denied")
    verifier = oauth.finish_flow(request, "google", state)
    if not verifier:
        return oauth.fail("google_state")
    try:
        with oauth.http() as client:
            tok = client.post(GOOGLE_TOKEN, data={
                "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
                "code": code, "code_verifier": verifier, "grant_type": "authorization_code",
                "redirect_uri": oauth.callback_url("google")}).json()
            if "access_token" not in tok:
                return oauth.fail("google_token")
            info = client.get(GOOGLE_USERINFO, headers={
                "Authorization": f"Bearer {tok['access_token']}"}).raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        return oauth.fail("google_unavailable")

    if not info.get("email") or not info.get("email_verified"):
        return oauth.fail("google_unverified")
    email = info["email"].lower()
    user = db.scalar(select(User).where(User.google_sub == info["sub"]))
    if user is None:
        user = db.scalar(select(User).where(User.email == email, User.is_demo.is_(False)))
        if user is not None:
            _claim_unverified(user)
        else:
            user = User(email=email, name=info.get("name") or email.split("@")[0], email_verified=True)
            db.add(user)
            db.flush()
            audit.record(db, user, "account_created", request, "With Google")
    user.google_sub = info["sub"]
    user.avatar_url = user.avatar_url or info.get("picture")
    sync_admin_flag(user)
    db.commit()
    return _done(sessions.sign_in_redirect(db, request, user, "google", "/app"))
