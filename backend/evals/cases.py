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
    def as_cases(d: dict) -> list[dict]:
        return [{"question": q, "answers": shas} for q, shas in d.items()]
    return indexed, as_cases(titles), as_cases(descriptions)


_CLOSING = re.compile(
    r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\b:?\s+"
    r"(?:(?P<repo>[\w.-]+/[\w.-]+)?#(?P<num>\d+)|https://github\.com/(?P<urlrepo>[\w.-]+/[\w.-]+)/issues/(?P<urlnum>\d+))",
    re.IGNORECASE)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


def closing_issues(text: str, repo: str) -> list[int]:
    """Issue numbers a PR or commit says it closes, using GitHub's closing keywords ("Fixes #12",
    "closes owner/repo#12", or a link to the issue). References to other repositories are ignored."""
    found = []
    for m in _CLOSING.finditer(text or ""):
        other = m["repo"] or m["urlrepo"]
        if other and other.lower() != repo.lower():
            continue
        n = int(m["num"] or m["urlnum"])
        if n not in found:
            found.append(n)
    return found


def issue_report(issue: dict, max_chars: int = 4000) -> str:
    """A GitHub issue as a user would paste it into Who broke it?: title, then the description with
    template comments removed. Code blocks stay, since stack traces in them name files."""
    body = _HTML_COMMENT.sub("", issue.get("body") or "").strip()
    return f"{issue['title'].strip()}\n\n{body}".strip()[:max_chars]


def is_bug_report(labels: list[str], fix_message: str, report: str) -> bool:
    """Many issues a pull request closes are feature requests or questions, where "who broke it" has no
    answer. An issue counts as a bug report if it's labelled as one, the commit that closed it is a fix
    by the app's own classifier, or the report has a Python traceback."""
    from retrieval.analytics import commit_type
    return (any("bug" in label.lower() for label in labels) or commit_type(fix_message) == "fix"
            or "traceback (most recent call last)" in report.lower())


def suspect_cases(fixes: list[dict]) -> list[dict]:
    """Traced fixes whose cause is one of the ingested commits."""
    cases = []
    for fix in fixes:
        if fix["status"] != "traced" or not fix["origins"][0]["ingested"]:
            continue
        cases.append({
            "fix": fix.get("sha"),
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
