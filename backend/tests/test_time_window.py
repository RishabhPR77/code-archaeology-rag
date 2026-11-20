"""Questions about a period: finding the period, and answering from every commit in it."""
from datetime import datetime, timedelta, timezone

import pytest

from app.services import rag
from retrieval.time_window import find_period
from storage import vector_store
from tests.test_repos import _connect_model, _ready_repo, fake_ingestion  # noqa: F401 (fakes cloning)

NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def _day(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


@pytest.mark.parametrize("question, start, end", [
    ("What activity has been done in last 1 month in this repo", "2026-10-12", "2026-11-11"),
    ("What changed in the past two weeks?", "2026-10-28", "2026-11-11"),
    ("Summarise the last month", "2026-10-12", "2026-11-11"),
    ("what happened over the past few days", "2026-11-08", "2026-11-11"),
    ("Anything big in the previous year?", "2025-11-11", "2026-11-11"),
    ("What was merged this month?", "2026-11-01", "2026-11-11"),
    ("What changed since October?", "2026-10-01", "2026-11-11"),
    ("What changed since December?", "2025-12-01", "2026-11-11"),     # December hasn't come yet this year
    ("Commits since 2026-10-15", "2026-10-15", "2026-11-11"),
    ("What was done in October 2025?", "2025-10-01", "2025-11-01"),
    ("What happened during Sept?", "2026-09-01", "2026-10-01"),
    ("Main themes in 2025", "2025-01-01", "2026-01-01"),
    ("what landed yesterday", "2026-11-10", "2026-11-11"),
])
def test_periods_are_found(question, start, end):
    period = find_period(question, NOW)
    assert period is not None, question
    assert (_day(period.start), _day(period.end)) == (start, end)


def test_a_commit_made_just_now_counts():
    from retrieval.time_window import commits_in
    period = find_period("what changed in the last week", NOW)
    ahead = {"metadata": {"timestamp": (NOW + timedelta(minutes=5)).isoformat()}}   # author's clock runs fast
    assert commits_in(period, [ahead]) == [ahead]
    fixed = find_period("what changed in October 2026", NOW)
    assert commits_in(fixed, [{"metadata": {"timestamp": "2026-11-01T00:00:00+00:00"}}]) == []


def test_this_week_starts_on_monday():
    period = find_period("what changed this week?", NOW)
    assert period.start.weekday() == 0 and period.start <= NOW and NOW - period.start < timedelta(days=7)


@pytest.mark.parametrize("question", [
    "Why was the last commit reverted?",
    "How did the auth module change?",
    "May this change break sessions?",
    "What is the latest release?",
    "Who wrote most of the past implementation of caching?",
])
def test_questions_without_a_period(question):
    assert find_period(question, NOW) is None


# ── Answering from every commit in the period ─────────────────────
def _chunk(sha: str, days_ago: float, message: str, now: datetime) -> dict:
    when = (now - timedelta(days=days_ago)).isoformat()
    return {"id": sha, "text": f"[feat] {sha} by dev: {message}\n\nDetails of {message}.",
            "metadata": {"sha": sha, "author": "dev", "email": "dev@x.io", "timestamp": when,
                         "files": "src/app.py", "insertions": 1, "deletions": 0, "has_pr": False,
                         "pr_number": 0, "pr_labels": ""}}


@pytest.fixture
def no_search(monkeypatch):
    """A period question must not go through search at all."""
    def fail(*a, **k):
        raise AssertionError("search was used for a period question")
    monkeypatch.setattr(vector_store.VectorStore, "search", fail)


def test_every_commit_in_the_period_is_used(no_search):
    now = datetime.now(timezone.utc)
    chunks = [_chunk(f"in{i:05d}", days, f"change {i}", now) for i, days in enumerate((2, 5, 9, 14, 20, 28))]
    chunks += [_chunk("old0001", 45, "older change", now), _chunk("old0002", 90, "much older change", now)]
    p = rag.prepare("What activity has been done in last 1 month in this repo", "ns", lambda s, q: "", chunks=chunks)
    assert "These are all 6 commits" in p["prompt"]
    assert all(f"in{i:05d}" in p["prompt"] for i in range(6))
    assert "old0001" not in p["prompt"] and "old0002" not in p["prompt"]
    assert p["prompt"].index("in00005") < p["prompt"].index("in00000")       # oldest first
    assert [s["sha"] for s in p["sources"]][0] == "in00000"                   # newest first in the sources
    assert all(s["score"] is None for s in p["sources"]) and "Re-sync" not in p["prompt"]


def test_an_old_sync_says_to_resync(no_search):
    now = datetime.now(timezone.utc)
    chunks = [_chunk("aaa0001", 20, "a change", now), _chunk("aaa0002", 40, "another", now)]
    synced = now - timedelta(days=10)
    p = rag.prepare("what happened in the last month?", "ns", lambda s, q: "", chunks=chunks, synced_at=synced)
    assert "aaa0001" in p["prompt"] and "Re-sync" in p["prompt"] and _day(synced) in p["prompt"]
    # Synced just now: a quiet stretch at the end of the period isn't staleness
    p = rag.prepare("what happened in the last month?", "ns", lambda s, q: "", chunks=chunks, synced_at=now)
    assert "Re-sync" not in p["prompt"]


def test_an_empty_period_explains_itself(no_search):
    now = datetime.now(timezone.utc)
    chunks = [_chunk("bbb0001", 60, "a change", now), _chunk("bbb0002", 90, "another", now)]
    p = rag.prepare("what changed this week?", "ns", lambda s, q: "", chunks=chunks)
    assert p["prompt"] is None and p["sources"] == []
    assert "no commits" in p["no_answer"] and "Re-sync" in p["no_answer"]


def test_a_long_period_is_listed_one_line_each(no_search):
    now = datetime.now(timezone.utc)
    chunks = [_chunk(f"c{i:06d}", i * 0.5, f"change {i}", now) for i in range(40)]
    p = rag.prepare("summarise the past month", "ns", lambda s, q: "", chunks=chunks)
    assert "These are all 40 commits" in p["prompt"] and "one line each" in p["prompt"]
    assert len(p["sources"]) == 40


def test_period_questions_through_the_api(user_client):
    """The test repository's commits are from January and February 2026."""
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/ask", json={"question": "What was done in January 2026?"})
    assert r.status_code == 200, r.text
    assert sorted(s["sha"] for s in r.json()["sources"]) == ["a1b2c3d", "b2c3d4e"]
    assert all(s["score"] is None for s in r.json()["sources"])

    r = user_client.post(f"/api/repos/{rid}/ask", json={"question": "What happened last week?"})
    assert r.status_code == 200 and r.json()["sources"] == []
    # Just synced, so no Re-sync hint; the answer says what the saved history covers instead
    assert "no commits" in r.json()["answer"] and "2026-01-05 to 2026-02-01" in r.json()["answer"]
    assert "Re-sync" not in r.json()["answer"]
