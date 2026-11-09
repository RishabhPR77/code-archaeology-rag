from types import SimpleNamespace

import pytest

from app.services import ingest
from ingestion.git_loader import CommitRecord
from ingestion.github_enricher import FetchResult, PRRecord


def _commit(sha, msg, author, ts, files):
    return CommitRecord(sha=sha * 8, message=msg, author=author, email=f"{author}@x.io", timestamp=ts,
                        files_changed=files, insertions=10, deletions=2, diff="+ code", parent_shas=[])


COMMITS = [
    _commit("a1b2c3d4e", "fix session cookie expiry bug", "alice", "2026-01-05T10:00:00", ["src/sessions.py"]),
    _commit("b2c3d4e5f", "add oauth login feature", "bob", "2026-01-12T10:00:00", ["src/auth.py", "src/sessions.py"]),
    _commit("c3d4e5f6a", "refactor auth module", "alice", "2026-02-01T10:00:00", ["src/auth.py", "README.md"]),
]
PR = PRRecord(number=42, title="add oauth login feature", body="Adds OAuth so users can sign in.",
              author="bob", merge_commit_sha="b2c3d4e5f" * 8, merged_at="2026-01-12T10:00:00",
              labels=["auth"], linked_issues=[], review_comments=[], review_summaries=[], discussion=[])


ORIGINS = [{"sha": "a1b2c3d", "message": "fix session cookie expiry bug", "author": "alice",
            "timestamp": "2026-01-05T10:00:00", "status": "traced", "older_lines": 0, "days": 16,
            "origins": [{"sha": "9e8d7c6", "message": "add session cookies", "author": "bob",
                         "timestamp": "2025-12-20T10:00:00", "lines": 3, "ingested": False}]}]


@pytest.fixture(autouse=True)
def fake_ingestion(monkeypatch):
    monkeypatch.setattr(ingest.git.Repo, "clone_from", lambda *a, **k: None)
    monkeypatch.setattr(ingest, "load_commits", lambda path, max_count: COMMITS)
    monkeypatch.setattr(ingest, "fetch_prs", lambda *a, **k: FetchResult(prs=[PR], warnings=[]))
    monkeypatch.setattr(ingest, "find_bug_origins", lambda path, commits: ORIGINS)


def _ready_repo(client):
    r = client.post("/api/repos", json={"url": "https://github.com/pallets/flask", "max_commits": 50})
    assert r.status_code == 202, r.text
    repo = client.get(f"/api/repos/{r.json()['id']}").json()
    assert repo["status"] == "ready", repo
    return repo


def _connect_model(client):
    client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    client.put("/api/providers/anthropic/model", json={"model": "claude-test-1"})


def test_ingest_runs_and_analytics_work(user_client):
    repo = _ready_repo(user_client)
    assert repo["full_name"] == "pallets/flask"
    assert repo["commit_count"] == 3 and repo["pr_count"] == 1
    rid = repo["id"]

    overview = user_client.get(f"/api/repos/{rid}/overview").json()
    assert overview["commits"] == 3 and overview["authors"] == 2 and overview["prs"] == 1

    hot = user_client.get(f"/api/repos/{rid}/hotfiles").json()
    assert {h["file"] for h in hot[:2]} == {"src/sessions.py", "src/auth.py"}

    pairs = user_client.get(f"/api/repos/{rid}/cochange").json()
    assert {"file_a": "src/auth.py", "file_b": "src/sessions.py", "co_changes": 1} in pairs

    authors = user_client.get(f"/api/repos/{rid}/authors").json()
    assert authors[0]["author"] == "alice" and authors[0]["commits"] == 2

    pulls = user_client.get(f"/api/repos/{rid}/pulls").json()
    assert pulls == [{"number": 42, "title": "add oauth login feature", "author": "bob",
                      "merged_at": "2026-01-12T10:00:00", "labels": ["auth"],
                      "commit_sha": "b2c3d4e", "files": ["src/auth.py", "src/sessions.py"]}]

    commits = user_client.get(f"/api/repos/{rid}/commits").json()
    assert [c["type"] for c in commits] == ["refactor", "feat", "fix"]


def test_rejects_non_github_urls(user_client):
    for url in ("https://gitlab.com/a/b", "github.com/a", "file:///etc/passwd", "https://github.com/a/b/c"):
        assert user_client.post("/api/repos", json={"url": url}).status_code == 422, url


def test_ask_requires_model_then_uses_users_provider(user_client):
    rid = _ready_repo(user_client)["id"]
    assert user_client.post(f"/api/repos/{rid}/ask", json={"question": "why oauth?"}).status_code == 409

    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/ask", json={"question": "why was oauth login added?", "mode": "bullets"})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["answer"].startswith("Answer from claude-test-1")
    assert q["provider"] == "anthropic" and q["model"] == "claude-test-1"
    assert q["sources"] and q["sources"][0]["sha"]

    from tests.conftest import FakeProvider
    prompt = FakeProvider.calls[-1]["prompt"]
    assert "Adds OAuth so users can sign in." in prompt      # PR description reaches the LLM
    assert "concise bullet point list" in prompt

    history = user_client.get(f"/api/repos/{rid}/queries").json()
    assert [h["question"] for h in history] == ["why was oauth login added?"]
    assert user_client.delete(f"/api/repos/{rid}/queries").status_code == 204
    assert user_client.get(f"/api/repos/{rid}/queries").json() == []


def test_only_pr_filter(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    q = user_client.post(f"/api/repos/{rid}/ask", json={"question": "what changed in sessions?", "only_pr": True}).json()
    assert q["sources"] and all(s["has_pr"] for s in q["sources"])


def test_timeline(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/timeline", json={"path": "sessions.py"}).json()
    assert [e["sha"] for e in r["entries"]] == ["a1b2c3d", "b2c3d4e"]
    assert r["answer"].startswith("Answer from")
    empty = user_client.post(f"/api/repos/{rid}/timeline", json={"path": "nope.py"}).json()
    assert empty["entries"] == [] and empty["answer"] is None


def test_file_list_and_exact_or_folder_timeline(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    files = user_client.get(f"/api/repos/{rid}/files").json()
    assert files == [{"path": "src/auth.py", "changes": 2}, {"path": "src/sessions.py", "changes": 2},
                     {"path": "README.md", "changes": 1}]

    def shas(path, match):
        r = user_client.post(f"/api/repos/{rid}/timeline", json={"path": path, "match": match})
        assert r.status_code == 200, r.text
        return [e["sha"] for e in r.json()["entries"]]

    assert shas("src/sessions.py", "exact") == ["a1b2c3d", "b2c3d4e"]
    assert shas("sessions.py", "exact") == []          # a bare name is not the full path
    assert shas("src/", "folder") == ["a1b2c3d", "b2c3d4e", "c3d4e5f"]
    assert shas("sr", "folder") == []                  # folders match whole path segments
    bad = user_client.post(f"/api/repos/{rid}/timeline", json={"path": "src", "match": "fuzzy"})
    assert bad.status_code == 422


def test_repos_are_private_per_user(client):
    from tests.conftest import register
    register(client, email="owner@example.com")
    rid = _ready_repo(client)["id"]
    client.post("/api/auth/logout")
    register(client, email="intruder@example.com")
    assert client.get(f"/api/repos/{rid}").status_code == 404
    assert client.delete(f"/api/repos/{rid}").status_code == 404
    assert client.get("/api/repos").json() == []


def test_limits_on_repo_count_and_commits(user_client):
    assert user_client.post("/api/repos", json={"url": "https://github.com/a/b", "max_commits": 500}).status_code == 403
    _ready_repo(user_client)
    _ready_repo(user_client)
    r = user_client.post("/api/repos", json={"url": "https://github.com/a/c", "max_commits": 50})
    assert r.status_code == 403 and "up to 2" in r.json()["detail"]


def test_daily_limit_survives_deletion(user_client):
    for _ in range(3):
        rid = _ready_repo(user_client)["id"]
        user_client.delete(f"/api/repos/{rid}")
    r = user_client.post("/api/repos", json={"url": "https://github.com/a/b", "max_commits": 50})
    assert r.status_code == 429


def test_delete_removes_vectors(user_client):
    from storage.vector_store import VectorStore
    repo = _ready_repo(user_client)
    rid = repo["id"]
    from app.db import SessionLocal
    from app.models import Repo
    with SessionLocal() as db:
        ns = db.get(Repo, rid).namespace
    assert VectorStore(ns).search("oauth", top_k=3)
    assert user_client.delete(f"/api/repos/{rid}").status_code == 204
    assert VectorStore(ns).search("oauth", top_k=3) == []


def test_failed_clone_reports_friendly_error(user_client, monkeypatch):
    def boom(*a, **k):
        raise ingest.git.GitCommandError("clone", 128)
    monkeypatch.setattr(ingest.git.Repo, "clone_from", boom)
    r = user_client.post("/api/repos", json={"url": "https://github.com/no/such-repo", "max_commits": 50})
    repo = user_client.get(f"/api/repos/{r.json()['id']}").json()
    assert repo["status"] == "failed" and "public" in repo["error"]


def test_expired_repos_are_cleaned_up(user_client):
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models import Repo, utcnow
    rid = _ready_repo(user_client)["id"]
    with SessionLocal() as db:
        db.get(Repo, rid).expires_at = utcnow() - timedelta(minutes=1)
        db.commit()
    assert ingest.cleanup_expired() == 1
    assert user_client.get(f"/api/repos/{rid}").status_code == 404


def test_bug_origins_are_saved_with_a_summary(user_client):
    rid = _ready_repo(user_client)["id"]
    r = user_client.get(f"/api/repos/{rid}/origins").json()
    assert r["computed"] is True
    assert r["fixes"][0]["origins"][0]["sha"] == "9e8d7c6"
    assert r["summary"] == {"fixes": 1, "traced": 1, "older": 0, "nothing_to_trace": 0,
                            "median_days": 16, "repeat_origins": []}


def test_bug_origin_failure_does_not_fail_the_ingest(user_client, monkeypatch):
    def broken(path, commits):
        raise RuntimeError("blame failed")

    monkeypatch.setattr(ingest, "find_bug_origins", broken)
    rid = _ready_repo(user_client)["id"]
    assert user_client.get(f"/api/repos/{rid}/origins").json() == {"computed": False, "summary": None, "fixes": []}


def test_questions_are_grouped_into_chats(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)

    def ask(question, chat=None):
        r = user_client.post(f"/api/repos/{rid}/ask", json={"question": question, "conversation_id": chat})
        assert r.status_code == 200, r.text
        return r.json()["conversation_id"]

    first = ask("why was oauth login added?")
    assert ask("who reviewed it?", first) == first           # a follow-up stays in the same chat
    second = ask("what changed in sessions?")                # no id starts a new chat
    assert second != first

    chats = user_client.get(f"/api/repos/{rid}/chats").json()
    assert [(c["id"], c["title"], c["questions"]) for c in chats] == [
        (second, "what changed in sessions?", 1), (first, "why was oauth login added?", 2)]
    messages = user_client.get(f"/api/repos/{rid}/chats/{first}").json()
    assert [m["question"] for m in messages] == ["why was oauth login added?", "who reviewed it?"]


def test_chats_are_private_and_deletable(client):
    from tests.conftest import register
    register(client, email="owner@example.com")
    rid = _ready_repo(client)["id"]
    _connect_model(client)
    chat = client.post(f"/api/repos/{rid}/ask", json={"question": "why oauth?"}).json()["conversation_id"]

    client.post("/api/auth/logout")
    register(client, email="other@example.com")
    other = _ready_repo(client)["id"]
    _connect_model(client)
    # Someone else's chat can't be read or extended, even through their own repository
    assert client.get(f"/api/repos/{rid}/chats/{chat}").status_code == 404
    assert client.post(f"/api/repos/{other}/ask",
                       json={"question": "why oauth?", "conversation_id": chat}).status_code == 404

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"email": "owner@example.com", "password": "correct-horse-battery"})
    assert client.delete(f"/api/repos/{rid}/chats/{chat}").status_code == 204
    assert client.get(f"/api/repos/{rid}/chats").json() == []
    assert client.get(f"/api/repos/{rid}/queries").json() == []
    assert client.get(f"/api/repos/{rid}/chats/{chat}").status_code == 404


def test_a_failed_first_question_leaves_no_empty_chat(user_client, monkeypatch):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    from tests.conftest import FakeProvider
    from app.llm.base import ProviderError

    def failing(*a):
        raise ProviderError("rate_limit", "slow down")

    monkeypatch.setattr(FakeProvider, "generate", lambda self, *a: failing())
    assert user_client.post(f"/api/repos/{rid}/ask", json={"question": "why oauth?"}).status_code == 429
    assert user_client.get(f"/api/repos/{rid}/chats").json() == []


def test_follow_ups_are_rewritten_using_the_chat(user_client):
    from app.services import rag
    from tests.conftest import FakeProvider
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)

    first = user_client.post(f"/api/repos/{rid}/ask", json={"question": "why was oauth login added?"}).json()
    assert first["search_query"] is None and len(FakeProvider.calls) == 1   # a first question isn't rewritten

    FakeProvider.calls.clear()
    r = user_client.post(f"/api/repos/{rid}/ask",
                         json={"question": "who reviewed it?", "conversation_id": first["conversation_id"]}).json()
    assert r["search_query"] == "Standalone: who reviewed it?"
    rewrite, answer = FakeProvider.calls
    assert rewrite["system"] == rag.REWRITE_PROMPT and "Q: why was oauth login added?" in rewrite["prompt"]
    assert "CONVERSATION SO FAR" in answer["prompt"] and "Q: why was oauth login added?" in answer["prompt"]
    assert "QUESTION:\nwho reviewed it?" in answer["prompt"]
    assert "searched for: Standalone: who reviewed it?" in answer["prompt"]

    saved = user_client.get(f"/api/repos/{rid}/chats/{first['conversation_id']}").json()
    assert [m["search_query"] for m in saved] == [None, "Standalone: who reviewed it?"]


def test_follow_ups_see_only_the_last_three_exchanges(user_client):
    from tests.conftest import FakeProvider
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)
    chat = None
    for n in ("one", "two", "three", "four", "five"):
        chat = user_client.post(f"/api/repos/{rid}/ask",
                                json={"question": f"question {n}?", "conversation_id": chat}).json()["conversation_id"]
    prompt = FakeProvider.calls[-1]["prompt"]
    # Asking the fifth question: exchanges two to four are sent, the first one has dropped out
    assert "Q: question one?" not in prompt
    assert all(f"Q: question {n}?" in prompt for n in ("two", "three", "four"))


@pytest.mark.parametrize("reply, expected", [
    ('"Why was the retry in 3f9c2a1 reverted?"', "Why was the retry in 3f9c2a1 reverted?"),
    ("Standalone question: Who reviewed PR #42?\n\nIt was bob.", "Who reviewed PR #42?"),
    ("  \n  ", "who reviewed it?"),
])
def test_rewrites_are_cleaned_up(reply, expected):
    from app.services.rag import _clean_rewrite
    assert _clean_rewrite(reply, "who reviewed it?") == expected


def test_suspects_rank_commits_and_explain_with_the_users_model(user_client):
    from tests.conftest import FakeProvider
    rid = _ready_repo(user_client)["id"]
    report = {"description": "Login breaks with a KeyError in src/auth.py after the latest release"}

    # No model connected: the ranking still works, there's just no explanation
    r = user_client.post(f"/api/repos/{rid}/suspects", json=report)
    assert r.status_code == 200, r.text
    plain = r.json()
    assert plain["answer"] is None and plain["mentioned_files"] == ["src/auth.py"]
    assert {s["sha"] for s in plain["suspects"][:2]} == {"b2c3d4e", "c3d4e5f"}   # both changed src/auth.py
    assert all(any("src/auth.py" in why for why in s["reasons"]) for s in plain["suspects"][:2])

    _connect_model(user_client)
    explained = user_client.post(f"/api/repos/{rid}/suspects", json=report).json()
    assert explained["answer"].startswith("Answer from claude-test-1")
    assert explained["provider"] == "anthropic" and explained["model"] == "claude-test-1"
    prompt = FakeProvider.calls[-1]["prompt"]
    assert "BUG REPORT:\nLogin breaks with a KeyError" in prompt and "Suspect 1 · commit" in prompt


def test_suspects_validate_input_and_filter_by_date(user_client):
    rid = _ready_repo(user_client)["id"]
    assert user_client.post(f"/api/repos/{rid}/suspects", json={"description": "broken"}).status_code == 422
    late = user_client.post(f"/api/repos/{rid}/suspects",
                            json={"description": "Login breaks in src/auth.py", "since": "2026-01-20"}).json()
    assert [s["sha"] for s in late["suspects"]] == ["c3d4e5f"]          # the only commit after Jan 20



# ── Streaming answers ─────────────────────────────────────────────
def _events(response) -> list[tuple[str, dict]]:
    """Server-sent events as (name, data) pairs."""
    import json
    out = []
    for block in response.text.split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line)
        if "event" in lines:
            out.append((lines["event"], json.loads(lines["data"])))
    return out


def test_answers_stream_and_only_complete_answers_are_saved(user_client):
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)

    r = user_client.post(f"/api/repos/{rid}/ask/stream", json={"question": "why was oauth login added?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _events(r)
    names = [name for name, _ in events]
    assert names[0] == "sources" and names[-1] == "done" and set(names[1:-1]) == {"delta"}
    sources = events[0][1]
    assert sources["sources"] and sources["search_query"] is None   # a first question isn't rewritten
    text = "".join(data["text"] for name, data in events if name == "delta")
    assert text == "Answer from claude-test-1: see `abc1234`." and names.count("delta") == 3

    done = events[-1][1]
    assert done["answer"] == text and done["provider"] == "anthropic" and done["model"] == "claude-test-1"
    assert done["sources"] == sources["sources"]
    saved = user_client.get(f"/api/repos/{rid}/chats/{done['conversation_id']}").json()
    assert [m["id"] for m in saved] == [done["id"]] and saved[0]["answer"] == text

    # A follow-up in the same chat is rewritten before searching, like /ask
    follow = _events(user_client.post(f"/api/repos/{rid}/ask/stream", json={
        "question": "who reviewed it?", "conversation_id": done["conversation_id"]}))
    assert follow[0][1]["search_query"] == "Standalone: who reviewed it?"
    assert follow[-1][1]["conversation_id"] == done["conversation_id"]
    assert len(user_client.get(f"/api/repos/{rid}/chats").json()) == 1


def test_a_stream_that_fails_midway_reports_it_and_saves_nothing(user_client, monkeypatch):
    from app.llm import ProviderError
    from tests.conftest import FakeProvider
    rid = _ready_repo(user_client)["id"]
    _connect_model(user_client)

    def breaks(self, api_key, model, system, prompt):
        yield "The change was "
        raise ProviderError("rate_limit", "Rate limit reached, try again in a minute")
    monkeypatch.setattr(FakeProvider, "stream", breaks)

    events = _events(user_client.post(f"/api/repos/{rid}/ask/stream", json={"question": "why was oauth login added?"}))
    assert [name for name, _ in events] == ["sources", "delta", "error"]
    assert events[-1][1] == {"message": "Rate limit reached, try again in a minute"}
    assert user_client.get(f"/api/repos/{rid}/chats").json() == []


def test_stream_setup_problems_are_normal_errors(user_client):
    rid = _ready_repo(user_client)["id"]
    r = user_client.post(f"/api/repos/{rid}/ask/stream", json={"question": "why was oauth login added?"})
    assert r.status_code == 409 and "Connect a model provider" in r.json()["detail"]
    _connect_model(user_client)
    r = user_client.post(f"/api/repos/{rid}/ask/stream", json={"question": "why?!", "conversation_id": 999})
    assert r.status_code == 404
