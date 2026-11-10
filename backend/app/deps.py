# app/deps.py
import hashlib
import ipaddress
from datetime import timedelta

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, get_db
from app.models import RateLimitHit, Repo, User, utcnow
from app.schemas import as_utc
from app.security import SESSION_COOKIE, decode_session_token


# The only changes the read-only demo account may make: neither stores anything
DEMO_WRITABLE = {"/api/repos/{repo_id}/suspects", "/api/repos/{repo_id}/timeline"}
DEMO_READ_ONLY = "This is a read-only demo. Sign up free to add your own repositories and ask your own questions."


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    session = decode_session_token(token) if token else None
    user = db.get(User, session[0]) if session else None
    # A token from before "sign out everywhere" carries an old version, so it no longer works
    if user is None or session[1] != (user.session_version or 0):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    # Every route that changes something goes through here, so the demo is read-only by default:
    # a new endpoint stays closed to it unless it's added to DEMO_WRITABLE
    if user.is_demo and request.method not in ("GET", "HEAD", "OPTIONS"):
        route = request.scope.get("route")
        if getattr(route, "path", None) not in DEMO_WRITABLE:
            raise HTTPException(status.HTTP_403_FORBIDDEN, DEMO_READ_ONLY)
    return user


def verified_user(user: User = Depends(current_user)) -> User:
    """Everything beyond sign-up needs a confirmed email address."""
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Confirm your email address to continue")
    return user


def owned_repo(repo_id: str, user: User = Depends(verified_user),
               db: Session = Depends(get_db)) -> Repo:
    repo = db.get(Repo, repo_id)
    if repo is None or repo.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Repository not found")
    return repo


def _wait(seconds: int) -> str:
    return f"{seconds}s" if seconds < 120 else f"{round(seconds / 60)} minutes"


class RateLimiter:
    """A sliding window: at most `limit` attempts per key in any `window_seconds`.

    Attempts are rows in the database rather than in this process's memory, so a restart doesn't
    reset the count and several servers would share it. Keys are hashed before they're stored."""

    def __init__(self, name: str, limit: int, window_seconds: int, message: str = "Too many attempts."):
        self.name, self.limit, self.window, self.message = name, limit, window_seconds, message

    def _key(self, key: str) -> str:
        return hashlib.sha256(f"{self.name}|{key}".encode()).hexdigest()

    def _refuse_if_full(self, db: Session, digest: str):
        now = utcnow()
        times = db.scalars(select(RateLimitHit.at)
                           .where(RateLimitHit.key == digest, RateLimitHit.at > now - timedelta(seconds=self.window))
                           .order_by(RateLimitHit.at).limit(self.limit)).all()
        if len(times) >= self.limit:
            retry = max(1, int((as_utc(times[0]) + timedelta(seconds=self.window) - now).total_seconds()) + 1)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                f"{self.message} Try again in {_wait(retry)}.",
                                headers={"Retry-After": str(retry)})

    def check(self, key: str):
        """Count this attempt, or refuse it with 429 if the window is full."""
        digest = self._key(key)
        with SessionLocal() as db:
            self._refuse_if_full(db, digest)
            db.add(RateLimitHit(key=digest, at=utcnow()))
            db.commit()

    def ensure_allowed(self, key: str):
        """Refuse if the window is full, without counting this attempt (see `add`)."""
        with SessionLocal() as db:
            self._refuse_if_full(db, self._key(key))

    def add(self, key: str):
        """Count an attempt, e.g. only the failed ones."""
        with SessionLocal() as db:
            db.add(RateLimitHit(key=self._key(key), at=utcnow()))
            db.commit()


def prune_rate_limits() -> int:
    """Forget attempts older than any window."""
    with SessionLocal() as db:
        result = db.execute(delete(RateLimitHit).where(RateLimitHit.at < utcnow() - timedelta(days=1)))
        db.commit()
        return result.rowcount or 0


auth_limiter = RateLimiter("auth", limit=10, window_seconds=300)
# Wrong passwords for one account from anywhere. Per-IP limits alone can't stop guesses spread over
# many addresses; only failures count, so the owner signing in normally is never held back.
account_limiter = RateLimiter("account", limit=20, window_seconds=3600,
                              message="Too many wrong passwords for this account.")
two_factor_limiter = RateLimiter("2fa", limit=10, window_seconds=300, message="Too many codes tried.")
# Every search embeds the question with the shared Pinecone allowance, so each account gets a fair share
search_limiter = RateLimiter("search", limit=150, window_seconds=3600,
                             message="That's a lot of searches in the last hour, so this one was held back.")

# Demo visitors share one account; each Who broke it? search costs embedding tokens,
# so it's capped per visitor and across all visitors
DEMO_BUSY = "The demo has a limit on searches. Sign up free to keep going."
demo_limiter = RateLimiter("demo", limit=20, window_seconds=3600, message=DEMO_BUSY)
demo_total_limiter = RateLimiter("demo-all", limit=300, window_seconds=3600, message=DEMO_BUSY)


def client_ip(request: Request) -> str:
    """The visitor's address. Behind a proxy that's a header the proxy sets (CLIENT_IP_HEADER);
    X-Forwarded-For is never used, because a visitor can put any address in it."""
    header = get_settings().client_ip_header
    if header:
        value = request.headers.get(header, "").strip()
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.client.host if request.client else "unknown"
