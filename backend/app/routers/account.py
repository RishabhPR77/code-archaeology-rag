# app/routers/account.py
"""Account security for a signed-in user: password, two-step sign-in, sessions, the activity log,
and deleting the account."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import auth_limiter, current_user, two_factor_limiter, verified_user
from app.models import Repo, User
from app.schemas import (ChangePasswordIn, DeleteAccountIn, MeOut, RecoveryCodesOut, SecurityEventOut,
                         TwoFactorCodeIn, TwoFactorSetupOut)
from app.security import hash_password, verify_password
from app.services import audit, ingest, mailer, sessions, two_factor

router = APIRouter(prefix="/api/auth", tags=["account"])


def _require_code(user: User, code: str | None, request: Request, db: Session):
    """Sensitive changes on an account with two-step sign-in need a current code too."""
    two_factor_limiter.check(f"user:{user.id}")
    if two_factor.verify(user, code or "") is None:
        audit.record(db, user, "two_factor_failed", request)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code isn't right. Codes change every 30 seconds.")


# ── Password ───────────────────────────────────────────────────────
@router.post("/password", response_model=MeOut)
def change_password(body: ChangePasswordIn, request: Request, response: Response,
                    user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """Change the password (or add one to a Google/GitHub account). Other devices are signed out."""
    auth_limiter.check(f"password:{user.id}")
    had_password = user.password_hash is not None
    if had_password and not verify_password(body.current_password or "", user.password_hash):
        audit.record(db, user, "sign_in_failed", request, "While changing the password")
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Your current password isn't right.")
    if had_password and body.current_password == body.new_password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "The new password is the same as the current one.")
    user.password_hash = hash_password(body.new_password)
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    sessions.start(response, user)          # this device stays signed in with a fresh token
    audit.record(db, user, "password_changed" if had_password else "password_set", request)
    mailer.send_security_alert(user.email, "Your password was changed" if had_password else "A password was added")
    return sessions.me(db, user)


# ── Sessions ───────────────────────────────────────────────────────
@router.post("/logout-everywhere", status_code=status.HTTP_204_NO_CONTENT)
def logout_everywhere(request: Request, response: Response, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    """End every session this account has, on every device: tokens carry the old version and stop working."""
    user.session_version = (user.session_version or 0) + 1
    db.commit()
    sessions.end(response)
    audit.record(db, user, "signed_out_everywhere", request)


# ── Two-step sign-in ───────────────────────────────────────────────
@router.post("/2fa/setup", response_model=TwoFactorSetupOut)
def two_factor_setup(user: User = Depends(verified_user), db: Session = Depends(get_db)):
    """A new secret for the authenticator app. Nothing changes until a code confirms it."""
    if two_factor.enabled(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is already on.")
    secret, uri, qr = two_factor.start_setup(user)
    db.commit()
    return TwoFactorSetupOut(secret=secret, uri=uri, qr_svg=qr)


@router.post("/2fa/enable", response_model=RecoveryCodesOut)
def two_factor_enable(body: TwoFactorCodeIn, request: Request, user: User = Depends(verified_user),
                      db: Session = Depends(get_db)):
    two_factor_limiter.check(f"user:{user.id}")
    codes = two_factor.confirm_setup(user, body.code)
    if codes is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "That code isn't right. Check the app shows Code Archaeologist and try the newest code.")
    db.commit()
    audit.record(db, user, "two_factor_enabled", request)
    mailer.send_security_alert(user.email, "Two-step sign-in was turned on")
    return RecoveryCodesOut(codes=codes)


@router.post("/2fa/disable", response_model=MeOut)
def two_factor_disable(body: TwoFactorCodeIn, request: Request, user: User = Depends(verified_user),
                       db: Session = Depends(get_db)):
    _require_code(user, body.code, request, db)
    two_factor.disable(user)
    db.commit()
    audit.record(db, user, "two_factor_disabled", request)
    mailer.send_security_alert(user.email, "Two-step sign-in was turned off")
    return sessions.me(db, user)


@router.post("/2fa/recovery-codes", response_model=RecoveryCodesOut)
def two_factor_new_recovery_codes(body: TwoFactorCodeIn, request: Request, user: User = Depends(verified_user),
                                  db: Session = Depends(get_db)):
    """Replace the recovery codes; the old ones stop working."""
    if not two_factor.enabled(user):
        raise HTTPException(status.HTTP_409_CONFLICT, "Two-step sign-in is off.")
    _require_code(user, body.code, request, db)
    codes = two_factor.new_recovery_codes(user)
    db.commit()
    audit.record(db, user, "recovery_codes_created", request)
    return RecoveryCodesOut(codes=codes)


# ── Activity ───────────────────────────────────────────────────────
@router.get("/activity", response_model=list[SecurityEventOut])
def activity(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The account's recent security events, newest first."""
    return audit.recent(db, user)


# ── Delete the account ─────────────────────────────────────────────
@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(body: DeleteAccountIn, request: Request, response: Response,
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Delete the account and everything in it: repositories (and their search index), chats,
    keys and history. Typing the email address confirms it's deliberate."""
    if body.confirm_email.strip().lower() != user.email.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Type your email address exactly to confirm.")
    if two_factor.enabled(user):
        _require_code(user, body.code, request, db)
    for repo in db.scalars(select(Repo).where(Repo.user_id == user.id)):
        ingest.delete_repo_data(repo)
    email = user.email
    db.delete(user)
    db.commit()
    sessions.end(response)
    mailer.send_security_alert(email, "Your account was deleted")
