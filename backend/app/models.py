# app/models.py
import uuid
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
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
    # The shared, read-only account behind "Try the demo"; it never signs in with a password
    is_demo:          Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    active_provider:  Mapped[str | None] = mapped_column(String(32))
    # Every session token carries this number. Raising it ends all of the user's sessions at once,
    # which a stateless token can't do on its own ("sign out everywhere")
    session_version:  Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Two-step sign-in with an authenticator app (TOTP). The secret is encrypted like API keys.
    # Pending: set up but not confirmed with a first code yet. Last step: the newest code used,
    # so the same code can't be used twice. Recovery codes: HMACs of the unused ones.
    totp_secret_enc:      Mapped[str | None] = mapped_column(Text)
    totp_pending_enc:     Mapped[str | None] = mapped_column(Text)
    totp_enabled_at:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    totp_last_step:       Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    recovery_codes_json:  Mapped[str | None] = mapped_column(Text)
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
    # Newest commits skipped, to ingest a window further back (0 = the latest commits)
    skip_commits:  Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status:        Mapped[str] = mapped_column(String(20), default="queued")
    stage_message: Mapped[str] = mapped_column(String(300), default="Waiting to start")
    error:         Mapped[str | None] = mapped_column(Text)
    warnings:      Mapped[str] = mapped_column(Text, default="")       # newline-separated
    commit_count:  Mapped[int] = mapped_column(Integer, default=0)
    pr_count:      Mapped[int] = mapped_column(Integer, default=0)
    created_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ready_at:      Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at:    Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Starts of this ingest; a restart resumes it, but not forever (a repo that crashes the server would loop)
    ingest_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    user:    Mapped[User] = relationship(back_populates="repos")
    data:    Mapped["RepoData | None"] = relationship(cascade="all, delete-orphan", lazy="select")
    queries: Mapped[list["Query"]] = relationship(cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(cascade="all, delete-orphan")


class RepoData(Base):
    """Commit chunks for a repo, kept apart so repo listings don't load the blob."""
    __tablename__ = "repo_data"

    repo_id:      Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), primary_key=True)
    chunks_json:  Mapped[str] = mapped_column(Text)
    # Bug fixes traced to their likely origins (see ingestion/bug_origins.py); None until computed
    origins_json: Mapped[str | None] = mapped_column(Text)


class Conversation(Base):
    """A chat on the Ask tab: one thread of questions about a repo."""
    __tablename__ = "conversations"

    id:         Mapped[int] = mapped_column(primary_key=True)
    repo_id:    Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    title:      Mapped[str] = mapped_column(String(200))                 # the first question, shortened
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    queries: Mapped[list["Query"]] = relationship(cascade="all, delete-orphan")


class Query(Base):
    __tablename__ = "queries"

    id:           Mapped[int] = mapped_column(primary_key=True)
    repo_id:      Mapped[str] = mapped_column(ForeignKey("repos.id", ondelete="CASCADE"), index=True)
    kind:         Mapped[str] = mapped_column(String(16))                # ask | timeline
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True)   # set for every ask
    question:     Mapped[str] = mapped_column(Text)
    search_query: Mapped[str | None] = mapped_column(Text)              # a follow-up, rewritten to stand alone
    answer:       Mapped[str] = mapped_column(Text)
    mode:         Mapped[str] = mapped_column(String(20), default="detailed")
    provider:     Mapped[str] = mapped_column(String(32))
    model:        Mapped[str] = mapped_column(String(200))
    sources_json: Mapped[str] = mapped_column(Text, default="[]")
    stopped:      Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())   # stopped part-way
    created_at:   Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EmailCode(Base):
    """A six-digit code emailed to a user: confirming their address ("verify") or resetting their
    password ("reset"). "notice" rows only throttle the "you already have an account" email.
    Only an HMAC of the code is stored."""
    __tablename__ = "email_codes"
    __table_args__ = (UniqueConstraint("user_id", "purpose"),)

    id:              Mapped[int] = mapped_column(primary_key=True)
    user_id:         Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose:         Mapped[str] = mapped_column(String(16))
    code_hash:       Mapped[str] = mapped_column(String(64))
    expires_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts:        Mapped[int] = mapped_column(Integer, default=0)
    last_sent_at:    Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sends_in_window: Mapped[int] = mapped_column(Integer, default=1)
    window_started:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RateLimitHit(Base):
    """One attempt counted by a rate limiter. Kept in the database, not in memory, so limits survive
    a restart and every server shares them. The key is a hash: no raw IPs or emails are stored."""
    __tablename__ = "rate_limit_hits"
    __table_args__ = (Index("ix_rate_limit_hits_key_at", "key", "at"),)

    id:  Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64))
    at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SecurityEvent(Base):
    """What happened to an account and roughly where from, shown to its owner under Security activity."""
    __tablename__ = "security_events"

    id:         Mapped[int] = mapped_column(primary_key=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind:       Mapped[str] = mapped_column(String(40))
    detail:     Mapped[str] = mapped_column(String(200), default="")
    ip:         Mapped[str] = mapped_column(String(64), default="")      # shortened, e.g. 203.0.113.x
    device:     Mapped[str] = mapped_column(String(120), default="")     # e.g. Chrome on Windows
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class IngestEvent(Base):
    """One row per ingest started — survives repo deletion so daily limits hold."""
    __tablename__ = "ingest_events"

    id:         Mapped[int] = mapped_column(primary_key=True)
    user_id:    Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
