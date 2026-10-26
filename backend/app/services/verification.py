# app/services/verification.py
"""Six-digit email codes for sign-up. Only an HMAC of the code is stored."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import EmailVerification, User, utcnow
from app.schemas import as_utc
from app.services import mailer

CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5
RESEND_COOLDOWN = timedelta(seconds=60)
SEND_WINDOW = timedelta(hours=1)
MAX_SENDS_PER_WINDOW = 5


def _hash(user_id: int, code: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def send_code(db: Session, user: User):
    """Create (or replace) the user's code and email it, enforcing resend limits."""
    now = utcnow()
    record = db.get(EmailVerification, user.id)
    if record is not None:
        wait = as_utc(record.last_sent_at) + RESEND_COOLDOWN - now
        if wait.total_seconds() > 0:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                f"Please wait {int(wait.total_seconds()) + 1}s before requesting another code.")
        if as_utc(record.window_started) + SEND_WINDOW < now:
            record.window_started, record.sends_in_window = now, 0
        if record.sends_in_window >= MAX_SENDS_PER_WINDOW:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                "Too many codes requested. Try again in an hour.")
    else:
        record = EmailVerification(user_id=user.id, window_started=now, sends_in_window=0)
        db.add(record)

    code = f"{secrets.randbelow(1_000_000):06d}"
    record.code_hash = _hash(user.id, code)
    record.expires_at = now + CODE_TTL
    record.attempts = 0
    record.last_sent_at = now
    record.sends_in_window += 1
    db.commit()
    try:
        mailer.send_verification_code(user.email, code, int(CODE_TTL.total_seconds() // 60))
    except mailer.EmailError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"{e}. Please try again shortly.") from e


def check_code(db: Session, user: User, code: str):
    record = db.get(EmailVerification, user.id)
    if record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Request a new code first.")
    if as_utc(record.expires_at) < utcnow():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That code has expired. Request a new one.")
    if record.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Too many wrong codes. Request a new one.")
    if not hmac.compare_digest(record.code_hash, _hash(user.id, code)):
        record.attempts += 1
        db.commit()
        left = MAX_ATTEMPTS - record.attempts
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"That code isn't right. {left} attempt{'s' if left != 1 else ''} left."
                            if left else "Too many wrong codes. Request a new one.")
    user.email_verified = True
    db.delete(record)
    db.commit()
