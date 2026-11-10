# app/routers/auth.py
"""Signing up and in with email and a password, confirming the address, resetting a forgotten
password, the authenticator step, and the user's own details.

Replies never reveal whether an email address has an account: sign-up, "resend code" and
"forgot password" answer the same way either way, and the owner is told by email instead."""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.deps import account_limiter, auth_limiter, client_ip, current_user, two_factor_limiter
from app.models import Conversation, Query, Repo, User
from app.schemas import (AuthConfigOut, CodeSentOut, EmailIn, LoginIn, MeOut, NameIn, ProfileOut,
                         RecentQuestionOut, RegisterIn, ResendCodeIn, ResetPasswordIn, TwoFactorCodeIn,
                         TwoFactorRequiredOut, VerifyEmailIn, as_utc)
from app.security import hash_password, verify_password
from app.services import audit, demo, mailer, sessions, two_factor, verification
from app.services.users import sync_admin_flag

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])

WRONG_PASSWORD = "Incorrect email or password."


def _by_email(db: Session, email: str) -> User | None:
    user = db.scalar(select(User).where(User.email == email.lower()))
    return None if user is not None and user.is_demo else user


def _claimed(user: User) -> bool:
    """Someone proved they own this address (a code, Google or GitHub), or it's the demo account."""
    return bool(user.email_verified or user.github_id or user.google_sub or user.is_demo)


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
    sessions.start(response, user)
    return sessions.me(db, user)


# ── Sign up ────────────────────────────────────────────────────────
@router.post("/register", response_model=MeOut | CodeSentOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"register:{client_ip(request)}")
    email = body.email.lower()
    name = body.name.strip() or email.split("@")[0]
    user = db.scalar(select(User).where(User.email == email))   # the demo account too: it can't be claimed

    if not verification.email_configured():
        # Local development without email: there's no other way to tell the person, so say it here
        if user is not None and _claimed(user):
            raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
        user = _save_sign_up(db, user, email, name, body.password, verified=True)
        audit.record(db, user, "account_created", request)
        sessions.start(response, user)
        return sessions.me(db, user)

    if user is not None and _claimed(user):
        # Same work and the same reply as a new sign-up; the owner gets an email instead
        verify_password(body.password, None)
        verification.send_quietly(db, user, "notice")
    else:
        # A sign-up that was never confirmed can't lock the real owner out: whoever proves the
        # address with the code gets the account, with the password they chose
        try:
            user = _save_sign_up(db, user, email, name, body.password, verified=False)
        except IntegrityError:
            db.rollback()
            user = None
        verification.send_quietly(db, user, "verify")
    response.status_code = status.HTTP_202_ACCEPTED
    return CodeSentOut(email=email, resend_in=int(verification.RESEND_COOLDOWN.total_seconds()))


def _save_sign_up(db: Session, user: User | None, email: str, name: str, password: str, verified: bool) -> User:
    if user is None:
        user = User(email=email, email_verified=verified)
        db.add(user)
    user.name, user.password_hash = name, hash_password(password)
    sync_admin_flag(user)
    db.commit()
    return user


@router.post("/verify-email", response_model=MeOut)
def verify_email(body: VerifyEmailIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """Confirm the address with the emailed code. Just after sign-up there's no session yet,
    so the code is checked against the email given, and a correct code signs the person in."""
    auth_limiter.check(f"verify:{client_ip(request)}")
    signed_in = sessions.session_user(request, db)
    if signed_in is not None and not signed_in.is_demo:
        if signed_in.email_verified:
            return sessions.me(db, signed_in)
        user = signed_in
    else:
        user = _by_email(db, body.email) if body.email else None
        if user is not None and user.email_verified:
            user = None      # nothing to confirm: answer like a wrong code
    verification.check_code(db, user, body.code, "verify")
    audit.record(db, user, "account_created", request, "Email address confirmed")
    if user is not signed_in:
        sessions.start(response, user)
        audit.record(db, user, "sign_in", request, sessions.METHODS["email"])
    return sessions.me(db, user)


@router.post("/resend-code", status_code=status.HTTP_204_NO_CONTENT)
def resend_code(request: Request, body: ResendCodeIn | None = None, db: Session = Depends(get_db)):
    auth_limiter.check(f"resend:{client_ip(request)}")
    signed_in = sessions.session_user(request, db)
    if signed_in is not None and not signed_in.is_demo:
        if not signed_in.email_verified:
            try:
                verification.send_code(db, signed_in, "verify")
            except verification.TooSoon as e:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, e.message) from None
        return
    user = _by_email(db, body.email) if body and body.email else None
    if user is not None and not user.email_verified:
        verification.send_quietly(db, user, "verify")


# ── Sign in ────────────────────────────────────────────────────────
@router.post("/login", response_model=MeOut | TwoFactorRequiredOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    auth_limiter.check(f"login:{client_ip(request)}:{email}")
    account_limiter.ensure_allowed(email)
    user = _by_email(db, email)
    # verify_password does the slow check even for unknown emails, so timing reveals nothing either
    if not verify_password(body.password, user.password_hash if user else None):
        account_limiter.add(email)
        if user is not None:
            audit.record(db, user, "sign_in_failed", request)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG_PASSWORD)
    sync_admin_flag(user)
    db.commit()
    return sessions.sign_in(db, request, response, user, "password")


@router.post("/2fa/verify", response_model=MeOut)
def two_factor_sign_in(body: TwoFactorCodeIn, request: Request, response: Response, db: Session = Depends(get_db)):
    """The second step: a code from the authenticator app, or a recovery code."""
    pending = sessions.pending_two_factor(request, db)
    if pending is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "That sign-in expired. Please sign in again.")
    user, method = pending
    two_factor_limiter.check(f"user:{user.id}")
    used = two_factor.verify(user, body.code)
    if used is None:
        audit.record(db, user, "two_factor_failed", request)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code isn't right. Codes change every 30 seconds.")
    db.commit()
    sessions.end_two_factor(response)
    sessions.start(response, user)
    how = sessions.METHODS.get(method, "")
    audit.record(db, user, "sign_in", request,
                 f"{how} and {'a recovery code' if used == 'recovery' else 'an authenticator code'}")
    if used == "recovery":
        left = two_factor.recovery_codes_left(user)
        audit.record(db, user, "recovery_code_used", request, f"{left} left")
        mailer.send_security_alert(user.email, "A recovery code was used to sign in")
    return sessions.me(db, user)


# ── Forgotten password ─────────────────────────────────────────────
@router.post("/forgot-password", status_code=status.HTTP_204_NO_CONTENT)
def forgot_password(body: EmailIn, request: Request, db: Session = Depends(get_db)):
    """Email a reset code if the address has an account. The reply is the same either way."""
    auth_limiter.check(f"forgot:{client_ip(request)}")
    if not verification.email_configured():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Password reset needs email, which isn't set up here.")
    verification.send_quietly(db, _by_email(db, body.email), "reset")


@router.post("/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(body: ResetPasswordIn, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_limiter.check(f"reset:{client_ip(request)}")
    user = _by_email(db, body.email)
    verification.check_code(db, user, body.code, "reset")
    user.password_hash = hash_password(body.password)
    user.email_verified = True                       # the code proved they read this inbox
    user.session_version = (user.session_version or 0) + 1   # every existing session ends
    db.commit()
    sessions.end(response)
    audit.record(db, user, "password_reset", request)
    mailer.send_security_alert(user.email, "Your password was reset")


# ── Session and profile ────────────────────────────────────────────
@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    sessions.end(response)
    sessions.end_two_factor(response)


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return sessions.me(db, user)


@router.patch("/me", response_model=MeOut)
def update_me(body: NameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Change the display name."""
    user.name = body.name
    db.commit()
    return sessions.me(db, user)


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
