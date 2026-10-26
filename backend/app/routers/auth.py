# app/routers/auth.py
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import auth_limiter, client_ip, current_user
from app.models import User
from app.schemas import AuthConfigOut, LoginIn, MeOut, RegisterIn
from app.security import (SESSION_COOKIE, create_session_token, encrypt_secret, hash_password,
                          session_cookie_kwargs, verify_password)
from app.services.users import limits_for, sync_admin_flag, user_out

router = APIRouter(prefix="/api/auth", tags=["auth"])

OAUTH_STATE_COOKIE = "ca_oauth_state"
GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN = "https://github.com/login/oauth/access_token"
GITHUB_API = "https://api.github.com"


def _start_session(response: Response, user: User):
    response.set_cookie(value=create_session_token(user.id), **session_cookie_kwargs())


def _me(db: Session, user: User) -> MeOut:
    return MeOut(user=user_out(db, user), limits=limits_for(db, user))


@router.get("/config", response_model=AuthConfigOut)
def auth_config():
    return AuthConfigOut(github_enabled=get_settings().github_oauth_enabled)


@router.post("/register", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"register:{client_ip(request)}")
    email = body.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=body.name.strip() or email.split("@")[0],
                password_hash=hash_password(body.password))
    sync_admin_flag(user)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    _start_session(response, user)
    return _me(db, user)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    auth_limiter.check(f"login:{client_ip(request)}:{email}")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash):
        detail = "Incorrect email or password"
        if user is not None and user.password_hash is None:
            detail = "This account uses Sign in with GitHub"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail)
    sync_admin_flag(user)
    db.commit()
    _start_session(response, user)
    return _me(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(db, user)


# ── GitHub OAuth ───────────────────────────────────────────────────
def _callback_url() -> str:
    # The frontend proxies /api to this server, so OAuth stays on one origin
    return f"{get_settings().frontend_url.rstrip('/')}/api/auth/github/callback"


def _fail(reason: str) -> RedirectResponse:
    return RedirectResponse(f"{get_settings().frontend_url}/login?error={reason}", status_code=302)


@router.get("/github/login")
def github_login():
    settings = get_settings()
    if not settings.github_oauth_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "GitHub sign-in is not configured")
    state = secrets.token_urlsafe(24)
    params = {"client_id": settings.github_client_id, "redirect_uri": _callback_url(),
              "scope": "read:user user:email", "state": state, "allow_signup": "true"}
    resp = RedirectResponse(f"{GITHUB_AUTHORIZE}?{urlencode(params)}", status_code=302)
    resp.set_cookie(OAUTH_STATE_COOKIE, state, max_age=600, httponly=True,
                    secure=settings.is_production, samesite="lax", path="/api/auth/github")
    return resp


@router.get("/github/callback")
def github_callback(request: Request, code: str = "", state: str = "", error: str = "",
                    db: Session = Depends(get_db)):
    settings = get_settings()
    if error or not code:
        return _fail("github_denied")
    expected = request.cookies.get(OAUTH_STATE_COOKIE)
    if not expected or not secrets.compare_digest(expected, state):
        return _fail("github_state")

    try:
        with httpx.Client(timeout=15) as http:
            tok = http.post(GITHUB_TOKEN, headers={"Accept": "application/json"}, data={
                "client_id": settings.github_client_id, "client_secret": settings.github_client_secret,
                "code": code, "redirect_uri": _callback_url()}).json()
            access_token = tok.get("access_token")
            if not access_token:
                return _fail("github_token")
            gh = {"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"}
            profile = http.get(f"{GITHUB_API}/user", headers=gh).raise_for_status().json()
            emails = http.get(f"{GITHUB_API}/user/emails", headers=gh).raise_for_status().json()
    except (httpx.HTTPError, ValueError):
        return _fail("github_unavailable")

    primary = next((e["email"] for e in emails if e.get("primary") and e.get("verified")), None)
    user = db.scalar(select(User).where(User.github_id == profile["id"]))
    if user is None and primary:
        # GitHub verified this address, so it's safe to link an existing account
        user = db.scalar(select(User).where(User.email == primary.lower()))
    if user is None:
        if not primary:
            return _fail("github_no_email")
        user = User(email=primary.lower(), name=profile.get("name") or profile["login"])
        db.add(user)

    user.github_id = profile["id"]
    user.github_login = profile["login"]
    user.avatar_url = profile.get("avatar_url")
    user.github_token_enc = encrypt_secret(access_token)
    sync_admin_flag(user)
    db.commit()

    resp = RedirectResponse(f"{settings.frontend_url}/app", status_code=302)
    resp.delete_cookie(OAUTH_STATE_COOKIE, path="/api/auth/github")
    _start_session(resp, user)
    return resp
