# Accuracy check

Run on 2026-11-09 with `python -m evals.run_eval` (local BGE-small embeddings, the last 200 commits of each repository, 9 minutes). The live site uses Pinecone's llama-text-embed-v2, so its numbers can differ.

| Repository | Commits | Linked PRs | Title questions | Description questions | Traced bugs |
|---|---:|---:|---:|---:|---:|
| [pallets/click](https://github.com/pallets/click) at `8abb77a` | 200 | 99 | 94 | 78 | 5 |
| [pallets/flask](https://github.com/pallets/flask) at `49943b5` | 200 | 52 | 52 | 40 | 5 |
| [encode/httpx](https://github.com/encode/httpx) at `b5addb6` | 200 | 180 | 174 | 145 | 3 |

## Search

Each merged pull request becomes a question: its title, or the first real sentence of its description. The answer is the commit the PR belongs to. That PR text is removed from the index first, and the title is also cut from the commit message (which often repeats it word for word), so the commit has to be found from the rest of its message and its diff.

Found = the answer is in the top k results. MRR (mean reciprocal rank) is 1 when the answer is always first, 0.5 when it's always second, and counts a miss outside the top 8 as 0.

The searches compared: the score mix the app used before; dense (embedding) search alone; and rank fusion, which merges the dense ranking with a BM25 keyword ranking by position, at several weights for the keyword side. Rank fusion also matches keywords over every commit rather than only the top 32 by meaning, and splits code into words properly (`ctx.ensure_object()` gives ctx, ensure, object).

### PR description questions, all repositories together

| Search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| Before: score mix (0.6 dense + 0.4 keywords) | 38% | 47% | 55% | 0.43 |
| Dense only | 40% | 57% | 68% | 0.49 |
| Rank fusion, keyword weight 1 | 47% | 64% | 74% | 0.56 |
| Rank fusion, keyword weight 2 | 48% | 66% | 76% | 0.58 |
| Rank fusion, keyword weight 3 (the app) | 49% | 67% | 78% | 0.59 |
| Rank fusion, keyword weight 4 | 50% | 68% | 78% | 0.60 |

### PR title questions, all repositories together

| Search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| Before: score mix (0.6 dense + 0.4 keywords) | 41% | 56% | 69% | 0.50 |
| Dense only | 47% | 63% | 75% | 0.56 |
| Rank fusion, keyword weight 1 | 51% | 70% | 81% | 0.62 |
| Rank fusion, keyword weight 2 | 53% | 70% | 83% | 0.63 |
| Rank fusion, keyword weight 3 (the app) | 53% | 70% | 84% | 0.63 |
| Rank fusion, keyword weight 4 | 52% | 69% | 83% | 0.63 |

### Per repository, before and now

| Repository, question, search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| pallets/click, description, before | 31% | 41% | 53% | 0.38 |
| pallets/click, description, now | 51% | 68% | 81% | 0.61 |
| pallets/click, title, before | 43% | 60% | 70% | 0.52 |
| pallets/click, title, now | 60% | 79% | 87% | 0.70 |
| pallets/flask, description, before | 40% | 48% | 55% | 0.45 |
| pallets/flask, description, now | 50% | 78% | 80% | 0.63 |
| pallets/flask, title, before | 46% | 62% | 75% | 0.55 |
| pallets/flask, title, now | 60% | 75% | 90% | 0.70 |
| encode/httpx, description, before | 41% | 50% | 56% | 0.46 |
| encode/httpx, description, now | 48% | 63% | 76% | 0.57 |
| encode/httpx, title, before | 38% | 53% | 67% | 0.47 |
| encode/httpx, title, now | 47% | 64% | 80% | 0.58 |

## Who broke it?

Every bug fix that Bug origins traced to one of the ingested commits becomes a report: the fix's commit message is the description and the traced commit is the answer. Only commits from before the fix are candidates, and the "already caused a bug" signal only counts fixes made before it. A fix message is shorter than a real bug report and the traced commit is a likely cause rather than a certain one, so treat these numbers as a rough guide.

### All repositories together

| Ranking | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| App ranking | 38% | 54% | 54% | 0.46 |
| Search only | 23% | 54% | 54% | 0.36 |
| Without change size | 31% | 54% | 54% | 0.41 |
| Earlier weights (search 0.5, files 0.3, type and earlier bugs 0.2) | 38% | 38% | 54% | 0.41 |
| App ranking, with the search from before | 38% | 54% | 54% | 0.46 |
| Newest commit first | 15% | 15% | 31% | 0.18 |

### Per repository, with the app's weights

| Repository | Cause in top 1 | Cause in top 3 | Cause in top 10 | MRR |
|---|---:|---:|---:|---:|
| pallets/click | 60% | 60% | 60% | 0.60 |
| pallets/flask | 20% | 40% | 40% | 0.30 |
| encode/httpx | 33% | 67% | 67% | 0.50 |
