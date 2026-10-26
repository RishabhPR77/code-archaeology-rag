import re, time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from github import Auth, Github, RateLimitExceededException

# Stop scanning once this many merged PRs in a row predate the commit window
_OUT_OF_WINDOW_STREAK = 50

@dataclass
class PRRecord:
    number: int
    title: str
    body: str
    author: str
    merge_commit_sha: str
    merged_at: str
    labels: list
    linked_issues: list
    review_comments: list
    review_summaries: list
    discussion: list

@dataclass
class FetchResult:
    prs: list[PRRecord]
    warnings: list[str]

def _check_rate(g) -> int:
    """Return remaining API calls. Returns -1 if uncheckable."""
    try:
        return g.get_rate_limit().resources.core.remaining
    except Exception:
        try:
            return g.get_rate_limit().core.remaining
        except Exception:
            return -1

def fetch_prs(repo_name: str, max_prs: int = 200, token: str | None = None,
              since: datetime | None = None) -> FetchResult:
    """Fetch merged PRs. `since` skips PRs merged before the oldest ingested commit."""
    g = Github(auth=Auth.Token(token)) if token else Github()
    repo = g.get_repo(repo_name)
    records = []
    warnings = []
    if since is not None and since.tzinfo is None:
        since = since.replace(tzinfo=timezone.utc)
    cutoff = since - timedelta(days=1) if since else None

    remaining = _check_rate(g)
    if remaining != -1 and remaining < 20:
        warnings.append(f"GitHub's API limit is nearly used up ({remaining} requests left), so pull requests "
                        "were skipped. Re-sync later to add them.")
        return FetchResult(prs=records, warnings=warnings)

    try:
        pulls = repo.get_pulls(state="closed", sort="created", direction="desc")
    except RateLimitExceededException:
        warnings.append("GitHub rate limit hit while opening PR list.")
        return FetchResult(prs=records, warnings=warnings)

    old_streak = 0
    for pr in pulls:
        if len(records) >= max_prs:
            break
        if not pr.merged_at:
            continue
        # Older PRs can't match any ingested commit, so skip their detail calls
        if cutoff and pr.merged_at < cutoff:
            old_streak += 1
            if old_streak >= _OUT_OF_WINDOW_STREAK:
                break
            continue
        old_streak = 0

        try:
            # Only fetch heavy review/discussion data if rate limit allows
            remaining = _check_rate(g)
            fetch_details = remaining == -1 or remaining > 1000

            review_comments = []
            review_summaries = []
            discussion = []

            if fetch_details:
                try:
                    review_comments = [c.body for c in pr.get_review_comments() if c.body.strip()][:10]
                except RateLimitExceededException:
                    warnings.append(f"Rate limited during review comments for PR #{pr.number}")
                except Exception:
                    pass

                try:
                    review_summaries = [r.body for r in pr.get_reviews() if r.body and r.body.strip()][:5]
                except RateLimitExceededException:
                    warnings.append(f"Rate limited during reviews for PR #{pr.number}")
                except Exception:
                    pass

                try:
                    discussion = [c.body for c in pr.get_issue_comments() if c.body.strip()][:10]
                except RateLimitExceededException:
                    warnings.append(f"Rate limited during discussion for PR #{pr.number}")
                except Exception:
                    pass

            records.append(PRRecord(
                number           = pr.number,
                title            = pr.title,
                body             = (pr.body or "")[:2000],
                author           = pr.user.login if pr.user else "unknown",
                merge_commit_sha = pr.merge_commit_sha or "",
                merged_at        = pr.merged_at.isoformat() if pr.merged_at else "",
                labels           = [l.name for l in pr.labels],
                linked_issues    = _extract_issues(pr.body or ""),
                review_comments  = review_comments,
                review_summaries = review_summaries,
                discussion       = discussion,
            ))

            # Throttle only when rate limit is getting tight
            if remaining != -1 and remaining < 500:
                time.sleep(1)
            elif remaining != -1 and remaining < 2000:
                time.sleep(0.2)

        except RateLimitExceededException:
            warnings.append(f"GitHub rate limit hit at PR #{pr.number}. Collected {len(records)} PRs so far.")
            break
        except Exception as e:
            print(f"Skipping PR #{pr.number}: {e}")
            continue

    return FetchResult(prs=records, warnings=warnings)

def _extract_issues(body: str) -> list:
    pattern = r'(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+#(\d+)'
    return [int(n) for n in re.findall(pattern, body, re.IGNORECASE)]
