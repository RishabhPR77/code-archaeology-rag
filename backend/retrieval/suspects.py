# retrieval/suspects.py
"""Rank the commits most likely to have caused a bug someone describes.

Three signals, all explainable: how well a commit matches the report (hybrid search),
whether it touched files the report names (including paths in stack traces), and a risk
prior (what kind of change it was, and whether Bug origins already traced earlier bugs
to it). The result is a list of suspects to check, never proof.
"""
import re
from collections import Counter

from retrieval.analytics import commit_log

WEIGHTS = {"search": 0.5, "files": 0.3, "risk": 0.2}
# New and reworked code is where bugs usually start; docs and tests rarely break behaviour
TYPE_RISK = {"feat": 1.0, "refactor": 1.0, "fix": 0.6, "other": 0.5, "chore": 0.2, "docs": 0.0, "test": 0.0}
TYPE_NOTE = {
    "feat": "A new feature, and new code is where bugs most often start",
    "refactor": "A refactor that changed how existing code works",
    "fix": "A bug fix, and fixes sometimes introduce new problems",
    "other": "A code change of unknown type",
    "chore": "A maintenance change, such as a dependency bump",
    "docs": "Only documentation, so less likely",
    "test": "Only tests, so less likely",
}
MAX_MENTIONS = 20

# Something that looks like a file: optional folders, a name, and an extension starting with a letter
_PATH = re.compile(r"[\w./\\-]*[\w-]\.[A-Za-z][A-Za-z0-9]{0,7}\b")


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


def origin_counts(origins: list[dict] | None) -> Counter:
    """How many bug fixes Bug origins traced to each commit."""
    return Counter(sha for fix in origins or [] for sha in {o["sha"] for o in fix.get("origins", [])})


def rank_suspects(description: str, chunks: list[dict], search_scores: dict[str, float],
                  caused: Counter | dict, since: str | None = None, top_n: int = 3,
                  weights: dict | None = None) -> tuple[list[dict], list[str]]:
    w = weights or WEIGHTS   # evals/run_eval.py compares other weightings
    mentions = mentioned_files(description)
    best = max(search_scores.values(), default=0) or 1
    ranked = []
    for row in commit_log(chunks):
        if since and row["timestamp"][:10] < since:
            continue
        s_search = max(0.0, search_scores.get(row["sha"], 0.0)) / best
        named = [m for m in mentions if any(_matches(f, m) for f in row["files"])]
        s_files = len(named) / len(mentions) if mentions else 0.0
        if not s_search and not s_files:
            continue  # unrelated to the report
        bugs = caused.get(row["sha"], 0)
        s_risk = 0.6 * TYPE_RISK.get(row["type"], 0.5) + 0.4 * (1.0 if bugs else 0.0)
        score = w["search"] * s_search + w["files"] * s_files + w["risk"] * s_risk

        reasons = []
        if s_search >= 0.8:
            reasons.append("Closely matches your description")
        elif s_search > 0:
            reasons.append("Partly matches your description")
        if named:
            touched = [f for f in row["files"] if any(_matches(f, m) for m in named)]
            reasons.append(f"Changed {', '.join(touched[:3])}, which your report names")
        if bugs:
            reasons.append(f"Already traced as the cause of {bugs} earlier bug {'fix' if bugs == 1 else 'fixes'}")
        reasons.append(TYPE_NOTE.get(row["type"], TYPE_NOTE["other"]))

        ranked.append({**row, "score": round(score, 3), "reasons": reasons,
                       "scores": {"search": round(s_search, 3), "files": round(s_files, 3), "risk": round(s_risk, 3)}})
    # Ties go to the newer commit: a bug usually appears soon after the change that caused it
    ranked.sort(key=lambda s: (s["score"], s["timestamp"]), reverse=True)
    return ranked[:top_n], mentions
