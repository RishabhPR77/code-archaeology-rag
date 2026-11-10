# app/routers/auth.py
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import auth_limiter, client_ip, current_user
from app.models import Conversation, Query, Repo, User
from app.schemas import (AuthConfigOut, LoginIn, MeOut, NameIn, ProfileOut, RecentQuestionOut, RegisterIn,
                         VerifyEmailIn, as_utc)
from app.security import (SESSION_COOKIE, create_session_token, decode_session_token,
                          hash_password, session_cookie_kwargs, verify_password)
from app.services import demo, github, oauth, verification
from app.services.users import limits_for, sync_admin_flag, user_out

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

GITHUB_AUTHORIZE = "https://github.com/login/oauth/authorize"
GOOGLE_AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"


def _start_session(response: Response, user: User):
    response.set_cookie(value=create_session_token(user.id), **session_cookie_kwargs())


def _me(db: Session, user: User) -> MeOut:
    return MeOut(user=user_out(db, user), limits=limits_for(db, user))


def _session_user(request: Request, db: Session) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = decode_session_token(token) if token else None
    return db.get(User, user_id) if user_id else None


def _claim_unverified(user: User):
    """A verified identity provider vouched for this email. If the account was never
    verified, whoever set its password didn't prove they own the address — drop it."""
    if not user.email_verified:
        user.password_hash = None
    user.email_verified = True


@router.get("/config", response_model=AuthConfigOut)
def auth_config(db: Session = Depends(get_db)):
    s = get_settings()
    return AuthConfigOut(github_enabled=s.github_oauth_enabled, google_enabled=s.google_oauth_enabled,
                         email_verification=s.email_verification_enabled,
                         contact_email=s.contact_email or None, demo_available=bool(demo.demo_repos(db)))


# ── Demo ───────────────────────────────────────────────────────────
@router.post("/demo", response_model=MeOut)
def demo_login(request: Request, response: Response, db: Session = Depends(get_db)):
    """Sign in to the shared, read-only demo account. No password: it can't change anything."""
    auth_limiter.check(f"demo:{client_ip(request)}")
    user = demo.demo_user(db)
    if user is None or not demo.demo_repos(db):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo isn't available right now")
    _start_session(response, user)
    return _me(db, user)


# ── Email + password ───────────────────────────────────────────────
@router.post("/register", response_model=MeOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"register:{client_ip(request)}")
    settings = get_settings()
    email = body.email.lower()
    name = body.name.strip() or email.split("@")[0]

    user = db.scalar(select(User).where(User.email == email))
    if user is not None:
        # An unclaimed sign-up can't lock the real owner out of their address
        if user.email_verified or user.github_id or user.google_sub:
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user.name, user.password_hash = name, hash_password(body.password)
    else:
        user = User(email=email, name=name, password_hash=hash_password(body.password),
                    email_verified=not settings.email_verification_enabled)
        db.add(user)
    sync_admin_flag(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    if not user.email_verified:
        try:
            verification.send_code(db, user)
        except HTTPException as e:
            # The account exists; the verify page can resend once the cooldown passes
            log.warning("Couldn't send the sign-up code to user %s: %s", user.id, e.detail)
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
            detail = "This account signs in with Google or GitHub"
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail)
    sync_admin_flag(user)
    db.commit()
    _start_session(response, user)
    return _me(db, user)


@router.post("/verify-email", response_model=MeOut)
def verify_email(body: VerifyEmailIn, request: Request,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    auth_limiter.check(f"verify:{client_ip(request)}")
    if not user.email_verified:
        verification.check_code(db, user, body.code)
    return _me(db, user)


@router.post("/resend-code", status_code=status.HTTP_204_NO_CONTENT)
def resend_code(user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not user.email_verified:
        verification.send_code(db, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _me(db, user)


@router.patch("/me", response_model=MeOut)
def update_me(body: NameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Change the display name."""
    user.name = body.name
    db.commit()
    return _me(db, user)


@router.get("/profile", response_model=ProfileOut)
def profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Counts of what the user has done, and their latest questions."""
    repos = db.scalars(select(Repo).where(Repo.user_id == user.id)).all()
    ready = [r for r in repos if r.status == "ready"]
    mine = select(Repo.id).where(Repo.user_id == user.id)
    questions = db.scalar(select(func.count()).select_from(Query).where(Query.repo_id.in_(mine), Query.kind == "ask"))
    chats = db.scalar(select(func.count()).select_from(Conversation).where(Conversation.repo_id.in_(mine)))
    names = {r.id: r.full_name for r in repos}
    latest = db.scalars(select(Query).where(Query.repo_id.in_(mine), Query.kind == "ask")
                        .order_by(Query.created_at.desc()).limit(5))
    return ProfileOut(
        repos=len(repos), ready_repos=len(ready), commits_indexed=sum(r.commit_count for r in ready),
        prs_linked=sum(r.pr_count for r in ready), questions=questions or 0, chats=chats or 0,
        recent=[RecentQuestionOut(question=q.question, repo_id=q.repo_id, repo=names.get(q.repo_id, ""),
                                  chat_id=q.conversation_id, created_at=as_utc(q.created_at)) for q in latest],
    )


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
    current = _session_user(request, db)
    if current is not None and current.is_demo:
        current = None   # leaving the demo for a real account, never linking GitHub to the shared one
    if current is not None:
        # Signed in already: this connects GitHub to the current account
        if owner is not None and owner.id != current.id:
            resp = RedirectResponse(f"{settings.frontend_url}/app/settings?github=taken", status_code=302)
            resp.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth")
            return resp
        user, landing = current, "/app/settings?github=connected"
    else:
        user, landing = owner, "/app"
        if user is None and primary:
            # GitHub verified this address, so it's safe to link an existing account
            user = db.scalar(select(User).where(User.email == primary.lower()))
            if user is not None:
                _claim_unverified(user)
        if user is None:
            if not primary:
                return oauth.fail("github_no_email")
            user = User(email=primary.lower(), name=profile.get("name") or profile["login"], email_verified=True)
            db.add(user)

    user.github_id = profile["id"]
    user.github_login = profile["login"]
    user.avatar_url = user.avatar_url or profile.get("avatar_url")
    github.store_tokens(user, tokens)
    sync_admin_flag(user)
    db.commit()

    resp = RedirectResponse(f"{settings.frontend_url}{landing}", status_code=302)
    resp.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth")
    _start_session(resp, user)
    return resp


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
        user = db.scalar(select(User).where(User.email == email))
        if user is not None:
            _claim_unverified(user)
        else:
            user = User(email=email, name=info.get("name") or email.split("@")[0], email_verified=True)
            db.add(user)
    user.google_sub = info["sub"]
    user.avatar_url = user.avatar_url or info.get("picture")
    sync_admin_flag(user)
    db.commit()

    resp = RedirectResponse(f"{settings.frontend_url}/app", status_code=302)
    resp.delete_cookie(oauth.FLOW_COOKIE, path="/api/auth")
    _start_session(resp, user)
    return resp
