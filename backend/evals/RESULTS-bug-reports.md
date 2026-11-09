# Who broke it? on real bug reports

Run on 2026-11-09 with `python -m evals.bug_reports` (local BGE-small embeddings, the last 1000 commits of each repository, 37 minutes).

A fix is a commit whose pull request or message closes a GitHub issue. Bug origins traces what it changed back to the commit that last wrote those lines, and that commit is the answer. The report is the issue's title and description, the way a user would paste them. Only commits from before the fix are ranked, and the "already caused a bug" signal only counts earlier fixes. Tracing finds a likely cause rather than a certain one, so the true accuracy is somewhat higher than measured.

| Repository | Commits | Close an issue | Traced to an earlier commit | Cases (one per issue) | Labelled bug | Issue names a file |
|---|---:|---:|---:|---:|---:|---:|
| [pallets/click](https://github.com/pallets/click) at `8abb77a` | 1000 | 242 | 40 | 32 | 0 | 30 |
| [pallets/flask](https://github.com/pallets/flask) at `49943b5` | 1000 | 194 | 29 | 24 | 0 | 21 |
| [encode/httpx](https://github.com/encode/httpx) at `b5addb6` | 1000 | 192 | 104 | 101 | 19 | 92 |

## All 157 cases

| Ranking | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| App weights (search 0.5, files 0.3, risk 0.2) | 17% | 32% | 50% | 0.26 |
| Search only | 17% | 25% | 43% | 0.24 |
| No risk (0.7, 0.3, 0) | 18% | 27% | 45% | 0.25 |
| More files (0.4, 0.5, 0.1) | 17% | 31% | 50% | 0.26 |
| More risk (0.4, 0.3, 0.3) | 15% | 29% | 52% | 0.25 |
| App weights, fix message as the report | 15% | 30% | 48% | 0.25 |
| Newest commit first | 4% | 6% | 12% | 0.06 |

### Per repository, app weights

| Repository | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| pallets/click (32 cases) | 25% | 44% | 62% | 0.35 |
| pallets/flask (24 cases) | 21% | 25% | 38% | 0.25 |
| encode/httpx (101 cases) | 13% | 30% | 50% | 0.23 |
