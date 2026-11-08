# evals/cases.py
"""Build accuracy-check cases from a repository's own history, so nobody has to label data by hand.

Search: a pull request's title, or the first real sentence of its description, is the question, and the
commit it belongs to is the answer. That PR text is removed from what gets indexed (the title also from the
commit message, which often repeats it), so the answer can't simply match itself.

Who broke it?: every bug fix that Bug origins traced is a report (its commit message), and the traced
cause is the answer. Only commits and fixes from before the fix are visible, so nothing leaks from later.
"""
import re
from statistics import mean

PR_LINE = re.compile(r"^PR #\d+ by [^\n]*?: (?P<title>[^\n]+)$", re.MULTILINE)
PR_DESCRIPTION = re.compile(
    r"PR DESCRIPTION: (?P<body>.*?)(?=\n\n(?:PR LABELS:|REVIEW COMMENTS:|REVIEW SUMMARY:|DIFF:)|\Z)", re.DOTALL)

_BLOCKS = re.compile(r"<!--.*?-->|```.*?```", re.DOTALL)                    # HTML comments, code blocks
_NOISE_LINE = re.compile(r"^\s*(?:#|>|\||[-*]\s*\[[ xX]\]).*$", re.MULTILINE)  # headings, quotes, tables, checklists
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_ISSUE_ONLY = re.compile(r"^(?:fix(?:es|ed)?|close[sd]?|resolve[sd]?|see|ref)?\s*#\d+\.?$", re.IGNORECASE)


def first_sentence(body: str, min_words: int = 6, max_words: int = 40) -> str | None:
    """The first sentence of a PR description that reads like a question someone might ask."""
    text = _NOISE_LINE.sub(" ", _BLOCKS.sub(" ", body))
    text = " ".join(_LINK.sub(r"\1", text).replace("`", "").split())
    for sentence in _SENTENCE_END.split(text):
        words = sentence.split()
        if min_words <= len(words) <= max_words and not _ISSUE_ONLY.match(sentence):
            return sentence
    return None


def retrieval_cases(chunks: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(chunks to index without their PR title and description, title questions, description questions)."""
    indexed, titles, descriptions = [], {}, {}
    for chunk in chunks:
        text, sha = chunk["text"], chunk["metadata"]["sha"]
        if chunk["metadata"].get("has_pr"):
            title = (m := PR_LINE.search(text)) and m["title"].strip()
            if title:
                titles.setdefault(title, set()).add(sha)
            if (d := PR_DESCRIPTION.search(text)) and (sentence := first_sentence(d["body"])):
                descriptions.setdefault(sentence, set()).add(sha)
            text = PR_DESCRIPTION.sub("", PR_LINE.sub("", text))
            if title:
                # Commit messages often repeat the PR title word for word, which would make it a giveaway
                text = re.sub(re.escape(title), "", text, flags=re.IGNORECASE)
        indexed.append({**chunk, "text": text})
    # One PR can be linked to several commits; finding any of them counts
    as_cases = lambda d: [{"question": q, "answers": shas} for q, shas in d.items()]
    return indexed, as_cases(titles), as_cases(descriptions)


def suspect_cases(fixes: list[dict]) -> list[dict]:
    """Traced fixes whose cause is one of the ingested commits."""
    cases = []
    for fix in fixes:
        if fix["status"] != "traced" or not fix["origins"][0]["ingested"]:
            continue
        cases.append({
            "report": fix["message"],
            "before": fix["timestamp"],
            "answer": fix["origins"][0]["sha"],
            # Bug origins' boost may only use what was known before this fix
            "earlier_fixes": [f for f in fixes if f["timestamp"] < fix["timestamp"]],
        })
    return cases


def rank_of(answers: set[str], ranked: list[str]) -> int | None:
    return next((i for i, sha in enumerate(ranked, 1) if sha in answers), None)


def scores(ranks: list[int | None], ks: tuple[int, ...]) -> dict:
    """recall@k (share of cases with the answer in the top k) and mean reciprocal rank."""
    if not ranks:
        return {**{f"@{k}": None for k in ks}, "mrr": None}
    return {**{f"@{k}": sum(1 for r in ranks if r and r <= k) / len(ranks) for k in ks},
            "mrr": mean(1 / r if r else 0 for r in ranks)}
