# retrieval/suspects.py
"""Rank the commits most likely to have caused a bug someone describes.

Every signal is one a person can check:
  search   how well the commit's message, pull request and diff match the report (hybrid search)
  code     whether its diff changed code the report names, like `follow_redirects` or `URL.join`
  files    whether it touched files the report names, including paths in stack traces
  type     what kind of change it was: new and reworked code breaks more often than other changes
  caused   whether Bug origins already traced an earlier bug to it
  size     how big it was: large changes introduce more bugs (just-in-time defect prediction)
  recency  how recent it is, as a small nudge
Commits that only changed docs or tests are left out. evals/bug_reports.py measures the
ranking on real GitHub bug reports. The result is a list of suspects to check, never proof.
"""
import functools
import math
import re
from collections import Counter

from ingestion.bug_origins import is_docs_or_tests
from retrieval.analytics import commit_log

WEIGHTS = {"search": 0.35, "code": 0.10, "files": 0.20, "type": 0.08, "caused": 0.06, "size": 0.14, "recency": 0.07}
# New and reworked code is where bugs usually start
TYPE_RISK = {"feat": 1.0, "refactor": 1.0, "fix": 0.6, "other": 0.5, "chore": 0.2, "docs": 0.0, "test": 0.0}
TYPE_NOTE = {
    "feat": "A new feature, and new code is where bugs most often start",
    "refactor": "A refactor that changed how existing code works",
    "fix": "A bug fix, and fixes sometimes introduce new problems",
    "other": "A code change of unknown type",
    "chore": "A maintenance change, such as a dependency bump",
    "docs": "Described as a documentation change, so less likely",
    "test": "Described as a test change, so less likely",
}
MAX_MENTIONS = 20
BIG_CHANGE = 1000      # lines added and removed at which the size signal is full
LARGE_NOTE = 200       # from this size on, the reasons call it a large change
RECENT = 100           # the 100th newest commit keeps about a third of the recency signal

# Something that looks like a file: optional folders, a name, and an extension starting with a letter
_PATH = re.compile(r"[\w./\\-]*[\w-]\.[A-Za-z][A-Za-z0-9]{0,7}\b")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
# Links and web addresses: `github.com` looks like a dotted code name but isn't one
_WEB = re.compile(r"https?://\S+|\bwww\.\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|io|dev|edu|gov|html?)\b", re.I)
# Words that look like code in a report but say nothing about where the bug is
_NOT_CODE = frozenset("""self cls none true false def class import from return with for while the and this that not
are was were has have had but can will would should could when what which where who how why all any its into than
then them they you your our there here also only just like use used using get set new old one two out see may might
issue bug error example code file line test tests python version expected actual behavior behaviour result following
work works working problem please thanks thank does doesn want below above""".split())


def mentioned_files(text: str) -> list[str]:
    """File names and paths in a bug report, such as `src/app.py` or a stack trace's `File "/x/y.py"`."""
    found: list[str] = []
    for raw in _PATH.findall(text):
        path = raw.replace("\\", "/").strip("/")
        while path.startswith("./"):
            path = path[2:]
        if "/" not in path and len(path.rsplit(".", 1)[0]) < 2:
            continue  # "e.g", "i.e": abbreviations, not files
        if path and path not in found:
            found.append(path)
    return found[:MAX_MENTIONS]


def _matches(path: str, mention: str) -> bool:
    """Same file if the last folders line up: `click/core.py` matches `/site-packages/click/core.py`."""
    a, b = path.lower().split("/"), mention.lower().split("/")
    same = 0
    while same < min(len(a), len(b)) and a[-1 - same] == b[-1 - same]:
        same += 1
    return same >= min(2, len(a), len(b))


def code_names(text: str) -> dict[str, str]:
    """Names in a report that look like code, lowercased, mapped to how the report wrote them:
    snake_case, CamelCase, dotted names like `client.get`, calls like `send()`, and anything in backticks."""
    found: dict[str, str] = {}
    text = _WEB.sub(" ", text)

    def add(name: str):
        key = name.lower()
        if len(key) > 2 and key not in _NOT_CODE and not key.isdigit():
            found.setdefault(key, name)

    for quoted in re.findall(r"`([^`\n]{1,80})`", text):
        for name in _NAME.findall(quoted):
            add(name)
    for name in _NAME.findall(text):
        if "_" in name.strip("_") or re.search(r"[a-z][A-Z]", name) or re.search(r"[A-Z]{2,}[a-z]", name):
            add(name)
    for pair in re.findall(r"\b([A-Za-z_]\w*)\.([A-Za-z_]\w*)", text):
        for name in pair:
            add(name)
    for name in re.findall(r"\b([A-Za-z_]\w{2,})\(", text):
        add(name)
    return found


@functools.lru_cache(maxsize=2048)
def _diff_names(text: str) -> frozenset[str]:
    """Names on the lines a commit added or removed, plus the functions its hunks sat in."""
    if "DIFF:" not in text:
        return frozenset()
    names = set()
    for line in text.split("DIFF:", 1)[1].split("\n"):
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            names.update(n.lower() for n in _NAME.findall(line))
        elif line.startswith("@@"):
            names.update(n.lower() for n in _NAME.findall(line.split("@@")[-1]))
    return frozenset(names)


def origin_counts(origins: list[dict] | None) -> Counter:
    """How many bug fixes Bug origins traced to each commit."""
    return Counter(sha for fix in origins or [] for sha in {o["sha"] for o in fix.get("origins", [])})


def rank_suspects(description: str, chunks: list[dict], search_scores: dict[str, float],
                  caused: Counter | dict, since: str | None = None, top_n: int = 3,
                  weights: dict | None = None) -> tuple[list[dict], list[str]]:
    """The top suspects with their reasons, and the report's file names that exist in the history."""
    w = weights or WEIGHTS   # the evals compare other weightings
    log = commit_log(chunks)  # newest first
    known = {f for row in log for f in row["files"]}
    # Only names of files this repository has had; URLs and `module.attr` look like files but aren't
    mentions = [m for m in mentioned_files(description) if any(_matches(f, m) for f in known)]
    # A commit that only touched docs or tests didn't change behaviour, so it can't have broken it
    rows = [row for row in log if any(not is_docs_or_tests(f) for f in row["files"])]

    texts = {c["metadata"]["sha"]: c["text"] for c in chunks}
    names = {row["sha"]: _diff_names(texts.get(row["sha"], "")) for row in rows}
    seen = Counter(n for found in names.values() for n in found)
    rarity = {n: math.log((len(rows) + 1) / (k + 0.5)) for n, k in seen.items()}   # rare names say more
    wanted = {k: v for k, v in code_names(description).items() if k in rarity}
    wanted_total = sum(rarity[k] for k in wanted) or 1.0

    best = max(search_scores.values(), default=0) or 1
    ranked = []
    for position, row in enumerate(rows):
        if since and row["timestamp"][:10] < since:
            continue
        s_search = max(0.0, search_scores.get(row["sha"], 0.0)) / best
        named = [m for m in mentions if any(_matches(f, m) for f in row["files"])]
        s_files = len(named) / len(mentions) if mentions else 0.0
        changed = sorted((k for k in wanted if k in names[row["sha"]]), key=lambda k: -rarity[k])
        s_code = sum(rarity[k] for k in changed) / wanted_total
        if not (s_search or s_files or s_code):
            continue  # unrelated to the report
        bugs = caused.get(row["sha"], 0)
        lines = row["insertions"] + row["deletions"]
        parts = {"search": s_search, "code": s_code, "files": s_files,
                 "type": TYPE_RISK.get(row["type"], 0.5), "caused": 1.0 if bugs else 0.0,
                 "size": min(1.0, math.log1p(lines) / math.log1p(BIG_CHANGE)),
                 "recency": math.exp(-position / RECENT)}
        score = sum(w.get(k, 0.0) * v for k, v in parts.items())

        reasons = []
        if s_search >= 0.8:
            reasons.append("Closely matches your description")
        elif s_search > 0:
            reasons.append("Partly matches your description")
        if changed:
            reasons.append(f"Changed code your report mentions: {', '.join(wanted[k] for k in changed[:3])}")
        if named:
            touched = [f for f in row["files"] if any(_matches(f, m) for m in named)]
            reasons.append(f"Changed {', '.join(touched[:3])}, which your report names")
        if bugs:
            reasons.append(f"Already traced as the cause of {bugs} earlier bug {'fix' if bugs == 1 else 'fixes'}")
        if lines >= LARGE_NOTE:
            reasons.append(f"A large change ({lines:,} lines), and large changes introduce more bugs")
        reasons.append(TYPE_NOTE.get(row["type"], TYPE_NOTE["other"]))

        ranked.append({**row, "score": round(score, 3), "reasons": reasons,
                       "scores": {k: round(v, 3) for k, v in parts.items()}})
    # Ties go to the newer commit: a bug usually appears soon after the change that caused it
    ranked.sort(key=lambda s: (s["score"], s["timestamp"]), reverse=True)
    return ranked[:top_n], mentions
