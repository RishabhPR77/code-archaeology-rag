# app/models.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, false, true)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id:               Mapped[int] = mapped_column(primary_key=True)
    email:            Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name:             Mapped[str] = mapped_column(String(120), default="")
    password_hash:    Mapped[str | None] = mapped_column(String(100))   # None for OAuth-only accounts
    # Accounts that existed before verification was added are treated as verified
    email_verified:   Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    google_sub:       Mapped[str | None] = mapped_column(String(64), unique=True)
    github_id:        Mapped[int | None] = mapped_column(Integer, unique=True)
    github_login:     Mapped[str | None] = mapped_column(String(100))
    # GitHub App user tokens: 8h access token + 6-month refresh token, both encrypted
    github_token_enc:          Mapped[str | None] = mapped_column(Text)
    github_token_expires_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    github_refresh_enc:        Mapped[str | None] = mapped_column(Text)
    github_refresh_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    avatar_url:       Mapped[str | None] = mapped_column(String(500))
    is_admin:         Mapped[bool] = mapped_column(Boolean, default=False)
    active_provider:  Mapped[str | None] = mapped_column(String(32))
    created_at:       Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    credentials: Mapped[list["ProviderCredential"]] = relationship(
        back_populates="user", cascade="all, delete-orphan")
    repos: Mapped[list["Repo"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class ProviderCredential(Base):
    """One encrypted LLM API key per user per provider."""
    __tablename__ = "provider_credentials"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    id:         Mapped[int] = mapped_column(primary_key=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    provider:   Mapped[str] = mapped_column(String(32))
    key_enc:    Mapped[str] = mapped_column(Text)
    key_hint:   Mapped[str] = mapped_column(String(32))
    model:      Mapped[str | None] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="credentials")


class Repo(Base):
    __tablename__ = "repos"

    id:            Mapped[str] = mapped_column(String(32), primary_key=True,
                                               default=lambda: uuid.uuid4().hex)
    user_id:       Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    url:           Mapped[str] = mapped_column(String(300))
    full_name:     Mapped[str] = mapped_column(String(200))             # owner/name
    is_private:    Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    namespace:     Mapped[str] = mapped_column(String(200), unique=True)
    max_commits:   Mapped[int] = mapped_column(Integer)
    status:        Mapped[str] = mapped_column(String(20), default="queued")
    stage_message: Mapped[str] = mapped_column(String(300), default="Waiting to start")
    error:         Mapped[str | None] = mapped_column(Text)
    warnings:      Mapped[str] = mapped_column(Text, default="")       # newline-separated
    commit_count:  Mapped[int] = mapped_column(Integer, default=0)
    pr_count:      Mapped[int] = mapped_column(Integer, default=0)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user:    Mapped[User] = relationship(back_populates="repos")
    data:    Mapped["RepoData | None"] = relationship(cascade="all, delete-orphan", lazy="select")
    queries: Mapped[list["Query"]] = relationship(cascade="all, delete-orphan")


class RepoData(Base):
    """Commit chunks for a repo, kept apart so repo listings don't load the blob."""
    __tablename__ = "repo_data"

    repo_id:     Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True)
    chunks_json: Mapped[str] = mapped_column(Text)


class Query(Base):
    __tablename__ = "queries"

    id:           Mapped[int] = mapped_column(primary_key=True)
    repo_id:      Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    kind:         Mapped[str] = mapped_column(String(16))                # ask | timeline
    question:     Mapped[str] = mapped_column(Text)
    answer:       Mapped[str] = mapped_column(Text)
    mode:         Mapped[str] = mapped_column(String(20), default="detailed")
    provider:     Mapped[str] = mapped_column(String(32))
    model:        Mapped[str] = mapped_column(String(200))
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailVerification(Base):
    """The pending sign-up code for a user. Only an HMAC of the code is stored."""
    __tablename__ = "email_verifications"

    user_id:         Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code_hash:       Mapped[str] = mapped_column(String(64))
    expires_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts:        Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)
    window_started:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class IngestEvent(Base):
    """One row per ingest started — survives repo deletion so daily limits hold."""
    __tablename__ = "ingest_events"

    id:         Mapped[int] = mapped_column(primary_key=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
