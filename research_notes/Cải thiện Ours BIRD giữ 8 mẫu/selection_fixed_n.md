# Compute-matched evaluation and better selection among a FIXED set of N SQL candidates (BIRD dev focus)

Scope note: all numbers below were read from the primary paper pages (arXiv HTML/ar5iv) unless marked "(search snippet only)". "Training-free" = no fine-tuning of generator or selector. Benchmarks other than BIRD dev are marked explicitly.

## Q1. How do text-to-SQL / code papers report compute- or sample-matched comparisons, and what gains survive at equal N?

### Takeaway
Few text-to-SQL papers do a true compute-matched comparison; the cleanest sample-matched tables are CSC-SQL (SC vs CSC at N=4..64 on BIRD dev) and CHASE-SQL (SC vs selector on the same candidate pool). At equal N, gains of roughly +1 to +2 EX survive for training-free or lightly-added selectors, and +3 to +6 only with a fine-tuned selector; plain SC itself is nearly saturated by N=8-16 for strong generators.

### Cited Findings
- CSC-SQL, BIRD dev, T=0.8, sample-matched table (SC = execution-result majority vote; CSC = SC + one extra "merge revision" call over the top-2 vote groups using a GRPO-trained 7B merge model). At N=8: Qwen2.5-Coder-7B (untrained generator) SC 62.18 vs CSC 64.28 (+2.10); Qwen2.5-Coder-32B SC 67.56 vs CSC 69.12 (+1.56); XiYanSQL-32B-2412 SC 67.50 vs CSC 69.37 (+1.87); Qwen2.5-Coder-3B SC 49.87 vs CSC 51.43. Reported CSC gain range over all settings: +0.72 to +5.54. The extra merge call is not compute-matched; the paper gives time/cost (Table 7) but no equal-cost comparison. — [CSC-SQL, arXiv 2505.13271](https://arxiv.org/html/2505.13271)
- CSC-SQL, SC saturation in the same table (BIRD dev): Qwen2.5-Coder-32B SC 66.97 (N=4) → 67.56 (N=8) → 68.54 (N=16) → 68.58 (N=32) → 68.67 (N=64), i.e. only +1.11 from N=8 to N=64; XiYanSQL-32B SC 67.50 (N=8) → 68.95 (N=64); Qwen2.5-Coder-7B SC 62.18 (N=8) → 64.45 (N=64); GRPO-trained 7B SC 64.95 (N=8) → 66.15 (N=64). — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CSC-SQL ablation: with an UNTRAINED merge model (Qwen2.5-Coder-7B generator, N=8), CSC gives 61.73 vs SC 61.86 (slightly worse); the GRPO-trained merge model gives 66.91 vs SC 65.02. Revising the top-1 group only = 64.73, top-2 = 66.91, top-3 = 65.05 (top-2 best). — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CHASE-SQL (ICLR 2025), BIRD dev, Gemini 1.5 Pro generators, same candidate pool per generator (Table 6): SC vs fine-tuned pairwise selection agent: QP T=0.5 65.78→71.70 (+5.92); QP T=1.8 65.51→71.73; DC T=0.5 66.43→71.31; DC T=1.8 64.41→70.53; OS T=0.5 67.34→70.40 (+3.06); OS T=1.8 66.88→71.38. Full pipeline (21 candidates = 7 per generator x 3): selector 73.01 vs SC 68.84 vs a "ranker agent" 65.51; upper bound 82.79; single query 63.01. Selector = LoRA-tuned Gemini 1.5 Flash (~3.8K training samples) — NOT training-free. Paper says going beyond ~20 candidates "did not yield significant improvements." — [CHASE-SQL, arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- CHASE-SQL binary pairwise selection accuracy (Table 5): Claude-3.5-Sonnet 60.21, untuned Gemini-1.5-Pro 63.98 (text elsewhere says 58.01, internal inconsistency), tuned Gemma-2-9B 64.28, tuned Gemini-1.5-Flash 71.01. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- DPC (training-free), N=5, T=0.7, BIRD Mini-Dev (500 q, NOT full dev): SC vs DPC: Qwen2.5-Coder-7B 46.4→47.6; DeepSeek-V3.2 51.2→53.4; GPT-5 49.4→51.2; Multiple-choice selection (MCS-style LLM pick) 43.6 / 51.0 / 50.4, i.e. at or below SC. Spider test: SC 76.5/71.6/72.2 vs DPC 77.5/73.2/73.3. Pass@5 upper bound BIRD 57.6/58.8/56.4. DPC lead over SC reported to widen from 1.2 to 2.4 as N grows 3→11 (Fig. 3, model unstated). — [DPC, arXiv 2604.15163](https://arxiv.org/html/2604.15163v1)
- Outcome reward models for BoN text-to-SQL (fine-tuned ORMs, Qwen2/Granite3/Llama3/OmniSQL): gains over majority vote +2.91 (BIRD) / +0.93 (Spider); over execution-based best-of-N +4.33 / +2.10; abstract says ORMs benefit more from larger N than Maj. N and absolute numbers not in abstract. — [arXiv 2509.01308](https://www.arxiv.org/abs/2509.01308)
- Agentar-Scale-SQL reports +1.82 EX over its self-consistency baseline; budget equality not verified (search snippet only). — [Agentar-Scale-SQL, arXiv 2509.24403](https://arxiv.org/pdf/2509.24403)
- SLM-SQL reports SC gains on BIRD dev "plateau beyond 16 samples" (sweep 4→64) (search snippet only). — [An Exploration of Small Language Models for Text-to-SQL](https://aclanthology.org/2025.findings-ijcnlp.92.pdf)
- General code/math (NOT text-to-SQL): Large Language Monkeys — coverage grows log-linearly over four orders of magnitude of samples (SWE-bench Lite, DeepSeek-Coder-V2-Instruct 15.9% @1 → 56% @250), but where no automatic verifier exists, majority voting and reward-model selection plateau beyond several hundred samples. — [Brown et al. 2024, arXiv 2407.21787](https://arxiv.org/abs/2407.21787)
- Snell et al. 2024 (math, NOT SQL): compute-optimal per-prompt allocation is >4x more efficient than best-of-N; in a FLOPs-matched evaluation a smaller model with test-time compute can beat a 14x larger model, but only on prompts where the base model already has non-trivial success. — [Snell et al., arXiv 2408.03314](https://arxiv.org/abs/2408.03314)

### Inferences
- The fair-comparison convention that exists in the literature is "same candidate pool / same N, vary only the selector" (CHASE-SQL Table 6, CSC-SQL Table 1, DPC Table 2). Reporting Ours vs OmniSQL-maj@8 on the same 8 samples, plus extra selector calls counted separately (calls/tokens per question), matches this convention.
- With a gpt-4o-mini-class generator, the plausible training-free gain at N=8 from a better selector is about +1 to +2 EX (DPC, CSC-style numbers), not the +4 to +6 of CHASE-SQL, which needs a fine-tuned selector.
- CSC-SQL's untrained merge model (-0.13 vs SC) and CHASE's ~58-64% untuned pairwise accuracy agree with the student's own finding that untuned gpt-4o-mini selectors are close to a coin flip.
- SC curves in CSC-SQL (+1.1 from N=8→64 for 32B models) support the argument that maj@8 is already near saturation, so selection, not more samples, is where headroom is.

### Gaps
- I did not verify sample-matched tables for Alpha-SQL, OpenSearch-SQL, XiYan-SQL, RSL-SQL, ReFoRCE, MCTS-SQL, SQL-o1 or Archer within the tool budget; no numbers are reported for them here.
- No paper found that reports a strictly FLOPs/token-matched comparison (SC with extra samples vs selector with extra call at the same token cost) on BIRD.

## Q2. Aggregation without extra samples: which techniques were evaluated on BIRD/Spider, with what gains over plain majority at the same N?

### Takeaway
On text-to-SQL, the training-free aggregators with measured numbers (USC, MCS-style LLM pick, log-probability) roughly tie execution-result voting; the training-free method with a measured gain is DPC (+1.2 to +2.2 on BIRD Mini-Dev at N=5), which builds a small database that separates the top-2 clusters. Logprob weighting has no published text-to-SQL selection gain; P(True)-style confidence weighting (CISC) helps on math/QA, not tested on SQL.

### Cited Findings
- Universal Self-Consistency (training-free; the LLM picks the most consistent of the samples), BIRD-SQL dev, gpt-3.5-turbo, 8 samples, 1-shot CoT: Greedy 42.4, Random 41.9, SC-Exec (execution-result vote) 45.6, USC 45.5; VES 44.4 / 44.0 / 48.1 / 48.8. Oracle 53.3. USC rises from 42.4 at k=1 to 45.5 at k=8. ARCADE: SC-Exec fuzzy 30.3, USC 30.1. So USC matches but does not beat execution voting at N=8. — [Chen et al. 2023, arXiv 2311.17311](https://arxiv.org/html/2311.17311)
- MBR-exec (training-free; marginalize over candidates with the same execution semantics, likelihood used only as tie-breaker), Codex code-davinci-001, 25 samples, T=0.3, five 3-shot prompts pooled. SPIDER (not BIRD): greedy 50.8, random sample 48.5, MBR-exec 63.6; MBPP 47.3→58.2; NL2Bash 52.8→58.5. MBR-exec on greedy candidates: Spider 62.1. Authors recommend T<0.5; Spider/MBPP accuracy drops sharply as T→1.0. Maximum-likelihood ranking numbers only in figures; ML restricted to executable Spider queries beat MBR-exec across sample sizes. — [Shi et al. 2022, ar5iv 2204.11454](https://ar5iv.labs.arxiv.org/html/2204.11454)
- LEVER (requires TRAINING a T5-base verifier on ~7K Spider train examples; inputs = question + SQL + linearized execution result), Codex code-davinci-002, 50 samples, T=0.6, SPIDER dev: greedy 75.3, EP+ML 77.3, LEVER 81.9; prior training-free MBR-Exec 75.2, Coder-Reviewer 74.5. Removing execution results from the verifier input: -3.0. Reducing samples 50→10: -1.8. T5-3B verifier 83.1. — [Ni et al. 2023, ar5iv 2302.08468](https://ar5iv.labs.arxiv.org/html/2302.08468)
- DPC mechanism (training-free): cluster by execution result, take largest (Champion) and second-largest (Challenger) clusters, have LLM agents build a Minimal Distinguishing Database where the two disagree, write a pandas reference solution on it, select by Bipartite Soft-F1 against the reference. Cost (Qwen, BIRD): ~3.8K tokens and 4.2 s per question vs MCS ~4.2K tokens and 5.1 s; SC ~0.8 s. Breakdown (BIRD, Qwen): on Majority-Correct questions SC 100% vs DPC 97.0%; on Majority-Incorrect questions SC 0% vs DPC 21.4% — gain comes from overturning wrong majorities at a small cost on correct ones. — [DPC](https://arxiv.org/html/2604.15163v1)
- Correctness signals with gpt-4o-mini, K=8, T=0.7, 800-question BIRD slice (AUROC of predicting whether the modal query is correct): string self-consistency 0.675, structural SC 0.619, execution SC 0.613, white-box token log-probability 0.669 (vs string SC -0.006, CI [-0.028, +0.017], not significant), schema-relevance 0.553, gpt-4o-mini YES/NO-logit verifier 0.724, GPT-4o verifier 0.770, Claude-Sonnet-4.6 verifier 0.776, GPT-4o + Claude ensemble 0.822. Modal-query EX on that slice 0.451. The paper does NOT report candidate-selection accuracy or logprob+SC combination. — [What Predicts Correctness in Text-to-SQL?, arXiv 2607.06799](https://arxiv.org/html/2607.06799v1)
- Contextual AI (BIRD dev, Qwen2.5-Coder-32B and Gemini models): log-probs give "a slightly better signal than consistency alone at small k" (values only in figures); final score = weighted average of candidate log-prob and a trained Qwen-2.5-32B reward model, α=0.4 tuned on a dev subset, ~73% BIRD dev with many candidates (up to 1024 in one experiment); reward-model selection alone ~70%. Reward model is trained, not training-free. — [Contextual AI blog](https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system)
- CISC (Confidence-Informed Self-Consistency, ACL Findings 2025; math/QA benchmarks, NOT SQL): confidence-weighted majority vote, confidence from the model itself; across nine models and four datasets it beats SC in nearly all configurations, cutting needed samples by >40% on average; with 8 samples it beats 30-sample SC. P(True) was reportedly the best confidence signal; the best-calibrated method was the least useful for voting; at very high temperature weights become uniform and CISC collapses to SC. — [Taubenfeld et al., arXiv 2502.06233](https://arxiv.org/html/2502.06233v2)
- CA-SQL: "sum-of-rewards voting" (accumulated candidate-evaluation scores) reported to beat majority voting, 51.72% EX on BIRD (search snippet only; model/N not verified). — [CA-SQL, arXiv 2605.08057](https://arxiv.org/pdf/2605.08057v1)
- N-best reranking (Zeng et al. 2022, SPIDER, fine-tuned T5 rerankers): oracle from a 10-best list = +7.7 EM/EX; combined reranking with T5-Large = +1.0 EM, +2.5 EX. — [arXiv 2210.10668](https://arxiv.org/abs/2210.10668v1)

### Inferences
- For the student's 27/300 selection losses and 55/300 no-majority questions, the most directly applicable training-free idea with BIRD evidence is DPC-style top-2 disambiguation (only Champion vs Challenger, i.e. the same "top-2 group" focus that CSC-SQL found optimal). Its measured gain on BIRD Mini-Dev was +1.2 to +2.2 at N=5.
- The token log-prob of gpt-4o-mini is not a stronger correctness signal than vote share on BIRD (0.669 vs 0.675 AUROC), so logprob-weighted voting likely gives little. A gpt-4o-mini YES/NO-logit verifier scores higher (0.724), so P(True)-style weighting (CISC) used only as a soft tie-breaker is the more promising variant; no SQL selection-accuracy number exists for it yet.
- USC at N=8 with gpt-3.5 tied execution voting on BIRD, consistent with the student's finding that listwise gpt-4o-mini selectors do not beat the vote except on ties.
- MBR-exec on Spider is essentially execution-result voting; its big gain is over greedy, not over majority vote. Its finding that T<0.5 works better than T→1 is relevant to T=0.8 sampling, but changing T changes the samples (out of scope for a fixed-8 comparison).
- LEVER, CHASE selector, ORMs and Contextual AI reward models all need training; they show what a trained verifier can do (+2.9 over Maj on BIRD for ORMs, +3 to +6 for CHASE), not what gpt-4o-mini prompting can do.

### Gaps
- No BIRD paper found that tests "soft" execution-result equivalence (column-subset, containment, numeric tolerance) as a voting relaxation with numbers; DPC's Bipartite Soft-F1 is the closest (used for matching against a reference, not for clustering). ARCADE "fuzzy" SC-Exec (30.3 vs strict 29.8) is the only fuzzy-match vote number found, and ARCADE is not SQL.
- No measured result found for NL back-translation (SQL→question similarity) reranking on BIRD; the N-best reranking paper is on Spider with fine-tuned models.
- No published BIRD result for logprob-weighted voting with gpt-4o-mini; CodeT-style generated test cases for SQL were not found apart from DPC's distinguishing database.

## Q3. Does a cheap single extra call (verifier/selector) help small proprietary models at fixed N, and under what gating?

### Takeaway
Evidence is weak for untuned small-model selectors: untuned LLM pairwise/multiple-choice selection is around 58-64% pairwise accuracy and MCS/USC tie or trail SC. Gains appear when the extra call is restricted to the top-2 disagreeing clusters (CSC-SQL, DPC) and when it uses new evidence (a distinguishing database or execution of a reference) rather than just re-reading the SQL.

### Cited Findings
- DPC (gated: it only compares the largest vs second-largest execution clusters) with GPT-5 on BIRD Mini-Dev N=5: SC 49.4 → DPC 51.2, while an LLM multiple-choice selector got 50.4; with Qwen2.5-Coder-7B the multiple-choice selector was below SC (43.6 vs 46.4). — [DPC](https://arxiv.org/html/2604.15163v1)
- CSC-SQL: one extra call on the top-2 vote groups helps only with a GRPO-trained merge model; untrained it gives 61.73 vs SC 61.86. — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CHASE-SQL: untuned frontier models as pairwise selectors reach only 60.21 (Claude-3.5-Sonnet) to 63.98 (Gemini-1.5-Pro) binary accuracy; fine-tuning Gemini-1.5-Flash raises it to 71.01. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- USC with gpt-3.5-turbo at N=8 on BIRD: 45.5 vs SC-Exec 45.6. — [USC](https://arxiv.org/html/2311.17311)
- gpt-4o-mini as a YES/NO-logit verifier of gpt-4o-mini's own modal BIRD query: AUROC 0.724 vs 0.675 for string self-consistency; with a gpt-4.1-mini generator the gpt-4o-mini verifier gives 0.677 vs SC 0.641. A stronger verifier (GPT-4o 0.770) adds more. — [arXiv 2607.06799](https://arxiv.org/html/2607.06799v1)
- DPC breakdown shows the cost of overriding the vote: on Majority-Correct questions accuracy falls from 100% to 97.0%, which is why gating matters. — [DPC](https://arxiv.org/html/2604.15163v1)

### Inferences
- Gating on disagreement (no majority, or the top-2 clusters close in size) is supported indirectly: every method with a gain concentrates on the top-2 clusters, and overriding a clear majority costs about 3% of majority-correct questions in DPC.
- A gpt-4o-mini verifier is better than vote share at *detecting* wrong modal answers (0.724 vs 0.675 AUROC), but no paper shows that this turns into a selection gain at N=8. Using it to break ties between the top-2 clusters is untested.
- Using a stronger model only for the gated extra call (e.g. GPT-4o as verifier, AUROC 0.770) would add compute that the baseline does not get, so it must be reported as such.

### Gaps
- No paper found that reports gpt-4o-mini or gpt-3.5 as a gated (disagreement-only) selector on full BIRD dev with selection accuracy numbers.

## Q4. Evidence of majority/self-consistency saturation for text-to-SQL around N=8

### Takeaway
Yes: in CSC-SQL's BIRD dev sweep, SC for 32B-class models gains only about +1 to +1.5 EX from N=8 to N=64, and smaller or RL-trained models also flatten after N=16. CHASE-SQL reports no significant gain beyond ~20 candidates even with its trained selector.

### Cited Findings
- BIRD dev SC (T=0.8): Qwen2.5-Coder-32B 67.56 @8 → 68.54 @16 → 68.67 @64; XiYanSQL-32B 67.50 @8 → 68.95 @64; GRPO XiYanSQL-3B 59.95 @8 → 61.30 @64; Qwen2.5-Coder-7B 62.18 @8 → 63.35 @16 → 64.45 @64. — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CHASE-SQL: going beyond ~20 candidates "did not yield significant improvements"; upper bounds keep rising with more candidates but selection plateaus for moderate/challenging questions. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- SLM-SQL: SC gains on BIRD dev plateau beyond 16 samples (search snippet only). — [ACL Findings IJCNLP 2025](https://aclanthology.org/2025.findings-ijcnlp.92.pdf)
- USC (gpt-3.5, BIRD) increases monotonically to k=8 (42.4 → 45.5); no SC-Exec sweep beyond 8 for SQL. — [USC](https://arxiv.org/html/2311.17311)
- Oracle vs vote gap stays large at small N: USC paper BIRD oracle 53.3 vs SC 45.6 (N=8, gpt-3.5); DPC BIRD Mini-Dev SC selection gap 7.0 to 11.2 points at N=5; CHASE upper bound 82.79 vs SC 68.84. — [USC](https://arxiv.org/html/2311.17311); [DPC](https://arxiv.org/html/2604.15163v1); [CHASE-SQL](https://arxiv.org/html/2410.01943)

### Inferences
- The student's gap (62.0 maj@8 vs the share of questions with at least one correct sample) fits the pattern: selection, not coverage, limits maj@8, and more samples would add roughly +1 EX for the baseline too.

### Gaps
- No saturation curve found specifically for gpt-4o-mini on BIRD dev; the CSC-SQL curves are for open Qwen/XiYan models.
