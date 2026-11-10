# app/services/demo.py
"""The public demo: one shared, read-only account that owns the sample repositories.

An admin hands one of their ingested repositories (with its chats) to this account from the repository
page. Anyone can then open it from "Try the demo" without signing up. The account can read everything
it owns, rank Who broke it? suspects and trace files, but it can't change anything: app/deps.py refuses
every other write for it.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Repo, User

# Not a deliverable address, so nobody can register it or sign in to it
DEMO_EMAIL = "demo@demo.code-archaeologist"


def demo_user(db: Session, create: bool = False) -> User | None:
    user = db.scalar(select(User).where(User.is_demo.is_(True)))
    if user is None and create:
        user = User(email=DEMO_EMAIL, name="Demo", password_hash=None, email_verified=True, is_demo=True)
        db.add(user)
        db.flush()
    return user


def demo_repos(db: Session) -> list[Repo]:
    """The demo's repositories that are ready to explore, newest first."""
    user = demo_user(db)
    if user is None:
        return []
    return list(db.scalars(select(Repo).where(Repo.user_id == user.id, Repo.status == "ready")
                           .order_by(Repo.created_at.desc())))


def make_demo(db: Session, repo: Repo) -> Repo:
    """Hand a repository, with its chats, to the demo account. Demo repositories never expire."""
    repo.user_id = demo_user(db, create=True).id
    repo.expires_at = None
    db.commit()
    return repo
