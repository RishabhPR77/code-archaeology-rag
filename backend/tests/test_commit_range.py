"""Commit ranges: GitHub lookups for the preview, and pull requests limited to the range."""
from datetime import datetime, timezone

import httpx

from app.services import github, oauth
from ingestion import github_enricher


def _commit(sha: str, message: str, date: str) -> dict:
    return {"sha": sha * 40, "commit": {"message": message, "author": {"date": date}}}


def test_commit_total_comes_from_the_last_page_link(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path != "/repos/acme/app/commits":
            return httpx.Response(404, json={"message": "Not Found"})
        if request.url.params.get("page") == "1":
            return httpx.Response(200, json=[_commit("a", "Newest change\n\nwith a body", "2026-01-02T00:00:00Z")], headers={
                "Link": '<https://api.github.com/repositories/1/commits?per_page=1&page=2>; rel="next", '
                        '<https://api.github.com/repositories/1/commits?per_page=1&page=873>; rel="last"'})
        return httpx.Response(200, json=[_commit("b", "Older change", "2025-01-01T00:00:00Z")])

    monkeypatch.setattr(oauth, "http", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    github._LOOKUPS.clear()
    assert github.commit_total("acme/app", None) == 873      # one commit per page: the last page is the count
    assert github.commit_at("acme/app", 1, None) == {
        "number": 1, "sha": "aaaaaaa", "message": "Newest change", "date": "2026-01-02T00:00:00Z"}
    assert github.commit_at("acme/app", 500, None)["sha"] == "bbbbbbb"
    assert github.commit_total("acme/missing", None) is None


class _PR:
    def __init__(self, number: int, merged: datetime):
        self.number, self.merged_at, self.title, self.body = number, merged, f"PR {number}", ""
        self.user, self.merge_commit_sha, self.labels = None, f"{number:040d}", []


class _Github:
    pulls: list = []

    def __init__(self, *args, **kwargs):
        pass

    def get_repo(self, name):
        return self

    def get_pulls(self, **kwargs):
        return list(self.pulls)


def test_pull_requests_newer_than_the_range_are_left_out(monkeypatch):
    day = lambda d: datetime(2024, 1, d, tzinfo=timezone.utc)  # noqa: E731
    _Github.pulls = [_PR(n, day(d)) for n, d in [(5, 28), (4, 20), (3, 10), (2, 6), (1, 1)]]   # newest first
    monkeypatch.setattr(github_enricher, "Github", _Github)
    window = github_enricher.fetch_prs("acme/app", max_prs=2, since=datetime(2024, 1, 5), until=datetime(2024, 1, 11),
                                       details=False)
    # Without `until`, PRs #5 and #4 would have used up max_prs before the range was reached
    assert [p.number for p in window.prs] == [3, 2]
