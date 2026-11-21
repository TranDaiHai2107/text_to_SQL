# Training-free single-pass techniques to raise per-sample SQL accuracy of small proprietary LLMs on BIRD dev (gpt-4o-mini focus, fixed N=8)

Scope note: every number is BIRD dev execution accuracy (EX, %) unless marked [Spider] or [Mini-Dev] / [subsampled dev]. "FT" marks a fine-tuned component. Reference point for judging relevance: the thesis baseline (OmniSQL-style prompt, gpt-4o-mini-2024-07-18) is around 59-60 EX single-sample, which is already above most published gpt-4o-mini "basic prompt" baselines (45.7 to 57.7, see below). So gains reported against weak baselines will probably shrink a lot here.

## Q1. Schema linking / pruning / filtering for gpt-4o-mini-class models: helps or hurts?

### Takeaway
On BIRD-sized schemas, explicit schema filtering *hurt* gpt-4o-mini when it was added on top of a strong pipeline (E-SQL: -5.5 to -8.2 EX). It helps only against weak full-schema zero-shot baselines (+5.4 for gpt-4o-mini at 45.7 -> 51.1), and that is still below the thesis baseline. The useful part of the "schema linking" papers is the *augmentation* (adding hints/columns/values), not the removal of columns.

### Cited Findings
- E-SQL, gpt-4o-mini, simple pipeline (Table 4): basic generation G = 57.69; with question enrichment QE-G = 58.80; with schema filtering SF-G = 49.48 (-8.21); SF-QE-G = 55.34. Full E-SQL (gpt-4o-mini) = 61.60; adding SF to full E-SQL gives 56.06 (-5.54). The authors say explicit schema filtering "can be redundant" with recent LLMs. — [E-SQL, Caferoğlu & Ulusoy 2024](https://arxiv.org/html/2409.16751)
- "The Death of Schema Linking?" (Maamari et al. 2024), ablation (Table 2): with ft:GPT-4o, using column-selection schema linking (SCSL) in place of the full schema gives 55.78 vs 67.35 full pipeline (-11.57); TCSL -4.77. Gemini 1.5 Pro: SCSL -5.44, TCSL -4.76. Llama-3.1-405B: SCSL -4.76, TCSL -2.72. Their full pipeline = full schema + augmentation + selection + correction. Linking recall: TCSL 77.44%, SCSL 88.77%, HySCSL 90.36% (so 10-23% of queries lose a needed column). Conclusion: for strong models, if the schema fits the context, schema linking is not needed; it can still help smaller/older models (e.g., Llama-3.1-8B). No gpt-4o-mini numbers. — [Maamari et al. 2024](https://arxiv.org/html/2408.07702)
- Same paper, "base model, full schema, no pipeline": ft:GPT-4o 59.18, Gemini 1.5 Pro 57.82, Llama-3.1-405B 53.74. Removing correction: -1.36 / -3.40 / -3.40. Removing augmentation: -2.72 / 0 / +0.68. — [Maamari et al. 2024](https://arxiv.org/html/2408.07702)
- "Rethinking Schema Linking" (context-aware bidirectional retrieval, 2025), single-response zero-shot, no fixing or self-consistency: gpt-4o-mini full schema 45.70 -> retrieved schema 51.11 (+5.41) -> gold schema 56.84. Gemini-2.0-flash 52.09 -> 57.86; DeepSeek 53.80 -> 56.80; Qwen2.5-7B 37.13 -> 40.16. Linking recall for gpt-4o-mini = 90.60%, FPR 25.29%. Plug-in: DIN-SQL 50.6 -> 55.4. — [Rethinking Schema Linking, arXiv 2510.14296](https://arxiv.org/html/2510.14296)
- RSL-SQL, cumulative ablation (Table IV): GPT-4o base prompt 48.70 -> +few-shot 58.67 (+9.97) -> +data samples 62.06 (+3.39) -> +bidirectional schema linking 62.71 (+0.65) -> +contextual info augmentation 65.06 (+2.35) -> +binary selection 66.43 -> +multi-turn self-correction 67.21 (+0.78). DeepSeek: 42.96 -> 55.48 -> 57.63 -> 58.80 (+1.17) -> 61.67 -> 63.30 -> 63.56. Linking strict recall 94.32% (GPT-4o), with about 13 columns kept per question vs 76 in full schema. No gpt-4o-mini results. — [RSL-SQL, Cao et al. 2024](https://arxiv.org/html/2411.00073)
- RSL-SQL "contextual information augmentation" (Table VI, GPT-4o): removing column descriptions 65.06 -> 63.89; removing generated SQL components (elements/keywords/conditions hints) -> 63.95; both -> 62.26. — [RSL-SQL](https://arxiv.org/html/2411.00073)
- CHESS: on small schemas, with capable LLMs, schema selection can lower accuracy because of the precision-recall trade-off. It helps on very large schemas (about 2 points on a 4,337-column schema). Column recall falls from 1.0 to 0.94 after select_columns. — [CHESS, Talaei et al. 2024](https://arxiv.org/html/2405.16755)
- MAC-SQL + GPT-4: without the Selector (schema pruning) 57.28 vs 59.39 full (-2.11). — [MAC-SQL, Wang et al. 2023](https://arxiv.org/html/2312.11242)
- TA-SQL + GPT-4: without task-aligned schema linking 49.77 vs 56.19 (-6.42). Plain GPT-4 with evidence = 46.35 (a weak baseline). ChatGPT (gpt-3.5): 37.22 -> 43.74 with TA-SQL. — [TA-SQL, Qu et al. 2024](https://arxiv.org/html/2405.15307)
- OpenSearch-SQL [Mini-Dev, GPT-4o]: without column filtering, single-generation EX_G 65.8 -> 63.2 (-2.6) and final 70.6 -> 68.6. Note: its filtering keeps question-relevant columns *plus* the full schema context, which differs from hard pruning. — [OpenSearch-SQL, Xie et al. 2025](https://arxiv.org/html/2502.14913)

### Inferences
- The only gpt-4o-mini measurement on a strong pipeline (E-SQL) shows hard filtering hurting. Gains in TA-SQL, MAC-SQL and Rethinking-Schema-Linking are measured against baselines (37 to 51 EX) far below the thesis's 59-60. Recommendation: do not prune. Use linking only as a *soft hint*, for example a "likely relevant columns" list placed above the full DDL, which matches the RSL-SQL "augmentation" gain (+2.35 GPT-4o).
- The 49 "no such column" errors are the class most likely to benefit from a soft-linking hint or execution repair, not from pruning (pruning raises missing-column risk by 6-23% of queries).

### Gaps
- No paper found gives a gpt-4o-mini ablation of *soft* schema hints vs. full schema on a baseline already near 60.
- Per-model EX curves in Maamari et al. are only in figures (Fig. 3, Fig. 5), not text.

## Q2. Output-format alignment (column order / extra columns, BIRD conventions)

### Takeaway
Alignment post-steps give measured but modest gains (about 1-3 EX) on GPT-4o. The largest single piece is "Info/SELECT alignment", which matches SELECT items to the question and directly targets the thesis's 145 wrong-column-count errors. No paper isolates gains for individual BIRD conventions (CAST AS REAL, IS NOT NULL, LIMIT 1 vs ties) with numbers.

### Cited Findings
- OpenSearch-SQL ablation [Mini-Dev, GPT-4o generation, bge-large retrieval]: without Info Alignment (SELECT alignment: matching the number and order of SELECT items to the question's phrases), EX_G 65.8 -> 62.8 (-3.0 single-sample) and final 70.6 -> 68.6 (-2.0). Removing all post-generation alignments (Agent + Function + Style together) gives EX_R 68.2 -> 67.0 (-1.2) and final -1.0. The three are not ablated separately. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- OpenSearch-SQL rule examples. Style Alignment adds `IS NOT NULL` before `ORDER BY ... LIMIT 1` and chooses between MAX and ORDER BY LIMIT 1. Function Alignment rewrites `ORDER BY MAX(score)` into GROUP BY + ORDER BY. Agent Alignment fixes literal case to match stored values ('John' -> 'JOHN'). The paper gives no full rule set. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- OpenSearch-SQL full dev: 67.8 single generation without self-consistency; 69.3 with Consistency & Vote. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- TA-SQL hallucination taxonomy (shares of errors, GPT-4): Attribute Overanalysis (extra or wrong attributes) 49%, Schema Contradiction 30%, Value Misrepresentation 24%, Clause Abuse 25%, Join Redundancy 15%, Mathematical Delusion 17%. The categories overlap, and the paper gives no per-category fix rates in text. — [TA-SQL](https://arxiv.org/html/2405.15307)
- RSL-SQL SQL-component hints [subsampled dev, Table VII, GPT-4o]: simplified schema + elements/keywords/conditions hints 62.59; without the elements hint 59.86; without the keywords hint 61.90; without the conditions hint 61.22; without all three 60.54. — [RSL-SQL](https://arxiv.org/html/2411.00073)
- MAC-SQL error analysis: 30% of BIRD errors are "Gold Error" and 14% are "Semantic Correct", so a sizable share of the "wrong" set cannot be fixed by format rules. — [MAC-SQL](https://arxiv.org/html/2312.11242)

### Inferences
- For the 145 wrong-column-count cases, a SELECT-alignment step is the best-supported option (OpenSearch: about +3 single-sample on GPT-4o [Mini-Dev]). It can run as a deterministic or LLM rewrite of each of the 8 samples before voting. It also tends to make samples agree with each other more, which helps the vote.
- The 104 row-count errors (DISTINCT/LIMIT/GROUP BY) line up with Style/Function Alignment. Its measured combined effect is small (about 1 EX). Expect around +0.5-1.
- BIRD conventions such as CAST AS REAL and NULL filtering are best put in few-shot examples (BM25 from train already does this implicitly) rather than as rules. This is inference; I found no isolated measurement.

### Gaps
- No paper reports gpt-4o-mini numbers for alignment agents, and none isolates individual rules (CAST AS REAL, DISTINCT, tie handling).

## Q3. Value retrieval (LSH, embedding, entity retrieval)

### Takeaway
Value retrieval is consistently worth about 1.4-3 EX on GPT-4o / Gemini pipelines. Since the thesis already has question-matched values plus explicit stored-value hints, extra headroom is probably small. The remaining lever is literal-case/format alignment against stored values.

### Cited Findings
- CHASE-SQL (Gemini 1.5 Pro, full system 73.01): without LSH value retrieval 70.09 (-2.92). — [CHASE-SQL, Pourreza et al. 2024](https://arxiv.org/html/2410.01943)
- OpenSearch-SQL [Mini-Dev, GPT-4o]: without values retrieval, EX_G 65.8 -> 64.4 (-1.4) and final -1.4. Without Extraction (entity/keyword extraction that drives retrieval and column filtering), EX_G 65.8 -> 61.6 (-4.2). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- CHESS [subsampled dev, 147 Q, GPT-3.5/FT-DeepSeek/GPT-4-turbo]: without retrieve_entity and retrieve_context (LSH values + description retrieval), 64.62 -> 59.86 (-4.76). The baseline used a random example and all column descriptions. — [CHESS](https://arxiv.org/html/2405.16755)
- E-SQL "candidate predicate generation" (executing LIKE-based candidate predicates to find stored values), gpt-4o-mini: without CPG 61.60 -> 59.58 (-2.02); without QE & CPG -3.26. — [E-SQL](https://arxiv.org/html/2409.16751)

### Inferences
- E-SQL's CPG is the only value-grounding ablation run on gpt-4o-mini (+2.0). It works by *executing* partial predicates to confirm values exist. The thesis's "stored-value hints" probably capture part of this, and the 236 "right shape, wrong values" errors may still contain literal mismatches that CPG-style probing catches.

### Gaps
- No head-to-head LSH vs embedding vs BM25 value retrieval on gpt-4o-mini was found.

## Q4. Few-shot selection quality (DAIL masked similarity, skeleton similarity, number of shots, online synthetic examples)

### Takeaway
Few-shot is the largest single per-sample lever in every ablation (+5 to +12 EX vs zero-shot on GPT-4o / DeepSeek). Better selection (masked question or skeleton similarity) beats raw question similarity by about 1.5-3 EX [Spider, gpt-3.5/4]. CHASE-SQL's online synthetic examples give the best single-candidate generator (+9.3 over baseline on Gemini 1.5 Pro). The thesis's BM25 few-shot (+1.6 at maj@8) is probably below what masked/skeleton selection or synthetic examples could give.

### Cited Findings
- DAIL-SQL [Spider dev], GPT-3.5-turbo 3-shot EX: random 73.6, question similarity 74.7, masked question similarity 77.3, DAIL selection (masked question + skeleton) 77.8. GPT-4 3-shot: 79.4 / 79.2 / 81.5 / 81.7. Shot count (DAIL selection, EX) for GPT-3.5: 0-shot 74.4 -> 1-shot 75.5 -> 3-shot 77.8 -> 5-shot 78.1. GPT-4: 72.3 -> 80.2 -> 81.7 -> 82.4. — [DAIL-SQL, Gao et al. 2023](https://arxiv.org/html/2308.15363)
- DAIL-SQL + GPT-4 on BIRD dev = 54.76 (reported in other papers' baseline tables). — [RSL-SQL Table I](https://arxiv.org/html/2411.00073)
- RSL-SQL: adding few-shot examples raises GPT-4o 48.70 -> 58.67 (+9.97) and DeepSeek 42.96 -> 55.48 (+12.52). — [RSL-SQL](https://arxiv.org/html/2411.00073)
- OpenSearch-SQL [Mini-Dev, GPT-4o]: removing few-shot from generation gives EX_G 65.8 -> 60.4 (-5.4). Query-CoT-SQL examples (with reasoning) 70.6 vs plain Query-SQL pairs 69.2 (-1.4). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- CHASE-SQL single-candidate (Gemini 1.5 Pro): baseline 57.75; online synthetic examples 67.09 (+9.34); query-plan CoT 63.62; divide-and-conquer CoT 63.92. Synthetic example mix: common-SQL-feature examples alone 65.45; filtered-schema examples alone 66.75; mixed 67.09 (75 examples per set). — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Solid-SQL [Spider dev, gpt-4o-mini]: DAIL-SQL 77.4, MAC-SQL 78.1, DIN-SQL 70.3, Solid-SQL (structural-similarity example retrieval + FT Llama3-8B schema linker) round 1 80.4, round 2 79.9. Shot count peaked at 7 [Spider variants]. BIRD dev reported only with GPT-4: 58.9. The schema linker is fine-tuned. — [Solid-SQL, COLING 2025](https://arxiv.org/html/2412.12522v1)
- E-SQL uses 9 shots per module (3 per difficulty) and does not ablate shot count. — [E-SQL](https://arxiv.org/html/2409.16751)

### Inferences
- Concrete upgrade paths with evidence: (a) mask schema/value tokens in the question before BM25/embedding retrieval (DAIL); (b) re-rank by SQL skeleton similarity to a draft SQL (DAIL/Solid-SQL two-round); (c) CHASE-style online synthetic examples built from *this* DB's schema (largest single-candidate gain, measured on Gemini). (c) also produces samples that are more diverse across the 8 slots if the example sets vary per sample.
- Using Query-CoT-SQL examples instead of Query-SQL is a cheap +1.4 [Mini-Dev, GPT-4o].

### Gaps
- No BIRD dev measurement of masked vs unmasked selection for gpt-4o-mini or gpt-3.5 was found. CHASE-SQL synthetic examples were not tested on GPT models.

## Q5. Question rewriting/decomposition, evidence handling, CoT formats

### Takeaway
Question enrichment that weaves in schema items and evidence gave gpt-4o-mini +1.1 (simple pipeline) to +1.9 (full E-SQL). Divide-and-conquer and query-plan CoT gave about +6 single-candidate on Gemini, but the thesis's 6-step query-plan prompt did not help on gpt-4o-mini, consistent with E-SQL-style gains being small at this baseline. BIRD evidence is noisy (6.84% wrong, 9.65% missing), but SEED's generated evidence does *not* beat the gold BIRD evidence for GPT models.

### Cited Findings
- E-SQL question enrichment (QE), gpt-4o-mini: simple G 57.69 -> QE-G 58.80 (+1.11); full E-SQL without QE 59.71 vs 61.60 (-1.89). For tiny open models, enriched questions (generated by the pipeline) lift DeepSeek-Coder-1.3B 20.92 -> 50.84 and Qwen2.5-Coder-7B 31.25 -> 40.22. — [E-SQL](https://arxiv.org/html/2409.16751)
- CHASE-SQL single-candidate (Gemini 1.5 Pro): divide-and-conquer CoT 63.92, query-plan CoT 63.62 vs baseline (BIRD prompt + zero-shot CoT) 57.75. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- OpenSearch-SQL [Mini-Dev, GPT-4o]: without CoT, EX_G 65.8 -> 63.0 (-2.8). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- TA-SQL + GPT-4: without logical synthesis (pandas-like logic-first step) 52.41 vs 56.19 (-3.78). — [TA-SQL](https://arxiv.org/html/2405.15307)
- MAC-SQL + GPT-4: without Decomposer 55.54 vs 59.39 (-3.85). — [MAC-SQL](https://arxiv.org/html/2312.11242)
- SEED (2025) evidence audit of BIRD dev (1,534 pairs): 148 (9.65%) without evidence; 105 (6.84%) with incorrect evidence (wrong calculations, typos, case errors, bad date formats, wrong schema/value mappings, wrong comparison operators). — [SEED, arXiv 2506.07423](https://arxiv.org/html/2506.07423)
- SEED Table IV: CHESS (IR+CG+UT, gpt-4o-mini) no evidence 54.69, BIRD evidence 63.04, SEED-generated evidence 56.26. RSL-SQL (GPT-4o): 54.50 / 65.78 / 58.28. Generated evidence beats no-evidence but stays well below gold BIRD evidence for GPT pipelines. — [SEED](https://arxiv.org/html/2506.07423)
- A CIDR 2026 study reports a 52.8% annotation error rate on BIRD Mini-Dev (not full dev). — [Text-to-SQL Benchmarks are Broken, CIDR 2026](https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf)

### Inferences
- Since gold evidence is worth about 8-11 EX for gpt-4o-mini pipelines, *how* evidence is used matters more than replacing it. E-SQL-style enrichment (rewriting the question to explicitly embed evidence formulas and column names) is the measured gpt-4o-mini option (+1.1 to +1.9).
- High label noise (about 30% "gold error" among MAC-SQL BIRD errors; 52.8% annotation errors on Mini-Dev) caps achievable gains. Some of the 236 "wrong values" errors are likely unfixable.

### Gaps
- No paper measured divide-and-conquer or query-plan CoT on gpt-4o-mini on BIRD dev. The thesis's own negative result is the best evidence for this model.

## Q6. Per-sample self-correction / refinement, and fairness at N=8

### Takeaway
Self-correction gives larger gains for weaker models: gpt-4o-mini fixes about 6.6% of non-executable queries and +3.6 EX in E-SQL, versus about 0.4% for GPT-4o. Execution-guided fixing gives +0.9 to +3.8 per single candidate (Gemini). Refiners that only touch failing or empty SQL (MAC-SQL, DIN-SQL style) leave the candidate count unchanged but add LLM calls. Fairness should therefore be reported in calls/tokens, not just "8 samples".

### Cited Findings
- E-SQL self-correction (SR) with gpt-4o-mini: without SR 58.03 vs 61.60 full (-3.57; the table row also removes QE and CPG, so attribution is mixed). SR effect analysis (Table 7): wrong-to-correct 5.35% (gpt-4o-mini) vs 1.83% (GPT-4o); non-executable-to-executable 6.58% (gpt-4o-mini) vs 0.39% (GPT-4o). — [E-SQL](https://arxiv.org/html/2409.16751)
- CHASE-SQL query fixer (execution-feedback repair, Gemini 1.5 Pro, single candidate): baseline 57.75 -> 61.58 (+3.83); QP 63.62 -> 65.51 (+1.89); DC 63.92 -> 65.77 (+1.85); online synthetic 67.09 -> 68.02 (+0.93). Full system without fixer 69.23 vs 73.01 (-3.78). Gains shrink as the generator gets stronger. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- MAC-SQL + GPT-4: without Refiner 54.76 vs 59.39 (-4.63, the largest component). The refiner runs at most 3 rounds and does not touch SQL that executes and returns non-empty results. — [MAC-SQL](https://arxiv.org/html/2312.11242)
- MCTS-SQL with gpt-4o-mini: full 63.15; without MCTS-Refiner 57.96 (-5.19); without Selector 60.79; "w/o Schema" 61.56. E-SQL + gpt-4o-mini as their baseline = 59.81. — [MCTS-SQL, arXiv 2501.16607](https://arxiv.org/html/2501.16607v1)
- RSL-SQL multi-turn self-correction: +0.78 (GPT-4o), +0.26 (DeepSeek) on top of a strong pipeline. — [RSL-SQL](https://arxiv.org/html/2411.00073)
- Maamari et al.: removing correction -1.36 (ft:GPT-4o), -3.40 (Gemini 1.5 Pro), -3.40 (Llama-3.1-405B). — [Maamari et al.](https://arxiv.org/html/2408.07702)
- CHESS [subsampled dev]: without revise 57.82 vs 64.62 (-6.80); revise limited to 1 pass 61.22 (-3.40). More revision samples for self-consistency gave larger gains. — [CHESS](https://arxiv.org/html/2405.16755)
- Self-consistency vs correction: in CHASE-SQL (Gemini 1.5 Pro), single query 63.01 -> self-consistency 68.84 (+5.84), oracle upper bound 82.79. CSC-SQL argues self-consistency can choose wrong majorities while self-correction mainly fixes syntax errors, and that combining them costs more compute than plain SC. — [CHASE-SQL](https://arxiv.org/html/2410.01943); [CSC-SQL, arXiv 2505.13271](https://arxiv.org/pdf/2505.13271)

### Inferences
- Fairness at N=8: if correction only runs on samples that error out or return empty results (74 + 68 of 630 baseline failures), the voting pool is still 8 candidates. The extra cost is bounded (at most 1-3 extra calls per failing sample), so "fixed 8 samples" remains a defensible comparison *if* the thesis also reports average LLM calls and tokens per question for both Ours and the baseline. A stricter check would be a compute-matched baseline: give the baseline as many extra samples as the repair calls used (e.g., maj@9-10), or run the same repair on the baseline's 8 samples. If Ours still wins, the gain comes from the method and not from the extra budget. This is my recommendation; no paper found does such a compute-matched comparison.
- Correcting every sample with an LLM critic (not just failing ones) is riskier: it increases agreement (fewer distinct answers), and E-SQL/CHASE data show most gains come from non-executable fixes. Applying the 'empty result' trigger is supported by MAC-SQL/DIN-SQL practice.
- For gpt-4o-mini specifically, repair has the highest relative value (6.58% vs 0.39% non-exec fixes compared with GPT-4o), so per-sample repair before voting should give more than the greedy-only repair already in use.

### Gaps
- I found no paper that compares self-consistency at budget N vs self-correction at matched token budget on BIRD for gpt-4o-mini. "Rethinking agentic workflows: Evaluating inference-based test-time scaling strategies in text2sql tasks" (Dessí & Ozsoy) may cover this, but I could not verify it.
- I could not read "Query and Conquer: Execution-Guided SQL Generation" ([arXiv 2503.24364](https://arxiv.org/pdf/2503.24364)); the PDF did not parse. It claims execution-based self-consistency lets small models approach larger reasoning models at lower cost, but I have no verified numbers.

## Q7. What helps gpt-4o-mini specifically (reported numbers)

### Takeaway
Published gpt-4o-mini BIRD dev results are 45.7 (zero-shot full schema) to 63.15 (MCTS-SQL, multi-call). The thesis's 59-60 single sample is already at the level of the full E-SQL pipeline as reproduced by others. Techniques with gpt-4o-mini evidence are: candidate predicate/value probing (+2.0), question enrichment (+1.1 to +1.9), self-correction (+3.6, mixed attribution), and MCTS refinement (+5.2, multi-call). Schema filtering hurt (-5.5 to -8.2).

### Cited Findings
- gpt-4o-mini BIRD dev results found: zero-shot full schema 45.70, with bidirectional retrieved schema 51.11, with gold schema 56.84 ([Rethinking Schema Linking](https://arxiv.org/html/2510.14296)); E-SQL basic generation 57.69, full E-SQL 61.60 ([E-SQL](https://arxiv.org/html/2409.16751)); MCTS-SQL 63.15 ([MCTS-SQL](https://arxiv.org/html/2501.16607v1)); CHESS (IR+CG+UT, gpt-4o-mini) with BIRD evidence 63.04 ([SEED](https://arxiv.org/html/2506.07423)).
- Conflicting reports for E-SQL + gpt-4o-mini: 61.60 self-reported ([E-SQL](https://arxiv.org/html/2409.16751)); 59.81 in MCTS-SQL's table ([MCTS-SQL](https://arxiv.org/html/2501.16607v1)); 56.6 in Rethinking-Schema-Linking's Table 3 ([2510.14296](https://arxiv.org/html/2510.14296)). The same table lists MAC-SQL* (gpt-4o-mini) 50.6, while Solid-SQL's Spider table shows MAC-SQL (gpt-4o-mini) 78.1 on Spider. This suggests reproduced pipeline numbers differ by 2-5 EX across papers.
- gpt-3.5 references: MAC-SQL + GPT-3.5 50.56; MAG-SQL + GPT-3.5 57.62 ([RSL-SQL Table I](https://arxiv.org/html/2411.00073)); TA-SQL + ChatGPT 43.74 vs 37.22 baseline ([TA-SQL](https://arxiv.org/html/2405.15307)); CHESS all-GPT-3.5 49.65 [subsampled dev] ([CHESS](https://arxiv.org/html/2405.16755)).
- GPT-4o references: RSL-SQL 67.21; E-SQL 65.58; OpenSearch-SQL single generation 67.8 (69.3 with vote) ([RSL-SQL](https://arxiv.org/html/2411.00073); [E-SQL](https://arxiv.org/html/2409.16751); [OpenSearch-SQL](https://arxiv.org/html/2502.14913)).
- Fine-tuned components (not training-free, listed separately): CHESS candidate generator FT-DeepSeek (64.62 vs 55.78 with GPT-4-turbo in that role) ([CHESS](https://arxiv.org/html/2405.16755)); Solid-SQL FT Llama3-8B schema linker ([Solid-SQL](https://arxiv.org/html/2412.12522v1)); Maamari et al. use ft:GPT-4o ([Maamari et al.](https://arxiv.org/html/2408.07702)); CHASE-SQL's best selector is tuned Gemini-1.5-Flash (71.01 binary acc vs 63.98 untuned Pro) ([CHASE-SQL](https://arxiv.org/html/2410.01943)).

### Inferences
- Ranked by evidence quality for this setup (gpt-4o-mini, baseline about 60, fixed 8 samples), the most promising untried per-sample levers are: (1) per-sample execution repair including the empty-result trigger; (2) SELECT/info alignment for column-count errors; (3) better few-shot (masked/skeleton re-rank, Query-CoT-SQL format, or online synthetic examples); (4) E-SQL-style value probing (CPG) and question enrichment. Expected gains on top of an already-strong baseline are probably around +0.5-2 each, not the +5-10 reported against weak baselines.
- Do not adopt hard schema pruning.

### Gaps
- The BIRD leaderboard was not fetched, so I have no gpt-4o-mini leaderboard entries beyond the papers above.
- CA-SQL (arXiv 2605.08057) uses gpt-4o-mini for all experiments, but I did not retrieve its numbers.
