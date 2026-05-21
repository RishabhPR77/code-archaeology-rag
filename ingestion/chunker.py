from dataclasses import asdict

def build_chunks(commits, pull_requests) -> list[dict]:
    sha_to_pr = {
        pr.merge_commit_sha: pr
        for pr in pull_requests
        if pr.merge_commit_sha
    }

    chunks = []
    for commit in commits:
        pr   = sha_to_pr.get(commit.sha)
        text = _build_text(commit, pr)

        chunks.append({
            "id":   commit.sha,
            "text": text,
            "metadata": {
                "sha":        commit.sha[:7],
                "author":     commit.author,
                "email":      commit.email,
                "timestamp":  commit.timestamp,
                "files":      ", ".join(commit.files_changed[:10]),
                "insertions": commit.insertions,
                "deletions":  commit.deletions,
                "has_pr":     pr is not None,
                "pr_number":  pr.number if pr else 0,
                "pr_labels":  ", ".join(pr.labels) if pr else "",
            }
        })

    print(f"Built {len(chunks)} chunks")
    return chunks


def _build_text(commit, pr=None) -> str:
    """
    Richer text per commit for better embedding + BM25 retrieval.
    Structure: intent summary first (most important for semantic search),
    then supporting context (files, diff, PR).
    """
    # Classify intent from message keywords for extra signal
    msg   = commit.message.strip()
    label = _classify(msg)

    parts = [
        f"COMMIT [{label}]: {msg}",
        f"AUTHOR: {commit.author}",
        f"DATE: {commit.timestamp[:10]}",
        f"FILES CHANGED: {', '.join(commit.files_changed[:15])}",
        f"LINES: +{commit.insertions} / -{commit.deletions}",
    ]

    # PR context is gold for intent - add it before diff
    if pr:
        parts.append(f"PR #{pr.number}: {pr.title}")
        if pr.body and pr.body.strip():
            parts.append(f"PR DESCRIPTION: {pr.body[:1200]}")
        if pr.labels:
            parts.append(f"PR LABELS: {', '.join(pr.labels)}")
        if pr.review_comments:
            parts.append("REVIEW COMMENTS:\n" + "\n".join(
                f"  - {c[:200]}" for c in pr.review_comments[:5]
            ))
        if pr.review_summaries:
            parts.append("REVIEW SUMMARY:\n" + "\n".join(
                f"  - {s[:300]}" for s in pr.review_summaries[:3]
            ))

    # Diff last - noisy but useful for keyword/BM25 matches
    if commit.diff:
        parts.append(f"DIFF:\n{commit.diff[:3000]}")

    return "\n\n".join(parts)


def _classify(message: str) -> str:
    m = message.lower()
    if any(w in m for w in ["fix", "bug", "patch", "hotfix", "error", "issue", "crash"]):
        return "BUG FIX"
    if any(w in m for w in ["feat", "feature", "add", "new", "implement", "create", "introduce"]):
        return "FEATURE"
    if any(w in m for w in ["refactor", "clean", "restructure", "reorganize", "simplify", "extract"]):
        return "REFACTOR"
    if any(w in m for w in ["doc", "readme", "comment", "docs", "docstring"]):
        return "DOCS"
    if any(w in m for w in ["test", "spec", "coverage"]):
        return "TEST"
    if any(w in m for w in ["perf", "optim", "speed", "faster", "cache", "memory"]):
        return "PERF"
    if any(w in m for w in ["chore", "bump", "upgrade", "deps", "dependency", "version", "release", "merge"]):
        return "CHORE"
    return "OTHER"