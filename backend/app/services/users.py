# app/services/users.py
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import IngestEvent, ProviderCredential, Repo, User, utcnow
from app.schemas import LimitsOut, UserOut, as_utc

COMMIT_OPTIONS = (50, 100, 200, 300, 500)


def credential(db: Session, user: User, provider: str) -> ProviderCredential | None:
    return db.scalar(select(ProviderCredential).where(
        ProviderCredential.user_id == user.id, ProviderCredential.provider == provider))


def user_out(db: Session, user: User) -> UserOut:
    cred = credential(db, user, user.active_provider) if user.active_provider else None
    return UserOut(id=user.id, email=user.email, name=user.name, avatar_url=user.avatar_url,
                   github_login=user.github_login, has_password=user.password_hash is not None,
                   is_admin=user.is_admin, active_provider=user.active_provider,
                   active_model=cred.model if cred else None, created_at=as_utc(user.created_at))


def limits_for(db: Session, user: User) -> LimitsOut:
    s = get_settings()
    unlimited = user.is_admin
    max_commits = max(COMMIT_OPTIONS) if unlimited else s.max_commits
    repos_used = db.scalar(select(func.count()).select_from(Repo).where(Repo.user_id == user.id))
    ingests_today = db.scalar(select(func.count()).select_from(IngestEvent).where(
        IngestEvent.user_id == user.id, IngestEvent.created_at > utcnow() - timedelta(days=1)))
    return LimitsOut(
        max_commits=max_commits,
        commit_options=[c for c in COMMIT_OPTIONS if c <= max_commits] or [max_commits],
        max_repos=s.max_repos_per_user, repos_used=repos_used,
        max_ingests_day=s.max_ingests_per_day, ingests_today=ingests_today,
        repo_ttl_hours=s.repo_ttl_hours, unlimited=unlimited,
    )


def sync_admin_flag(user: User):
    user.is_admin = user.email.lower() in get_settings().admin_email_set
