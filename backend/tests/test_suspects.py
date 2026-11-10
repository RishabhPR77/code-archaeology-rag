import pytest

from retrieval.suspects import _matches, code_names, mentioned_files, origin_counts, rank_suspects


def _chunk(sha, message, files, ts, author="alice", diff="", lines=2):
    text = f"COMMIT [OTHER]: {message}\n\nAUTHOR: {author}" + (f"\n\nDIFF:\n{diff}" if diff else "")
    return {"id": sha * 6, "text": text,
            "metadata": {"sha": sha, "author": author, "timestamp": ts, "files": ", ".join(files),
                         "insertions": lines // 2, "deletions": lines - lines // 2, "has_pr": False, "pr_number": 0}}


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
    # The commit that changed the named file wins even though another matched the words better.
    # The docs-only commit matched too, but changing docs can't break behaviour.
    assert [s["sha"] for s in suspects] == ["aaaaaaa", "bbbbbbb"]
    top = suspects[0]
    assert top["scores"]["search"] == 0.625 and top["scores"]["files"] == 1.0 and top["scores"]["recency"] == 1.0
    assert "Changed src/checkout/session.py, which your report names" in top["reasons"]


def test_only_real_files_count_as_named():
    report = "Broken since 2.0, see github.com/acme/shop and payment.retry() in src/checkout/session.py"
    _, mentions = rank_suspects(report, CHUNKS, {"aaaaaaa": 0.5}, caused={})
    assert mentions == ["src/checkout/session.py"]     # not the URL or the call, which only look like files


def test_code_names_in_reports():
    names = code_names("`Client.send()` fails when follow_redirects is set on AsyncClient; see e.g. the docs")
    assert {"client", "send", "follow_redirects", "asyncclient"} <= set(names)
    assert names["asyncclient"] == "AsyncClient" and "the" not in names and "docs" not in names
    # Links aren't code, even though github.com looks like a dotted name
    assert set(code_names("See https://github.com/acme/shop/issues/1 or github.com and run_job()")) == {"run_job"}


def test_changing_code_the_report_names_and_size_raise_a_commit():
    chunks = [
        _chunk("aaaaaaa", "tidy imports", ["src/net/client.py"], "2026-03-01T10:00:00",
               diff="@@ -1,3 +1,3 @@ class Client:\n-import os\n+import sys"),
        _chunk("bbbbbbb", "rework redirects", ["src/net/client.py"], "2026-02-01T10:00:00", lines=900,
               diff="@@ -40,6 +40,9 @@ def send(self, request):\n-    if follow_redirects:\n+    if self.follow_redirects:"),
    ]
    report = "Redirects are ignored: `follow_redirects=True` has no effect since the last release"
    suspects, _ = rank_suspects(report, chunks, {"aaaaaaa": 0.5, "bbbbbbb": 0.5}, caused={})
    assert [s["sha"] for s in suspects] == ["bbbbbbb", "aaaaaaa"]
    assert "Changed code your report mentions: follow_redirects" in suspects[0]["reasons"]
    assert "A large change (900 lines), and large changes introduce more bugs" in suspects[0]["reasons"]
    assert suspects[0]["scores"]["size"] > suspects[1]["scores"]["size"]


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
