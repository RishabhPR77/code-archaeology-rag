# app/deps.py
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Repo, User
from app.security import SESSION_COOKIE, decode_session_token


# The only changes the read-only demo account may make: neither stores anything
DEMO_WRITABLE = {"/api/repos/{repo_id}/suspects", "/api/repos/{repo_id}/timeline"}
DEMO_READ_ONLY = "This is a read-only demo. Sign up free to add your own repositories and ask your own questions."


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = decode_session_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
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
    """In-process sliding window. Per instance — put a shared limiter in front if you scale out."""

    def __init__(self, limit: int, window_seconds: int, message: str = "Too many attempts."):
        self.limit, self.window, self.message = limit, window_seconds, message
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def check(self, key: str):
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                retry = int(self.window - (now - q[0])) + 1
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                                    f"{self.message} Try again in {_wait(retry)}.",
                                    headers={"Retry-After": str(retry)})
            q.append(now)


auth_limiter = RateLimiter(limit=10, window_seconds=300)
# Demo visitors share one account; each Who broke it? search costs embedding tokens,
# so it's capped per visitor and across all visitors
DEMO_BUSY = "The demo has a limit on searches. Sign up free to keep going."
demo_limiter = RateLimiter(limit=20, window_seconds=3600, message=DEMO_BUSY)
demo_total_limiter = RateLimiter(limit=300, window_seconds=3600, message=DEMO_BUSY)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
