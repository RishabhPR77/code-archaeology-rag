import pytest

from evals.cases import first_sentence, rank_of, retrieval_cases, scores, suspect_cases


def test_first_sentence_skips_templates_and_issue_references():
    body = ("<!-- Describe your change -->\n## Summary\n- [x] Tests added\nFixes #412.\n"
            "Sessions could expire halfway through payment and the retry charged twice. More detail follows here.")
    assert first_sentence(body) == "Sessions could expire halfway through payment and the retry charged twice."
    assert first_sentence("Fixes #12.") is None
    assert first_sentence("See [the docs](https://x.io) for the `retry` option in every single client.") == \
        "See the docs for the retry option in every single client."


def _chunk(sha, pr_text=""):
    text = f"COMMIT [FEATURE]: retry payments when the token expires (#7)\n\nAUTHOR: alice{pr_text}\n\nDIFF:\n+ retry()"
    return {"text": text, "metadata": {"sha": sha, "has_pr": bool(pr_text)}}


def test_pr_text_becomes_the_question_and_leaves_the_index():
    pr = ("\n\nPR #7 by bob: Retry payments when the token expires"
          "\n\nPR DESCRIPTION: Tokens can expire mid-payment, so we now refresh and retry the charge once."
          "\n\nPR LABELS: bug")
    indexed, titles, descriptions = retrieval_cases([_chunk("aaaaaaa", pr), _chunk("bbbbbbb", pr), _chunk("ccccccc")])
    assert titles == [{"question": "Retry payments when the token expires", "answers": {"aaaaaaa", "bbbbbbb"}}]
    assert descriptions[0]["question"].startswith("Tokens can expire mid-payment")
    assert all("PR #7" not in c["text"] and "PR DESCRIPTION" not in c["text"] for c in indexed)
    assert "PR LABELS: bug" in indexed[0]["text"] and "DIFF:" in indexed[0]["text"]
    # The title is also cut from the commit message that repeats it, but only where a PR is linked
    assert indexed[0]["text"].startswith("COMMIT [FEATURE]:  (#7)")
    assert "retry payments when the token expires" in indexed[2]["text"]


def test_suspect_cases_use_only_earlier_fixes():
    origin = lambda sha, ingested=True: [{"sha": sha, "ingested": ingested}]
    fixes = [
        {"message": "fix crash", "timestamp": "2026-03-01T00:00:00", "status": "traced", "origins": origin("o1")},
        {"message": "fix leak", "timestamp": "2026-02-01T00:00:00", "status": "traced", "origins": origin("o2")},
        {"message": "fix old", "timestamp": "2026-01-01T00:00:00", "status": "traced", "origins": origin("o3", False)},
        {"message": "fix docs", "timestamp": "2026-01-15T00:00:00", "status": "nothing_to_trace", "origins": []},
    ]
    cases = suspect_cases(fixes)
    assert [c["answer"] for c in cases] == ["o1", "o2"]                  # o3 is outside the ingested commits
    assert [f["message"] for f in cases[1]["earlier_fixes"]] == ["fix old", "fix docs"]


def test_scores():
    assert rank_of({"b"}, ["a", "b", "c"]) == 2 and rank_of({"z"}, ["a"]) is None
    assert scores([1, 2, None, 5], ks=(1, 3)) == {"@1": 0.25, "@3": 0.5, "mrr": pytest.approx((1 + 0.5 + 0 + 0.2) / 4)}
    assert scores([], ks=(1,)) == {"@1": None, "mrr": None}
