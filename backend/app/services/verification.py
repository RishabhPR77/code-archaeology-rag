# app/services/verification.py
"""Six-digit email codes: confirming an address at sign-up ("verify") and resetting a password
("reset"). Only an HMAC of each code is stored."""
import logging
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailCode, User, utcnow
from app.schemas import as_utc
from app.security import sign, signature_matches
from app.services import mailer

log = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_SENDS_PER_WINDOW = 5
# One message for every way a code can fail (wrong, expired, used up, or no such account),
# so trying codes can't tell anyone whether an email address is registered
BAD_CODE = "That code didn't work. Check it's the newest one we sent, or request a new code."


class TooSoon(Exception):
    """A code was sent moments ago, or too many were sent this hour."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def _message(user_id: int, purpose: str, code: str) -> str:
    # Sign-up codes keep the original format, so codes emailed before this change still verify
    return f"{user_id}:{code}" if purpose == "verify" else f"{purpose}:{user_id}:{code}"


def record(db: Session, user: User, purpose: str) -> EmailCode | None:
    return db.scalar(select(EmailCode).where(EmailCode.user_id == user.id, EmailCode.purpose == purpose))


def resend_in(db: Session, user: User, purpose: str = "verify") -> int:
    rec = record(db, user, purpose)
    if rec is None:
        return 0
    return max(0, int((as_utc(rec.last_sent_at) + RESEND_COOLDOWN - utcnow()).total_seconds() + 0.999))


def _throttle(db: Session, user: User, purpose: str) -> EmailCode:
    """The user's record for this purpose, after checking the resend limits. Raises TooSoon."""
    now = utcnow()
    rec = record(db, user, purpose)
    if rec is None:
        rec = EmailCode(user_id=user.id, purpose=purpose, code_hash="", expires_at=now,
                        attempts=0, last_sent_at=now, window_started=now, sends_in_window=0)
        db.add(rec)
        return rec
    wait = as_utc(rec.last_sent_at) + RESEND_COOLDOWN - now
    if wait.total_seconds() > 0:
        raise TooSoon(f"Please wait {int(wait.total_seconds()) + 1}s before requesting another code.")
    if as_utc(rec.window_started) + SEND_WINDOW < now:
        rec.window_started, rec.sends_in_window = now, 0
    if rec.sends_in_window >= MAX_SENDS_PER_WINDOW:
        raise TooSoon("Too many codes requested. Try again in an hour.")
    return rec


def send_code(db: Session, user: User, purpose: str = "verify"):
    """Create (or replace) the user's code for this purpose and email it. Raises TooSoon,
    or HTTPException 502 if the email service fails."""
    rec = _throttle(db, user, purpose)
    now = utcnow()
    code = f"{secrets.randbelow(1_000_000):06d}"
    rec.code_hash = sign(_message(user.id, purpose, code))
    rec.expires_at = now + CODE_TTL
    rec.attempts = 0
    rec.last_sent_at = now
    rec.sends_in_window += 1
    db.commit()
    minutes = int(CODE_TTL.total_seconds() // 60)
    try:
        if purpose == "reset":
            mailer.send_reset_code(user.email, code, minutes)
        else:
            mailer.send_verification_code(user.email, code, minutes)
    except mailer.EmailError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{e}. Please try again shortly.") from e


def send_quietly(db: Session, user: User | None, purpose: str):
    """Send a code if possible and say nothing either way: the caller's reply must look the same
    whether or not the account exists."""
    if user is None or user.is_demo:
        return
    try:
        if purpose == "notice":
            _throttle(db, user, "notice")
            rec = record(db, user, "notice")
            rec.last_sent_at, rec.sends_in_window = utcnow(), rec.sends_in_window + 1
            db.commit()
            mailer.send_account_exists(user.email)
        else:
            send_code(db, user, purpose)
    except (TooSoon, HTTPException, mailer.EmailError) as e:
        db.rollback()
        log.info("Didn't send a %s email to user %s: %s", purpose, user.id, getattr(e, "message", e))


def check_code(db: Session, user: User | None, code: str, purpose: str = "verify"):
    """Accept the code (and use it up) or raise 400 with the same message whatever went wrong."""
    rec = record(db, user, purpose) if user is not None else None
    if rec is None or as_utc(rec.expires_at) < utcnow() or rec.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    if not signature_matches(_message(user.id, purpose, code), rec.code_hash):
        rec.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, BAD_CODE)
    db.delete(rec)
    if purpose == "verify":
        user.email_verified = True
    db.commit()


def email_configured() -> bool:
    return get_settings().email_verification_enabled
