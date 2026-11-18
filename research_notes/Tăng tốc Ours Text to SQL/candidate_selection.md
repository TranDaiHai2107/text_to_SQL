# Cost-efficient candidate generation and selection for LLM Text-to-SQL (2023-2026)

Target context: 3 candidates (gpt-5-mini), plus an LLM verify and repair step for each candidate and an LLM selector, comes to about 15 calls and 10-12 min per question. Patient rows must not reach the LLM, but result fingerprints can be compared locally.

## Q1. Execution-result voting vs an LLM selector: accuracy and candidate count

### Takeaway
Voting on execution results reliably adds 1.5-6 EX points over a single query. A trained or strong selector adds another 0.6-4 points on top of voting. Most of the selector's gain comes from cases where the votes are split, so you can run the selector only on those.

### Cited Findings
- CHASE-SQL (BIRD dev, Gemini 1.5 Pro):
  - A single query gets 63.01%. Self-consistency gets 68.84%, the pairwise selector gets 73.01%, and the oracle upper bound is 82.79%.
  - Replacing the selector with self-consistency costs 4.17 points. A listwise "ranker agent" does worse (65.51%, −7.5).
  - The selector is a fine-tuned binary pairwise model.
  - Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)
- CHASE-SQL per-generator results (Table 6, T=0.5): the selector beats self-consistency by about 3-6 points. Examples are QP 65.78 → 71.70 and OS 67.34 → 70.40. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL (BIRD dev) with 3 candidates:
  - The full system with its selection model gets 71.58%. Self-consistency alone gets 68.84% (−2.74).
  - With 5 candidates it gets 73.34%.
  - Source: [XiYan-SQL](https://arxiv.org/html/2411.08599)
- MCS-SQL (BIRD dev):
  - Majority vote gets 62.8. LLM multiple-choice selection without the confidence filter gets 62.5, and with the filter it gets 63.4. Spider shows the same pattern: 89.2 / 85.4 / 89.5.
  - The filter removes candidates that share their execution result with less than 20% of the pool.
  - Up to 100 candidates are generated (5 prompts × 20).
  - An unfiltered listwise LLM selection can be worse than plain voting.
  - Source: [MCS-SQL](https://arxiv.org/html/2405.07467)
- OmniSQL: maj@8 over greedy adds +1.7 to +2.5 on BIRD dev (e.g. 7B: 63.9 → 66.1) and adds 0-2.2 on Spider. — [OmniSQL](https://arxiv.org/html/2503.02240)
- N-rep ("Cheaper, Better, Faster, Stronger", BIRD dev full set):
  - Regular voting gets 67.2 EX with 0 selection calls.
  - Pairwise LLM selection used only on low-confidence cases gets 68.8 EX with 2,436 calls.
  - LLM-based voting on every question gets 67.9 EX with 6,178 calls.
  - Source: [N-rep](https://arxiv.org/html/2505.14174)

### Inferences
- With only 3 candidates, voting has little to work with. A 1-1-1 split carries no signal, so a selector is still needed for split cases.
- Running the selector on every question is waste. N-rep's gated selector got higher accuracy with about 60% fewer calls than an always-on LLM selector.

### Gaps
- I found no published comparison of voting vs selector specific to gpt-5-mini or to clinical EHR datasets.

## Q2. Early stopping and adaptive sample counts

### Takeaway
Adaptive stopping on execution-result agreement is standard practice in 2025-2026. One recipe: sample sequentially, group candidates by result, and stop when a group reaches a threshold. Another is difficulty routing, which cuts tokens by about 40% without losing accuracy.

### Cited Findings
- ZAS-SQL EGES:
  - The method samples up to N_max=20 candidates at τ=1, executes each, and groups them by identical result set. It discards errors but keeps empty results.
  - It stops as soon as any group reaches θ=6 and returns the shortest SQL in that group.
  - EGES adds +1.0 / +1.5 / +0.9 EX with DeepSeek-V3.
  - The paper gives no figure for calls saved.
  - Source: [ZAS-SQL](https://arxiv.org/html/2606.08245v1)
- "Knowing When to Stop" (2026):
  - The method uses lightweight 1-D models that predict when execution-consistency has converged, so the stopping point is set per question.
  - Baselines are a Beta-Bernoulli stopping rule and a learned fixed run count.
  - It is evaluated on BIRD and two production datasets.
  - The abstract gives no savings numbers.
  - Source: [arXiv 2607.03991](https://arxiv.org/abs/2607.03991)
- EvoSQL stops refinement once the top-K pool meets a confidence threshold and a ratio of shared execution outcome. This comes from a search snippet only. — [EvoSQL](https://arxiv.org/pdf/2607.20489)
- EllieSQL routes questions by complexity to Basic, Intermediate or Advanced pipelines. Its Qwen2.5-0.5B router cuts tokens by more than 40% on BIRD dev with no loss in performance and doubles TEP. — [EllieSQL](https://arxiv.org/abs/2503.22402)
- N-rep gates pairwise selection on vote confidence: it runs selection when every candidate has 1 vote, or when the top two are tied or close. It uses a median of 8 and a mean of 10.9 calls per question, against 100+ for CHASE-SQL. — [N-rep](https://arxiv.org/html/2505.14174)

### Inferences
- A cascade fits this system:
  1. Generate 2 candidates.
  2. If their result fingerprints match, accept and skip verify, repair and select.
  3. Otherwise generate the 3rd candidate.
  4. If 2 of 3 agree, accept the majority.
  5. Only on a 1-1-1 split, or when all results are empty or errors, call repair and the selector.
- Run repair only on candidates that error, return empty, or are outliers, not on every candidate. That should cut the roughly 15 calls to around 3-5 on easy or consistent questions. This figure is my estimate, not a published one.

### Gaps
- No 2023-2026 paper I found reports the exact share of questions with early agreement on BIRD. "Let's Sample Step by Step" and Adaptive-Consistency are general-purpose LLM methods, and I did not verify SQL-specific numbers for them.

## Q3. Pairwise vs listwise selection and its cost

### Takeaway
On BIRD, pairwise selection beats listwise ranking (CHASE-SQL: 73.0 for pairwise vs 65.5 for the ranker), but it costs O(n²) calls. Group candidates by result first, then compare only one representative from each distinct result group.

### Cited Findings
- CHASE-SQL's pairwise selector scores 73.01 against 65.51 for a listwise ranker agent. It sums over C(n,2) pairs and evaluates both orderings to reduce order bias. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- N-rep compares each pair twice with the order swapped, and only in low-confidence cases. — [N-rep](https://arxiv.org/html/2505.14174)
- MCS-SQL keeps only the fastest query from each identical-result group before its listwise multiple-choice selection. — [MCS-SQL](https://arxiv.org/html/2405.07467)

### Inferences
- With 3 candidates, pairwise selection needs at most 3 pairs, or 6 calls with order swapping. If two candidates share a result, there are only 2 groups, so 1 pair (2 calls) is enough. One listwise call over 3 candidates is also cheap. The gap between pairwise and listwise may be smaller with 3 candidates than with 21, which is not tested.

### Gaps
- I found no direct cost and accuracy comparison of pairwise vs listwise selection at n=3.

## Q4. Diminishing returns in candidate count

### Takeaway
Gains flatten at roughly 20 candidates (CHASE-SQL). Going from 3 to 5 candidates still gives a measurable +1.8 points (XiYan-SQL).

### Cited Findings
- CHASE-SQL uses 21 candidates (7 per generator × 3 generators). The authors say more than 20 "did not yield significant improvements". — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL: 3 candidates give 71.58 and 5 give 73.34. — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- Alpha-SQL:
  - Upper bound and final accuracy both increase with the number of MCTS rollouts (default 24). The paper shows this only in a figure.
  - Selection takes the candidate whose execution results agree most with the other candidates.
  - Source: [Alpha-SQL](https://arxiv.org/html/2502.17248)
- OmniSQL uses maj@8 as its standard setting. — [OmniSQL](https://arxiv.org/html/2503.02240)
- N-rep vs CHASE-SQL:

  | Method | EX | Cost per query |
  |---|---|---|
  | N-rep | 69.25 | $0.039 |
  | CHASE-SQL | 74.9 | $0.44 |

  CHASE-SQL buys about 5.6 points for about 11× the cost. — [N-rep](https://arxiv.org/html/2505.14174)

### Gaps
- Exact points on the scaling curves for CHASE-SQL and Alpha-SQL are only in figures, so I could not extract them.

## Q5. Selection with result fingerprints only (no data sent to the LLM), ties and empty results

### Takeaway
All the voting methods above use only result-set equality, so they can run entirely locally with hashes. Tie-breaking rules from the literature are: prefer the fastest query, prefer the shortest SQL, and use the size of the agreeing group as confidence.

### Cited Findings
- OpenSearch-SQL picks the candidate with the highest execution-result consistency and breaks ties by shortest execution time. — [OpenSearch-SQL](https://arxiv.org/pdf/2502.14913)
- MCS-SQL drops syntax errors and timeouts (180s), groups candidates by identical results, keeps the fastest in each group, and filters out results shared by less than 20% of the pool. — [MCS-SQL](https://arxiv.org/html/2405.07467)
- ZAS-SQL keeps empty result sets in the vote and breaks ties by shortest SQL. — [ZAS-SQL](https://arxiv.org/html/2606.08245v1)
- Alpha-SQL uses the fraction of agreeing samples as the confidence score for a candidate. — [Alpha-SQL](https://arxiv.org/html/2502.17248)

### Inferences
- Fingerprint design:
  - Hash the result as an order-insensitive multiset unless the SQL has ORDER BY.
  - Normalize floats by rounding them.
  - Add a fingerprint of row count and column count.
- An LLM selector can still be given SQL text, column names and types, row counts, and a "same as candidate X" flag, without seeing any patient rows.
- Treat empty results as low-confidence even when the candidates agree. Several wrong queries can easily agree on an empty result. This is my inference: ZAS-SQL counts empty results as normal votes and does not penalize them.

### Gaps
- No paper I found evaluates selection specifically under a no-data-to-LLM privacy constraint, or reports how often agreement on an empty result is wrong.
