# app/deps.py
import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Repo, User
from app.security import SESSION_COOKIE, decode_session_token


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    user_id = decode_session_token(token) if token else None
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
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


class RateLimiter:
    """In-process sliding window. Per instance — put a shared limiter in front if you scale out."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
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
                                    f"Too many attempts. Try again in {retry}s.",
                                    headers={"Retry-After": str(retry)})
            q.append(now)


auth_limiter = RateLimiter(limit=10, window_seconds=300)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
