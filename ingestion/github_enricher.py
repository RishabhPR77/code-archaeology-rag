import os, re, time
from dataclasses import dataclass, field
from github import Github, RateLimitExceededException

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
        return g.get_rate_limit().core.remaining
    except Exception:
        return -1

def fetch_prs(repo_name: str, max_prs: int = 200) -> FetchResult:
    g = Github(os.getenv("GITHUB_TOKEN"))
    repo = g.get_repo(repo_name)
    records = []
    warnings = []

    remaining = _check_rate(g)
    if remaining != -1 and remaining < 100:
        warnings.append(f"GitHub API rate limit too low ({remaining} remaining). Skipping PR fetch.")
        return FetchResult(prs=records, warnings=warnings)

    try:
        pulls = repo.get_pulls(state="closed", sort="updated")
    except RateLimitExceededException:
        warnings.append("GitHub rate limit hit while opening PR list.")
        return FetchResult(prs=records, warnings=warnings)

    for pr in pulls:
        if not pr.merged:
            continue
        if len(records) >= max_prs:
            break

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

    if not warnings:
        print(f"Fetched {len(records)} merged PRs")
    else:
        for w in warnings:
            print(f"WARNING: {w}")

    return FetchResult(prs=records, warnings=warnings)

def _extract_issues(body: str) -> list:
    pattern = r'(?:fix(?:es)?|close[sd]?|resolve[sd]?)\s+#(\d+)'
    return [int(n) for n in re.findall(pattern, body, re.IGNORECASE)]
