# Accuracy check with the live site's embedding model

Since this run, the live site uses keyword weight 1, the best rank-fusion row below; it was weight 3 at the time, which is why that row is marked as the app.

Run on 2026-11-09 with `python -m evals.run_eval --hosted` (Pinecone's hosted llama-text-embed-v2, the live site's model, in a throwaway index; search only, the last 200 commits of each repository, 13 minutes).

| Repository | Commits | Linked PRs | Title questions | Description questions | Traced bugs |
|---|---:|---:|---:|---:|---:|
| [pallets/click](https://github.com/pallets/click) at `8abb77a` | 200 | 99 | 94 | 78 | not run |
| [pallets/flask](https://github.com/pallets/flask) at `49943b5` | 200 | 52 | 52 | 40 | not run |
| [encode/httpx](https://github.com/encode/httpx) at `b5addb6` | 200 | 180 | 174 | 145 | not run |

## Search

Each merged pull request becomes a question: its title, or the first real sentence of its description. The answer is the commit the PR belongs to. That PR text is removed from the index first, and the title is also cut from the commit message (which often repeats it word for word), so the commit has to be found from the rest of its message and its diff.

Found = the answer is in the top k results. MRR (mean reciprocal rank) is 1 when the answer is always first, 0.5 when it's always second, and counts a miss outside the top 8 as 0.

The searches compared: the score mix the app used before; dense (embedding) search alone; and rank fusion, which merges the dense ranking with a BM25 keyword ranking by position, at several weights for the keyword side. Rank fusion also matches keywords over every commit rather than only the top 32 by meaning, and splits code into words properly (`ctx.ensure_object()` gives ctx, ensure, object).

### PR description questions, all repositories together

| Search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| Before: score mix (0.6 dense + 0.4 keywords) | 40% | 50% | 65% | 0.47 |
| Dense only | 55% | 67% | 78% | 0.62 |
| Rank fusion, keyword weight 1 | 54% | 71% | 81% | 0.64 |
| Rank fusion, keyword weight 2 | 52% | 71% | 81% | 0.63 |
| Rank fusion, keyword weight 3 (the app) | 51% | 71% | 81% | 0.62 |
| Rank fusion, keyword weight 4 | 51% | 69% | 80% | 0.61 |

### PR title questions, all repositories together

| Search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| Before: score mix (0.6 dense + 0.4 keywords) | 46% | 64% | 79% | 0.56 |
| Dense only | 59% | 78% | 89% | 0.70 |
| Rank fusion, keyword weight 1 | 59% | 79% | 89% | 0.70 |
| Rank fusion, keyword weight 2 | 57% | 77% | 88% | 0.68 |
| Rank fusion, keyword weight 3 (the app) | 55% | 74% | 87% | 0.66 |
| Rank fusion, keyword weight 4 | 54% | 72% | 87% | 0.65 |

### Per repository, before and now

| Repository, question, search | Found in top 1 | Found in top 3 | Found in top 8 | MRR |
|---|---:|---:|---:|---:|
| pallets/click, description, before | 36% | 47% | 63% | 0.44 |
| pallets/click, description, now | 51% | 71% | 85% | 0.62 |
| pallets/click, title, before | 49% | 67% | 78% | 0.58 |
| pallets/click, title, now | 64% | 82% | 89% | 0.73 |
| pallets/flask, description, before | 42% | 42% | 65% | 0.47 |
| pallets/flask, description, now | 52% | 78% | 82% | 0.65 |
| pallets/flask, title, before | 52% | 67% | 83% | 0.61 |
| pallets/flask, title, now | 62% | 75% | 88% | 0.70 |
| encode/httpx, description, before | 41% | 53% | 66% | 0.49 |
| encode/httpx, description, now | 51% | 70% | 79% | 0.61 |
| encode/httpx, title, before | 43% | 61% | 78% | 0.54 |
| encode/httpx, title, now | 48% | 70% | 85% | 0.61 |
