import pytest

from retrieval.suspects import _matches, mentioned_files, origin_counts, rank_suspects


def _chunk(sha, message, files, ts, author="alice"):
    return {"id": sha * 6, "text": f"COMMIT [OTHER]: {message}\n\nAUTHOR: {author}",
            "metadata": {"sha": sha, "author": author, "timestamp": ts, "files": ", ".join(files),
                         "insertions": 1, "deletions": 1, "has_pr": False, "pr_number": 0}}


CHUNKS = [
    _chunk("aaaaaaa", "add retry to checkout", ["src/checkout/session.py", "src/payments/retry.py"], "2026-03-01T10:00:00"),
    _chunk("bbbbbbb", "refactor payment client", ["src/payments/client.py"], "2026-02-01T10:00:00"),
    _chunk("ccccccc", "docs: explain retries", ["docs/retries.md"], "2026-03-05T10:00:00"),
    _chunk("ddddddd", "bump dependencies", ["requirements.txt"], "2026-01-01T10:00:00"),
]


def test_file_mentions_come_from_plain_text_and_stack_traces():
    report = ('Checkout charges twice. Traceback (most recent call last):\n'
              '  File "/srv/app/src/checkout/session.py", line 42, in pay\n'
              '    at retry (web\\payments\\retry.ts:10:5)\nSee also session.py and version 1.2.3, e.g. this.')
    assert mentioned_files(report) == ["srv/app/src/checkout/session.py", "web/payments/retry.ts", "session.py"]


@pytest.mark.parametrize("path, mention, same", [
    ("src/checkout/session.py", "srv/app/src/checkout/session.py", True),
    ("src/checkout/session.py", "session.py", True),
    ("src/checkout/session.py", "other/session.py", False),     # same name, different folder
    ("session.py", "src/checkout/session.py", True),
    ("src/payments/retry.py", "web/payments/retry.ts", False),
])
def test_paths_match_on_their_last_folders(path, mention, same):
    assert _matches(path, mention) is same


def test_ranking_combines_search_named_files_and_risk():
    report = "Payments are charged twice after a retry in src/checkout/session.py"
    search = {"aaaaaaa": 0.5, "bbbbbbb": 0.8, "ccccccc": 0.7}
    suspects, mentions = rank_suspects(report, CHUNKS, search, caused={})
    assert mentions == ["src/checkout/session.py"]
    # The commit that changed the named file wins even though another matched the words better
    assert [s["sha"] for s in suspects] == ["aaaaaaa", "bbbbbbb", "ccccccc"]
    top = suspects[0]
    assert top["scores"] == {"search": 0.625, "files": 1.0, "risk": 0.6}
    assert "Changed src/checkout/session.py, which your report names" in top["reasons"]
    assert suspects[2]["reasons"][-1] == "Only documentation, so less likely"


def test_unrelated_commits_are_left_out_and_since_filters_by_date():
    suspects, _ = rank_suspects("payment retry fails", CHUNKS, {"aaaaaaa": 0.4}, caused={})
    assert [s["sha"] for s in suspects] == ["aaaaaaa"]          # no match, no file: not a suspect
    later, _ = rank_suspects("payment retry fails", CHUNKS, {"aaaaaaa": 0.4, "bbbbbbb": 0.4}, caused={},
                             since="2026-02-15")
    assert [s["sha"] for s in later] == ["aaaaaaa"]


def test_commits_behind_earlier_bugs_rank_higher():
    search = {"aaaaaaa": 0.5, "bbbbbbb": 0.5}
    caused = origin_counts([{"origins": [{"sha": "bbbbbbb"}, {"sha": "zzzzzzz"}]},
                            {"origins": [{"sha": "bbbbbbb"}]}])
    assert caused == {"bbbbbbb": 2, "zzzzzzz": 1}
    suspects, _ = rank_suspects("payments break", CHUNKS, search, caused)
    assert suspects[0]["sha"] == "bbbbbbb"
    assert "Already traced as the cause of 2 earlier bug fixes" in suspects[0]["reasons"]
