# app/schemas.py
import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

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
    is_demo:         bool = False      # the shared, read-only demo account
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


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Name can't be blank")
        return v.strip()


class RecentQuestionOut(BaseModel):
    question:   str
    repo_id:    str
    repo:       str           # owner/name
    chat_id:    int | None
    created_at: datetime


class ProfileOut(BaseModel):
    """What a user has done here, for their profile page."""
    repos:           int
    ready_repos:     int
    commits_indexed: int
    prs_linked:      int
    questions:       int
    chats:           int
    recent:          list[RecentQuestionOut]


class AuthConfigOut(BaseModel):
    github_enabled:     bool
    google_enabled:     bool
    email_verification: bool
    contact_email:      str | None
    demo_available:     bool = False   # a sample repository can be explored without signing up


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
# How far back a commit range may reach, counted from the newest commit. Deeper clones get slow
# and large on a small server.
MAX_COMMIT_REACH = 5000


class RepoIn(BaseModel):
    url:          str
    max_commits:  int = Field(default=100, ge=10, le=2000)
    # Commit 1 is the newest. Skipping 100 and taking 100 ingests commits 101-200.
    skip_commits: int = Field(default=0, ge=0, le=MAX_COMMIT_REACH)

    @model_validator(mode="after")
    def _within_reach(self):
        if self.skip_commits + self.max_commits > MAX_COMMIT_REACH:
            raise ValueError(f"A range can reach back at most {MAX_COMMIT_REACH:,} commits")
        return self

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
    skip_commits:  int = 0
    commit_count:  int
    pr_count:      int
    created_at:    datetime
    ready_at:      datetime | None
    expires_at:    datetime | None


class CommitBriefOut(BaseModel):
    number:  int        # 1 = the newest commit
    sha:     str
    message: str        # first line
    date:    str | None


class RangePreviewOut(BaseModel):
    """What a commit range covers, so the user can see it before ingesting."""
    full_name: str
    total:     int                      # commits on the default branch
    reach:     int                      # how far back a range may go
    newest:    CommitBriefOut | None    # the first commit in the range
    oldest:    CommitBriefOut | None    # the last commit in the range


class AskIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    mode:     Literal["detailed", "summary", "bullets"] = "detailed"
    only_pr:  bool = False
    conversation_id: int | None = None   # None starts a new chat


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
    conversation_id: int | None
    question:   str
    search_query: str | None
    answer:     str
    mode:       str
    provider:   str
    model:      str
    sources:    list[SourceOut]
    stopped:    bool = False   # the user stopped it part-way; `answer` is what was written until then
    created_at: datetime


class StoppedIn(AskIn):
    """An answer the user stopped part-way, sent back by the page so the chat keeps what was written."""
    answer:       str = Field(min_length=1, max_length=100_000)
    search_query: str | None = Field(default=None, max_length=2000)
    sources:      list[SourceOut] = Field(default_factory=list, max_length=100)


class ConversationOut(BaseModel):
    id:         int
    title:      str
    questions:  int
    created_at: datetime
    updated_at: datetime


class SuspectsIn(BaseModel):
    description: str = Field(min_length=10, max_length=5000)
    since:       date | None = None   # only commits on or after this day are suspects


class SuspectsOut(BaseModel):
    suspects:        list[dict]
    mentioned_files: list[str]
    answer:          str | None     # None when no model is connected
    provider:        str | None
    model:           str | None


class TimelineIn(BaseModel):
    path:  str = Field(min_length=1, max_length=300)
    match: Literal["contains", "exact", "folder"] = "contains"


class TimelineOut(BaseModel):
    path:     str
    answer:   str | None
    provider: str | None
    model:    str | None
    entries:  list[dict]
