# Accuracy check

Run on 2026-11-09 with `python -m evals.run_eval` (local BGE-small embeddings, the last 200 commits of each repository, 17 minutes). The live site uses Pinecone's llama-text-embed-v2, so its numbers can differ.

| Repository | Commits | Linked PRs | Title questions | Description questions | Traced bugs |
|---|---:|---:|---:|---:|---:|
| [pallets/click](https://github.com/pallets/click) at `8abb77a` | 200 | 99 | 94 | 78 | 5 |
| [pallets/flask](https://github.com/pallets/flask) at `49943b5` | 200 | 52 | 52 | 40 | 5 |
| [encode/httpx](https://github.com/encode/httpx) at `b5addb6` | 200 | 0 | 0 | 0 | 3 |

No pull requests were fetched for encode/httpx (GitHub's limit for requests without a token ran out), so it only counts toward Who broke it?.

## Search

Each merged pull request becomes a question: its title, or the first real sentence of its description. The answer is the commit the PR belongs to. That PR text is removed from the index first, and the title is also cut from the commit message (which often repeats it word for word), so the commit has to be found from the rest of its message and its diff.

Found = the answer is in the top k results. MRR (mean reciprocal rank) is 1 when the answer is always first, 0.5 when it's always second, and counts a miss outside the top 8 as 0.

### PR description questions, all repositories together

| Dense share (alpha) | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| 1.0 (dense only) | 44% | 56% | 71% | 0.52 |
| 0.8 | 36% | 44% | 63% | 0.43 |
| 0.6 (the app) | 34% | 43% | 53% | 0.40 |
| 0.4 | 31% | 41% | 53% | 0.37 |
| 0.2 | 30% | 39% | 52% | 0.36 |
| 0.0 (keywords only) | 31% | 39% | 51% | 0.37 |

### PR title questions, all repositories together

| Dense share (alpha) | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| 1.0 (dense only) | 53% | 66% | 81% | 0.62 |
| 0.8 | 48% | 63% | 75% | 0.57 |
| 0.6 (the app) | 44% | 60% | 72% | 0.53 |
| 0.4 | 43% | 60% | 71% | 0.52 |
| 0.2 | 44% | 58% | 68% | 0.52 |
| 0.0 (keywords only) | 43% | 56% | 68% | 0.51 |

### Per repository, with the app's settings (alpha 0.6)

| Repository, question | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| pallets/click, description | 31% | 41% | 53% | 0.38 |
| pallets/click, title | 43% | 60% | 70% | 0.52 |
| pallets/flask, description | 40% | 48% | 55% | 0.45 |
| pallets/flask, title | 46% | 62% | 75% | 0.55 |
| encode/httpx, description | n/a | n/a | n/a | n/a |
| encode/httpx, title | n/a | n/a | n/a | n/a |

## Who broke it?

Every bug fix that Bug origins traced to one of the ingested commits becomes a report: the fix's commit message is the description and the traced commit is the answer. Only commits from before the fix are candidates, and the "already caused a bug" signal only counts fixes made before it. A fix message is shorter than a real bug report and the traced commit is a likely cause rather than a certain one, so treat these numbers as a rough guide.

### All repositories together

| Ranking | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| App (search 0.5, files 0.3, risk 0.2) | 31% | 31% | 38% | 0.33 |
| Search only | 31% | 38% | 46% | 0.36 |
| No risk (0.7, 0.3, 0) | 31% | 38% | 46% | 0.36 |
| More risk (0.4, 0.3, 0.3) | 31% | 31% | 31% | 0.31 |
| Newest commit first | 15% | 15% | 31% | 0.18 |

### Per repository, with the app's weights

| Repository | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| pallets/click | 40% | 40% | 40% | 0.40 |
| pallets/flask | 20% | 20% | 40% | 0.25 |
| encode/httpx | 33% | 33% | 33% | 0.33 |
