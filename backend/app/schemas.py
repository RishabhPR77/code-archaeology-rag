# app/schemas.py
import re
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

GITHUB_URL = re.compile(r"^https?://(www\.)?github\.com/([\w.-]+)/([\w.-]+?)(\.git)?/?$")


def as_utc(dt: datetime | None) -> datetime | None:
    # SQLite hands datetimes back naive; everything is stored in UTC
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ── Auth ───────────────────────────────────────────────────────────
class RegisterIn(BaseModel):
    email:    EmailStr
    password: str = Field(min_length=8)
    name:     str = Field(default="", max_length=120)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v: str) -> str:
        if len(v.encode()) > 72:
            raise ValueError("Password must be at most 72 bytes")
        return v


class LoginIn(BaseModel):
    email:    EmailStr
    password: str


class VerifyEmailIn(BaseModel):
    code: str = Field(pattern=r"^\d{6}$")


class UserOut(BaseModel):
    id:               int
    email:            str
    name:             str
    avatar_url:       str | None
    email_verified:   bool
    code_resend_in:   int = 0          # seconds until another sign-up code may be requested
    github_login:     str | None
    github_connected: bool
    google_linked:    bool
    has_password:     bool
    is_admin:        bool
    active_provider: str | None
    active_model:    str | None
    created_at:      datetime


class LimitsOut(BaseModel):
    max_commits:       int
    commit_options:    list[int]
    max_repos:         int
    repos_used:        int
    max_ingests_day:   int
    ingests_today:     int
    repo_ttl_hours:    int
    unlimited:         bool


class MeOut(BaseModel):
    user:   UserOut
    limits: LimitsOut


class AuthConfigOut(BaseModel):
    github_enabled:     bool
    google_enabled:     bool
    email_verification: bool
    contact_email:      str | None


# ── GitHub ─────────────────────────────────────────────────────────
class GitHubInstallationOut(BaseModel):
    id:                   int
    account:              str
    repository_selection: str
    manage_url:           str | None


class GitHubStatusOut(BaseModel):
    enabled:       bool
    connected:     bool
    login:         str | None
    install_url:   str | None
    installations: list[GitHubInstallationOut]
    error:         str | None = None


class GitHubRepoOut(BaseModel):
    full_name:      str
    private:        bool
    html_url:       str
    description:    str | None
    updated_at:     str | None
    default_branch: str | None


# ── Providers ──────────────────────────────────────────────────────
class ProviderOut(BaseModel):
    id:         str
    name:       str
    key_url:    str
    docs_url:   str
    configured: bool
    key_hint:   str | None
    model:      str | None
    active:     bool


class ModelOut(BaseModel):
    id:             str
    name:           str
    context_window: int | None
    max_output:     int | None
    description:    str | None


class SaveKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)

    @field_validator("api_key")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


class SaveKeyOut(BaseModel):
    provider: ProviderOut
    models:   list[ModelOut]


class SelectModelIn(BaseModel):
    model: str = Field(min_length=1, max_length=200)


class ActiveProviderIn(BaseModel):
    provider: str


# ── Repos ──────────────────────────────────────────────────────────
class RepoIn(BaseModel):
    url:         str
    max_commits: int = Field(default=100, ge=10, le=2000)

    @field_validator("url")
    @classmethod
    def _github_only(cls, v: str) -> str:
        v = v.strip()
        if not GITHUB_URL.match(v):
            raise ValueError("Enter a public GitHub repository URL, like https://github.com/pallets/flask")
        return v


class RepoOut(BaseModel):
    id:            str
    url:           str
    full_name:     str
    is_private:    bool
    status:        str
    stage_message: str
    error:         str | None
    warnings:      list[str]
    max_commits:   int
    commit_count:  int
    pr_count:      int
    created_at:    datetime
    ready_at:      datetime | None
    expires_at:    datetime | None


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode:     Literal["detailed", "summary", "bullets"] = "detailed"
    only_pr:  bool = False


class SourceOut(BaseModel):
    sha:       str
    author:    str
    timestamp: str
    files:     list[str]
    score:     float
    has_pr:    bool
    pr_number: int | None
    message:   str


class QueryOut(BaseModel):
    id:         int
    kind:       str
    question:   str
    answer:     str
    mode:       str
    provider:   str
    model:      str
    sources:    list[SourceOut]
    created_at: datetime


class TimelineIn(BaseModel):
    path: str = Field(min_length=1, max_length=300)


class TimelineOut(BaseModel):
    path:     str
    answer:   str | None
    provider: str | None
    model:    str | None
    entries:  list[dict]
