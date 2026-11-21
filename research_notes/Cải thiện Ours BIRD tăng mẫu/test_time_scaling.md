# Test-time scaling (number of sampled candidates) in LLM text-to-SQL, focus BIRD dev

Scope: how EX accuracy and cost change with the number of candidates k (1/8/16/32/64+), why majority vote saturates while pass@k keeps rising, which methods make extra samples useful again, and reported cost figures. Relevance target: "Ours" on gpt-4o-mini-2024-07-18 (Ours@8 = 63.62, v9 17 candidates = 65.06, baseline Maj-8 = 61.99, Maj-16 ~62.0).

Caveat that applies throughout: most text-to-SQL numbers below come from Qwen2.5-Coder, OmniSQL, XiYan, Gemini 1.5/2.5 Pro or GPT-4o generators. Absolute EX does not transfer to gpt-4o-mini. Only the shapes of the curves (gain per doubling, the pass@k minus vote gap) are reasonably transferable.

## Q1. Which text-to-SQL papers report EX vs number of candidates, with exact numbers (k=1/8/16/32/64) and the pass@k vs vote/selector gap?

### Takeaway
On BIRD dev, majority vote / self-consistency (SC) gains about +1 EX going from 8 to 16 samples and almost nothing after that. For strong 32B models it adds only about +1 to +1.5 EX from 8 to 64 samples. For OmniSQL-7B it is completely flat from 8 to 32 (66.95). Meanwhile pass@N keeps climbing by about +2 to +2.5 EX per doubling (76.1 at 8, 78.5 at 16, 80.6 at 32). So the oracle-minus-vote gap widens from about 9 to about 14 points. Only better selectors (an ORM, a pairwise or merge selector) or more diverse generators turn the extra candidates into real EX.

### Cited Findings

**GradeSQL (arXiv 2509.01308; OmniSQL-7B generator, BIRD dev, Table VI).** EX is listed for majority vote / execution-based BoN / ORM-based BoN / Pass@N:
- N=1: 63.89 for all four.
- N=2: 64.41 / 64.86 / 66.04 / 68.84.
- N=4: 65.32 / 65.32 / 67.34 / 72.82.
- N=8: 66.95 / 65.71 / 68.51 / 76.14.
- N=16: 66.95 / 65.91 / 68.77 / 78.49.
- N=32: 66.95 / 66.04 / 68.90 / 80.57.

Sources: [GradeSQL](https://arxiv.org/html/2509.01308)
- Majority vote is identical at N=8, 16 and 32 (66.95). Pass@N gains +4.43 from 8 to 32. The ORM gains only +0.39 from 8 to 32. — [GradeSQL Table VI](https://arxiv.org/html/2509.01308)
- Gap between Pass@N and majority vote: 9.19 at N=8, 11.54 at N=16, 13.62 at N=32 (computed from Table VI). — [GradeSQL](https://arxiv.org/html/2509.01308)
- Spider dev, same setup: majority vote 83.95 (N=8), 83.66 (N=16), 83.75 (N=32). That is slightly non-monotonic. Pass@N goes 89.65, 90.72, 91.68. — [GradeSQL](https://arxiv.org/html/2509.01308)
- OmniSQL-14B / 32B at N=32 on BIRD dev (Table VII): Maj 67.01 / 63.95 (as reported; the 63.95 for 32B looks anomalous, possibly a table typo), ex-BoN 66.75 / 66.10, ORM 69.04 / 69.30, Pass@32 80.90 / 82.20. — [GradeSQL](https://arxiv.org/html/2509.01308)
- The authors say majority vote and execution-based BoN "quickly saturate, whereas ORM continues to scale." They chose N=32 as "a well-balanced trade-off between performance and computational cost," without giving numbers. — [GradeSQL](https://arxiv.org/html/2509.01308)
- A 2026 follow-up, "Test-Time Verification for Text-to-SQL via Outcome Reward Models" (arXiv 2606.30851, Tritto, Farano, Di Palma, Rossiello, Narducci, Subramanian, Di Noia; same group and repo, sisinflab/GradeSQL), is reported in a search snippet to give "Majority Voting (N=32) 66.95" on BIRD dev. The PDF body could not be extracted, so this is unverified beyond the snippet. — [arXiv 2606.30851](https://arxiv.org/pdf/2606.30851)

**CSC-SQL (arXiv 2505.13271; BIRD dev EX, T=0.8).** SC vs CSC (corrective self-consistency, which merges/fixes the top-2 vote groups) at n = 4 / 8 / 16 / 32 / 64:

| Model | SC: n=4 / 8 / 16 / 32 / 64 | CSC: n=4 / 8 / 16 / 32 / 64 |
|---|---|---|
| Qwen2.5-Coder-7B | 58.34 / 62.18 / 63.35 / 63.80 / 64.45 | 59.63 / 64.28 / 66.41 / 67.54 / 68.70 |
| XiYan-7B-2502 | 59.26 / 62.58 / 63.67 / 64.84 / 66.19 | 61.13 / 65.34 / 66.93 / 68.08 / 69.21 |
| XiYan-32B-2412 | 66.11 / 67.50 / 68.45 / 68.75 / 68.95 | 67.26 / 69.37 / 70.57 / 70.87 / 71.33 |
| Qwen2.5-Coder-32B | 66.97 / 67.56 / 68.54 / 68.58 / 68.67 | 68.02 / 69.12 / 69.95 / 70.32 / 70.69 |
| XiYan-3B-2502 | 49.22 / 54.56 / 56.82 / 58.19 / 58.87 | 51.06 / 57.74 / 61.10 / 63.23 / 64.41 |
| Qwen2.5-Coder-7B + GRPO | 63.73 / 64.95 / 65.58 / 65.88 / 66.15 | 64.91 / 66.96 / 68.30 / 68.61 / 69.19 |

Source: [CSC-SQL](https://arxiv.org/html/2505.13271)

- SC gain from n=8 to 64 (computed): +2.27 (Qwen-7B), +3.61 (XiYan-7B), +1.45 (XiYan-32B), +1.11 (Qwen-32B), +4.31 (XiYan-3B), +1.20 (7B+GRPO). The gain shrinks as the model gets stronger. — [CSC-SQL](https://arxiv.org/html/2505.13271)
- SC gain from 16 to 32 for 32B models: +0.30 (XiYan-32B) and +0.04 (Qwen-32B), i.e. saturated. — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CSC (merge top-2 groups) gains more from extra samples than SC. From 8 to 64: +4.42 (Qwen-7B) and +1.96 (XiYan-32B). — [CSC-SQL](https://arxiv.org/html/2505.13271)
- CSC-SQL defines a "major_top2_pass@k" metric: pass@k computed over only the two top-voted groups. Exact values are shown only in Figure 1. — [CSC-SQL](https://arxiv.org/html/2505.13271)

**CHASE-SQL (arXiv 2410.01943; Gemini 1.5 Pro generators, BIRD dev).**
- Single query 63.01. Self-consistency 68.84. Oracle upper bound of the combined 21-candidate pool 82.79. Final selection agent 73.01 (test 73.0). — [CHASE-SQL Tables 1, 2, 7](https://arxiv.org/html/2410.01943)
- Gap between oracle and SC = 13.95. Gap between oracle and selector = 9.78. The selector beats SC by +4.17 (Table 7 ablation). — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- The pool is 7 candidates × 3 generators = 21. Fig. 2(d) shows the pool size "beyond 20 did not yield significant improvements." Exact curve values are only in the figure. — [CHASE-SQL Sec. 4.4](https://arxiv.org/html/2410.01943)
- Per-generator results with 10 samples (Table 6), as lower bound / upper bound / SC / selection agent:
  - QP T=0.5: 50.46 / 78.55 / 65.78 / 71.7
  - QP T=1.8: 48.63 / 80.44 / 65.51 / 71.73
  - DC T=0.5: 51.37 / 78.42 / 66.43 / 71.31
  - DC T=1.8: 47.39 / 79.34 / 64.41 / 70.53
  - OS T=0.5: 60.43 / 74.77 / 67.34 / 70.4
  - OS T=1.8: 50.98 / 79.66 / 66.88 / 71.38

  Higher temperature raises the upper bound but not SC. — [CHASE-SQL Table 6](https://arxiv.org/html/2410.01943)

**Agentar-Scale-SQL (arXiv 2509.24403v6).**
- Pass@k rises from 1 to 16 candidates at every difficulty level, with the largest gains on challenging questions. Gains are "most substantial when increasing the candidates up to 8, after which the gains diminish" (Fig. 6; exact values only in the figure). — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- The final pool is 17 candidates: 9 from an ICL generator (Gemini-2.5-Pro at T=0.5 and 1.8, plus GPT-5 at minimal reasoning) and 8 from a reasoning generator fine-tuned from OmniSQL-32B. — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- Upper bounds: ICL generator 81.36, reasoning generator 75.88, combined 84.29.
- Dev EX: 74.90 with the RL-trained tournament selector (Qwen2.5-Coder-32B base) vs 73.08 with SC (−1.82). Test EX 81.67. — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- The authors note "the most frequently executed result is not necessarily correct." — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403)

**OmniSQL (arXiv 2503.02240), BIRD dev, greedy vs majority vote (8 samples at T=0.8, vote over execution-result groups):**

| Model | Greedy | Maj | Gain |
|---|---|---|---|
| GPT-4o-mini | 58.8 | 61.5 | +2.7 |
| GPT-4o | 61.9 | 64.0 | +2.1 |
| OmniSQL-7B | 63.9 | 66.1 | +2.2 |
| OmniSQL-14B | 64.2 | 65.9 | +1.7 |
| OmniSQL-32B | 64.5 | 67.0 | +2.5 |

Source: [OmniSQL Table 4 / Sec. 6.1.6](https://arxiv.org/html/2503.02240)

- The paper reports no maj@k or pass@k curves. — [OmniSQL](https://arxiv.org/html/2503.02240)
- **Conflict to check:** the fetched paper version shows GPT-4o-mini Maj = 61.5. The thesis context cites 61.99. That could be a different arXiv version or the user's own rerun ("rerun 58.9/62.0" in project memory). This needs checking before citing either number in the thesis.

**XiYan-SQL (arXiv 2411.08599; ICL generator GPT-4o plus fine-tuned generators).**
- BIRD dev 71.58 with 3 candidates (the text says 71.51, which conflicts) and 73.34 with 5 candidates (+1.76). Removing the selection model costs −2.74. — [XiYan-SQL Table 8](https://arxiv.org/html/2411.08599)
- No upper bound or k-curve is reported. The paper stresses that it uses 5 candidates vs CHASE-SQL's 21 to limit cost. — [XiYan-SQL](https://arxiv.org/html/2411.08599)

**Alpha-SQL (arXiv 2502.17248; MCTS, zero-shot, Qwen2.5-Coder).**
- BIRD dev 66.8 (7B), 68.7 (14B), 69.7 (32B) with N_rollout = 24.
- Selection picks the candidate with the highest execution-result consistency (SC-like).
- Upper bound and final EX are both "positively correlated" with rollouts, but numbers appear only in Fig. 5.

Source: [Alpha-SQL](https://arxiv.org/html/2502.17248)

**Contextual-SQL (Contextual AI blog, not peer reviewed).**
- Generates 1,024 candidates (32 samples × 32 few-shot variants, T=1) for its pass@k study on Gemini-1.5-Flash.
- A Qwen-2.5-32B reward model trained on BIRD train reached about 70 EX alone. Combined with log-probs (α = 0.4) the system reached "around 73%" on BIRD dev.
- Reward-based selection beats majority vote "dramatically." Exact per-k values are only in charts.

Source: [Contextual AI blog](https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system)

**CA-SQL (arXiv 2605.08057, Petullo & Xue; GPT-4o-mini).**
- Complexity-aware exploration budget plus voting: BIRD dev 61.06 EX overall, 51.72 on the challenging tier.
- Its curves of accuracy vs budget were not visible in the abstract.
- This is the closest same-model reference point. Ours@8 (63.62) is above it.

Source: [CA-SQL abstract](https://arxiv.org/abs/2605.08057)

### Inferences
- The user's observation (gpt-4o-mini baseline Maj-8 ≈ 62.0, Maj-16 ≈ 62.0) matches the literature pattern exactly. With a single prompt, vote accuracy is essentially converged by k = 8–16. Expected Maj-32 / Maj-64 for gpt-4o-mini is roughly 62–63.5. This is extrapolated from CSC-SQL's +1.1 to +3.6 for 8→64 and GradeSQL's +0.0 for 8→32. No paper reports gpt-4o-mini at k ≥ 16.
- Pass@k should keep growing by about +2 points per doubling (GradeSQL: +2.35 for 8→16, +2.08 for 16→32), so the oracle headroom of Ours will keep growing with more samples. The binding constraint is selection, not generation.
- CHASE-SQL (Table 6) shows that one generator with 10 samples already has an oracle of about 75–80. Combining 3 diverse generators reaches 82.79 with 21 candidates, more than any single generator. Diversity across prompts buys more oracle headroom than more samples from the same prompt.

### Gaps
- No paper found reports gpt-4o-mini BIRD dev EX at k = 16/32/64 with majority vote or a selector.
- Exact curve values for CHASE-SQL Fig. 2, Agentar-Scale-SQL Fig. 6, Alpha-SQL Fig. 5 and the CSC-SQL Fig. 1 pass@k are only in figures and were not extracted.
- The OpenSearch-SQL, MCTS-SQL and ReFoRCE scaling numbers were not checked in this pass (tool budget).

## Q2. What is known about majority-vote saturation vs pass@k growth in the general LLM literature, and what is the mechanism?

### Takeaway
Coverage (pass@k) keeps growing roughly log-linearly with samples over orders of magnitude. Majority vote and reward-model selection plateau, and can even go down. The vote converges to the mode of the model's answer distribution for each question. Once k is large enough to estimate that mode reliably, more samples cannot change the answer. Questions where the correct answer is not the mode are permanently lost to voting, even though pass@k "solves" them.

### Cited Findings
- **Large Language Monkeys (Brown et al., arXiv 2407.21787).**
  - Coverage "scales with the number of samples over four orders of magnitude," often log-linearly, modeled by an exponentiated power law.
  - SWE-bench Lite with DeepSeek-Coder-V2-Instruct goes from 15.9% (1 sample) to 56% (250 samples), against a 43% single-sample SOTA.
  - Without an automatic verifier, majority vote and reward models "plateau beyond several hundred samples."
  - Source: [arXiv 2407.21787](https://arxiv.org/abs/2407.21787)
- **"Are More LLM Calls All You Need?" (Chen et al., arXiv 2403.02419).**
  - Vote and Filter-Vote performance "can first increase but then decrease" as calls grow.
  - The theory: more calls help on "easy" queries and hurt on "hard" queries, so a mix of the two gives non-monotonic scaling.
  - An analytical scaling model fitted on a few samples predicts the optimal number of calls.
  - Source: [arXiv 2403.02419](https://arxiv.org/abs/2403.02419)
- **Inference scaling flaws (Stroebl et al., arXiv 2411.17501).**
  - With an imperfect verifier (non-zero false-positive rate), resampling has a hard accuracy ceiling.
  - The optimal number of attempts is "often fewer than 10," and the curves bend downward beyond that.
  - Weaker models cannot match a strong model's single-sample accuracy by resampling (HumanEval/MBPP).
  - Source: [arXiv 2411.17501](https://arxiv.org/abs/2411.17501)
  - This is relevant because execution checks in text-to-SQL ("runs without error, non-empty result") are verifiers with a high false-positive rate.
- **Snell et al. (arXiv 2408.03314).**
  - A difficulty-adaptive, compute-optimal allocation improves test-time scaling efficiency by more than 4x over best-of-N.
  - Effectiveness "critically varies depending on the difficulty of the prompt."
  - FLOPs-matched, test-time compute can beat a 14x larger model, but only where the small model already has non-trivial success.
  - Source: [arXiv 2408.03314](https://arxiv.org/abs/2408.03314)
- **Text-to-SQL confirmation.** GradeSQL's majority vote is flat at 66.95 for N=8/16/32 while Pass@N rises 76.14 → 80.57. Spider dev majority vote is slightly non-monotonic (83.95 → 83.66 → 83.75). — [GradeSQL](https://arxiv.org/html/2509.01308)
- **Self-consistency (Wang et al., ICLR 2023, arXiv 2203.11171)** introduced sample-and-majority-vote over reasoning paths.
  - UNVERIFIED in this pass, from background knowledge: gains in that paper's figures mostly saturate by about 20–40 sampled paths. The paper's main experiments use 40 paths.
  - Source: [arXiv 2203.11171](https://arxiv.org/abs/2203.11171)

### Inferences
- The mechanism in formal terms: for question q, let p_q(a) be the model's distribution over execution-result groups. Majority vote with k samples returns argmax_a p̂_q(a), which converges to the mode as k grows.
  - EX(maj@∞) = fraction of questions whose mode is correct.
  - pass@k → fraction of questions where the correct answer has any probability mass, so pass@k ≥ EX(maj@k) and the gap grows with k.
  - Questions with p_q(correct) slightly below p_q(wrong mode) get *worse* with more votes (Chen et al.'s "hard" queries). Questions with p_q(correct) as a narrow plurality get better. The net effect saturates.
- For the user's system, this means adding more base-prompt T=0.8 samples mostly sharpens the estimate of the same mode. Ours already beats Maj-8 by using a second prompt (plan) plus repair plus a selector, which changes the distribution rather than estimating it better.

### Gaps
- The exact numeric curves in Chen et al. and Wang et al. were not extracted, only the abstract claims.

## Q3. Which methods make more samples useful again (diversity, selectors/verifiers, adaptive sampling/early stopping)?

### Takeaway
Three levers work:
1. **Diversity across generators/prompts.** This raises the oracle more than more samples from one prompt (CHASE-SQL 82.79 combined vs 74.8–80.4 for a single generator; Agentar 84.29 combined vs 81.36 / 75.88).
2. **Learned or pairwise selectors, ORMs, or merge-correct steps.** These beat SC by +1.8 to +4.2 EX and keep scaling slowly where SC is flat.
3. **Adaptive sampling / early stopping.** This mostly cuts cost by 2–8x at near-equal accuracy, rather than raising accuracy.

### Cited Findings
- **Diversity.**
  - CHASE-SQL: removing a generator costs −1.24 (DC), −0.85 (OS) and −0.65 (QP). The combined 21-candidate oracle is 82.79 vs per-generator oracles of 74.77–80.44 with 10 samples each. — [CHASE-SQL Tables 6–7](https://arxiv.org/html/2410.01943)
  - Agentar-Scale-SQL: removing the reasoning generator costs −4.89 and removing the ICL generator −3.78. The ICL and reasoning generators contribute 47 and 12 uniquely-correct questions respectively. — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
  - XiYan-SQL: removing the fine-tuned generator costs −2.91 and the ICL generator −1.31. Going from 3 to 5 candidates adds +1.76. — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- **Selectors / verifiers.**
  - CHASE-SQL pairwise selector (fine-tuned Gemini-1.5-Flash): 73.01 vs SC 68.84 (+4.17). A ranker agent scores only 65.51. — [CHASE-SQL Table 7](https://arxiv.org/html/2410.01943)
  - Pairwise binary accuracy on pairs where exactly one candidate is correct:
    - Claude-3.5-Sonnet untuned 60.21
    - Gemini-1.5-Pro untuned 63.98 (the text says 58.01, which conflicts)
    - tuned Gemma-2-9B 64.28
    - tuned Gemini-1.5-Flash 71.01

    Source: [CHASE-SQL Table 5](https://arxiv.org/html/2410.01943)
  - Untuned frontier LLMs as pairwise judges are only about 60–64% accurate. That limits a prompt-only LLM selector like the one in Ours.
  - Agentar RL-trained tournament selector: +1.82 over SC (74.90 vs 73.08). — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
  - GradeSQL ORM (OmniSQL-7B generator): 68.51 / 68.77 / 68.90 at N=8/16/32 vs majority vote 66.95 flat. The ORM keeps scaling, but slowly (+0.39 from 8 to 32). — [GradeSQL](https://arxiv.org/html/2509.01308)
  - CSC-SQL merge of the top-2 groups: +2.1 to +4.4 over SC at n=64. Its gain from 8 to 64 is about double SC's for 7B models. — [CSC-SQL](https://arxiv.org/html/2505.13271)
  - Contextual-SQL reward model plus log-prob scoring: about 73 on BIRD dev using up to 1,024 candidates. — [Contextual AI](https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system)
- **Adaptive sampling / early stopping.**
  - Adaptive-Consistency (EMNLP 2023): up to 7.9x fewer samples than SC with less than 0.1% average accuracy drop, across 17 reasoning and code datasets and 3 LLMs. — [arXiv 2305.11860](https://arxiv.org/abs/2305.11860)
  - Early-Stopping Self-Consistency (ICLR 2024): sample cuts of −33.8% (MATH), −80.1% (GSM8K), −76.8% (StrategyQA), −78.5% (CSQA), −84.2% (Coin Flip) and −67.4% (Last Letters), with "comparable" accuracy. — [arXiv 2401.10480](https://arxiv.org/abs/2401.10480)
  - Snell et al.: difficulty-adaptive allocation is more than 4x more compute-efficient than best-of-N. — [arXiv 2408.03314](https://arxiv.org/abs/2408.03314)
  - CA-SQL applies complexity-aware budget allocation to text-to-SQL with GPT-4o-mini, reaching 61.06 overall and 51.72 on the challenging tier on BIRD dev. — [arXiv 2605.08057](https://arxiv.org/abs/2605.08057)

### Inferences
- For Ours, the best levers in expected order are:
  1. **Spend samples only where the vote is uncertain** (early stop when the first 4–8 agree). Most BIRD questions are "easy" for voting, so cost can drop with almost no EX loss.
  2. **Add a third, different generator or prompt** (e.g., divide-and-conquer or online few-shot in CHASE-SQL style) rather than raising k for the base prompt.
  3. **Improve the selector for no-majority cases.** A CSC-style top-2 merge or pairwise comparison is cheap. A trained ORM would need training, which conflicts with "training-free".
- Ours v9 (17 candidates, 65.06) vs Ours@8 (63.62) gives +1.44 for about 2x candidates. That is larger than single-prompt SC's +0 to +1.2 for 8→16, consistent with the diversity/selector effect.

### Gaps
- No text-to-SQL paper found applies Adaptive-Consistency or ESC early stopping to BIRD with exact sample savings. The CA-SQL full text, which may contain this, was not read.

## Q4. Reported cost / tokens / latency per question and cost-accuracy trade-off statements

### Takeaway
Few papers report dollars. CSC-SQL is the clearest: n=64 sampling on a 32B open model costs about $6.56 for all of BIRD dev ($0.0043/question) for +1.45 EX over n=8. Agentar-Scale-SQL reports 20–630 LLM calls per question vs 297 for CHASE-SQL and 2,048 for Contextual-SQL. For the user's gpt-4o-mini setup, linear extrapolation gives roughly $4.5 (Maj-16), $9 (Maj-32) and $18 (Maj-64) for the whole dev set, for an expected EX gain of only about 0–1.5 over Maj-8.

### Cited Findings
- **CSC-SQL Table 7 (BIRD dev, 1,534 questions, H800 at about $2/hour):**
  - Qwen2.5-Coder-7B GRPO, n=4: 0.16 h, $0.32 ($0.00022/question), EX 64.91.
  - Same model, n=64: 1.08 h, $2.16 ($0.0014/question), EX 69.19.
  - XiYan-32B, n=16: 1.07 h, $2.14, EX 70.57.
  - XiYan-32B, n=64: 3.28 h, $6.56 ($0.0043/question), EX 71.33.
  - The CSC merge step adds only 3–11% time.
  - Source: [CSC-SQL](https://arxiv.org/html/2505.13271)
  - Implication: going from 16 to 64 samples on XiYan-32B is about 3.1x the cost for +0.76 EX.
- **Agentar-Scale-SQL Table 5, LLM calls per question:**
  - Agentar 20–630 in total: understanding 1, generation 17, refinement 1–51, selection 1–561.
  - CHASE-SQL + Gemini 297; Contextual-SQL 2,048; Sophon-Text2SQL-32B 8–32; Databricks RLVR 32B 1–7; Gemini-SQL 1–7.
  - The paper says "a latency of 10–30 seconds is often tolerable for complex analytics."
  - Source: [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- CHASE-SQL gives no dollar or latency numbers. It only says the Gemini-1.5-Flash selector has "much less latency" than Pro. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL motivates using 5 candidates (vs 21) by the "significant inference overheads" of multi-path SC, without numbers. — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- GradeSQL picks N=32 as a cost/performance trade-off, without numbers. — [GradeSQL](https://arxiv.org/html/2509.01308)
- Contextual-SQL calls candidate generation "computationally expensive," without numbers. — [Contextual AI](https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system)
- Large Language Monkeys argues that repeated sampling of cheaper models can be cost-effective where coverage converts to accuracy (with verifiers). Its exact cost comparison was not in the fetched abstract. — [arXiv 2407.21787](https://arxiv.org/abs/2407.21787)

### Inferences
- **Cost extrapolation for the user's numbers** (one extra gpt-4o-mini sample ≈ $0.24–0.30 for all 1,534 questions; Maj-8 ≈ $2.3):

  | Setting | Estimated cost | Expected EX |
  |---|---|---|
  | Maj-16 | ≈ $4.2–4.7 | ~62.0 (observed) |
  | Maj-32 | ≈ $8–9.5 | ~62–63 (extrapolated) |
  | Maj-64 | ≈ $17–19.5 | ~62.5–63.5 (extrapolated) |
  | v9 (17 candidates) | ≈ $6.5 | 65.06 (measured) |

  v9 at about $6.5 already beats the extrapolated Maj-64 (about 3x the cost). Cost per extra EX point is far better for diversity plus selection than for more base samples.
- **Possible cost lever, not verified here.** If generation uses the OpenAI `n` parameter in one request, input tokens are billed once and only output tokens scale with n. Automatic prompt caching may also discount repeated long schema prompts. Both would make extra samples cheaper than linear. Check this against the user's billing logs before relying on it.
- **Thesis framing.** Moving from a "more samples" curve to a "cost vs EX" Pareto curve (Maj-k for k = 1, 4, 8, 16 vs Ours@8 vs v9) would match how CSC-SQL and Agentar present trade-offs. Literature saturation (GradeSQL, CSC-SQL) can justify not running Maj-32/64 in full.

### Gaps
- No paper found reports token counts or dollar cost for gpt-4o-mini sampling on BIRD.
- Wall-clock latency per question is not measured in CHASE-SQL, XiYan-SQL, Alpha-SQL, GradeSQL or Agentar-Scale-SQL.
- gpt-4o-mini pricing and `n`-parameter billing were not re-verified in this pass.
