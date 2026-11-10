# Who broke it? on real bug reports

Run on 2026-11-10 with `python -m evals.bug_reports` (local BGE-small embeddings, the last 1000 commits of each repository, 26 minutes).

A fix is a commit whose pull request or message closes a GitHub issue. Bug origins traces what it changed back to the commit that last wrote those lines, and that commit is the answer. The report is the issue's title and description, the way a user would paste them. Each case is ranked as of when the issue was opened: only earlier commits are candidates, and the "already caused a bug" signal only counts earlier fixes. A traced cause newer than the issue can't be right, so those cases are left out.

Many issues a pull request closes are feature requests, where "who broke it" has no answer. An issue counts as a real bug report if it's labelled as a bug, the commit that closed it is a fix, or it has a Python traceback. Tracing finds a likely cause rather than a certain one, and a fix can trace to several commits: the main rows count only the commit that wrote most of the fixed lines, and one row counts any of them.

| Repository | Commits | Close an issue | Traced to an earlier commit | Cause newer than the issue | Cases (one per issue) | Real bug reports | Issue names a file |
|---|---:|---:|---:|---:|---:|---:|---:|
| [pallets/click](https://github.com/pallets/click) at `8abb77a` | 1000 | 242 | 40 | 24 | 15 | 8 | 14 |
| [pallets/flask](https://github.com/pallets/flask) at `49943b5` | 1000 | 194 | 29 | 4 | 22 | 6 | 19 |
| [encode/httpx](https://github.com/encode/httpx) at `b5addb6` | 1000 | 192 | 104 | 15 | 86 | 35 | 79 |

## Real bug reports (49)

| Ranking | Cause in top 1 | Cause in top 3 | Cause in top 5 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|---:|
| App ranking | 35% | 57% | 57% | 61% | 0.46 |
| App ranking, any traced cause counts | 35% | 57% | 57% | 63% | 0.46 |
| Without change size | 35% | 49% | 55% | 61% | 0.43 |
| Without code names | 31% | 53% | 57% | 61% | 0.41 |
| Without recency | 35% | 53% | 57% | 61% | 0.44 |
| Without named files | 29% | 53% | 55% | 61% | 0.41 |
| Earlier weights (search 0.5, files 0.3, type and earlier bugs 0.2) | 27% | 43% | 51% | 55% | 0.36 |
| Search only | 24% | 35% | 43% | 53% | 0.32 |
| App ranking, fix message as the report | 35% | 47% | 53% | 61% | 0.42 |
| Newest commit first | 2% | 6% | 6% | 10% | 0.04 |

| Repository, app ranking | Cause in top 1 | Cause in top 3 | Cause in top 5 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|---:|
| pallets/click (8 cases) | 38% | 75% | 75% | 88% | 0.58 |
| pallets/flask (6 cases) | 50% | 67% | 67% | 67% | 0.58 |
| encode/httpx (35 cases) | 31% | 51% | 51% | 54% | 0.41 |

## Every issue (123)

| Ranking | Cause in top 1 | Cause in top 3 | Cause in top 5 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|---:|
| App ranking | 22% | 43% | 46% | 56% | 0.34 |
| App ranking, any traced cause counts | 27% | 50% | 53% | 64% | 0.40 |
| Without change size | 24% | 37% | 45% | 53% | 0.32 |
| Without code names | 21% | 41% | 46% | 57% | 0.33 |
| Without recency | 23% | 41% | 47% | 54% | 0.33 |
| Without named files | 19% | 41% | 46% | 56% | 0.31 |
| Earlier weights (search 0.5, files 0.3, type and earlier bugs 0.2) | 18% | 35% | 42% | 50% | 0.28 |
| Search only | 19% | 28% | 35% | 45% | 0.26 |
| App ranking, fix message as the report | 24% | 38% | 46% | 56% | 0.33 |
| Newest commit first | 2% | 5% | 6% | 10% | 0.04 |

| Repository, app ranking | Cause in top 1 | Cause in top 3 | Cause in top 5 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|---:|
| pallets/click (15 cases) | 33% | 60% | 60% | 73% | 0.48 |
| pallets/flask (22 cases) | 18% | 32% | 36% | 36% | 0.26 |
| encode/httpx (86 cases) | 21% | 43% | 47% | 58% | 0.33 |
