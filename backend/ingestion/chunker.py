# ingestion/chunker.py

def build_chunks(commits, pull_requests) -> list[dict]:
    # Primary match: merge_commit_sha → PR
    sha_to_pr = {
        pr.merge_commit_sha: pr
        for pr in pull_requests
        if pr.merge_commit_sha
    }

    # Fallback match: PR title keywords → commit message
    # Handles squash-merge where SHA doesn't match
    def find_pr_by_message(commit_msg: str, commit_sha: str):
        msg_lower = commit_msg.lower().strip()
        best_match = None
        best_score = 0
        for pr in pull_requests:
            if pr.merge_commit_sha == commit_sha:
                continue
            score = 0

            # Title word matching — require at least 2 significant words
            pr_title_lower = pr.title.lower().strip()
            pr_words = [w for w in pr_title_lower.split() if len(w) > 3]
            if len(pr_words) >= 2:
                matches = sum(1 for w in pr_words if w in msg_lower)
                if matches >= 2:
                    score = matches

            # Merge commit patterns like "Merge pull request #N" or "(#123)"
            if f"#{pr.number}" in commit_msg:
                score = max(score, 10)
            if f"(#{pr.number})" in commit_msg:
                score = max(score, 10)

            # Author name match as tiebreaker
            if pr.author and pr.author.lower() in msg_lower:
                score = max(score, 1)

            if score > best_score:
                best_score = score
                best_match = pr

        return best_match if best_score >= 2 else None

    chunks = []
    for commit in commits:
        # Try SHA match first, then fuzzy title match
        pr = sha_to_pr.get(commit.sha) or find_pr_by_message(commit.message, commit.sha)
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

    matched = sum(1 for c in chunks if c["metadata"]["has_pr"])
    print(f"Built {len(chunks)} chunks — {matched} linked to PRs")
    return chunks


def _build_text(commit, pr=None) -> str:
    msg   = commit.message.strip()
    label = _classify(msg)

    parts = [
        f"COMMIT [{label}]: {msg}",
        f"AUTHOR: {commit.author}",
        f"DATE: {commit.timestamp[:10]}",
        f"FILES CHANGED: {', '.join(commit.files_changed[:15])}",
        f"LINES: +{commit.insertions} / -{commit.deletions}",
    ]

    if pr:
        parts.append(f"PR #{pr.number} by {pr.author}: {pr.title}")
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