# Training-free techniques (2023–2026) for better candidates on BIRD dev, focused on gpt-4o-mini-class models

Context for the reader: "Ours" = gpt-4o-mini-2024-07-18, OmniSQL prompt (full DDL + sample values) + evidence + BM25 few-shot + value retrieval + base/plan prompts, 8 samples @T=0.8, one execution repair of greedy, result-set majority vote (non-empty preferred), LLM selector on ties. Ours greedy 58.80, Ours@8 63.62, v9 65.06 (BIRD dev EX). All numbers below are BIRD dev EX (%) unless stated. "Unverified" = from memory / not confirmed in a fetched primary source this session.

## Q1. Schema linking / schema pruning: gains, and when full schema is better for small models

### Takeaway
For GPT-4o / GPT-4o-mini-class models, explicit schema *filtering* usually hurts (E-SQL: −8.21 for gpt-4o-mini; Maamari et al.: −11.57 with single-column linking); only high-recall linking that keeps most columns (RSL-SQL bidirectional linking, ~94% strict recall) gives small gains (+0.65 to +1.17). Since Ours already uses full DDL, schema pruning is NOT a promising direction; "schema linking as a hint/augmentation" (not removal) is the only variant with positive evidence.

### Cited Findings
- **E-SQL** (arXiv 2409.16751, v2 Jan 2025; venue not stated on page). Main model gpt-4o-mini. Table 4 (BIRD dev, gpt-4o-mini): plain generation G = 57.69; SF-G (schema filtering then generate) = 49.48 (−8.21); SF-QE-G = 55.34 (−2.35); QE-G (question enrichment, full schema) = 58.80 (+1.11). Authors conclude schema filtering is redundant/harmful with GPT-4o and GPT-4o-mini, with drops at every difficulty level regardless of where filtering is placed. Table 5: adding SF to full E-SQL drops 61.60 → 56.06 (−5.54). — [E-SQL](https://arxiv.org/html/2409.16751)
- **The Death of Schema Linking? (Maamari et al., Distyl AI)** (arXiv 2408.07702). Table 2, evaluated on a 10% BIRD dev subset (147 Qs; small-sample noise ±~4 pts): full pipeline (full schema) ft:GPT-4o 67.35 / Gemini 1.5 Pro 60.54 / Llama 3.1-405B 59.18; "w/ TCSL" (table+column schema linking) 62.58 (−4.77) / 55.78 (−4.76) / 56.46 (−2.72); "w/ SCSL" (single-column linking) 55.78 (−11.57) / 55.10 (−5.44) / 54.42 (−4.76). Base model with full schema and no pipeline: 59.18 / 57.82 / 53.74 — i.e., SCSL pipeline with ft:GPT-4o was *worse than the bare full-schema base model*. Table 1: full schema false-positive rate 94.62% but strict linking recall 100%; TCSL recall only 77.44%. GPT-4o-mini was used for the schema-linking (SCSL/HySCSL) and formatting steps. — [Maamari et al.](https://arxiv.org/html/2408.07702)
- **RSL-SQL** (arXiv 2411.00073, Oct/Nov 2024). Models GPT-4o and DeepSeek (no gpt-4o-mini). Cumulative ablation (Table IV): base prompt 48.70 (GPT-4o) / 42.96 (DeepSeek); +few-shot 58.67 / 55.48; +data samples 62.06 / 57.63; +Step1 bidirectional schema linking 62.71 (+0.65) / 58.80 (+1.17); +Step2 contextual info augmentation 65.06 (+2.35) / 61.67 (+2.87); +Step3 binary selection (full vs simplified schema SQL) 66.43 (+1.37) / 63.30 (+1.63); +Step4 multi-turn self-correction 67.21 (+0.78) / 63.56 (+0.26). Linked schema keeps strict recall 94.32% (GPT-4o) while cutting columns from 76.28 to 13.02 on average. — [RSL-SQL](https://arxiv.org/html/2411.00073)
- **CHESS** (arXiv 2405.16755, v3 Nov 2024). Tool ablation on a subsampled BIRD dev set (engine: GPT-3.5-turbo filtering, fine-tuned DeepSeek generation, GPT-4-turbo selection/revision): all tools 64.62; w/o filter_column 61.90 (−2.72); w/o select_tables 58.50 (−6.12); w/o select_columns 59.18 (−5.44). Pruning helps here, but the generator is a fine-tuned DeepSeek and older GPT-4-turbo/GPT-3.5 models; with all-GPT-3.5 the pipeline gets only 49.65 and all-Llama-3-70B 54.42. No gpt-4o-mini results. — [CHESS](https://arxiv.org/html/2405.16755)
- **MCTS-SQL** (arXiv 2501.16607) ablation with gpt-4o-mini (Table 4): full 63.15; w/o Selector (selects a minimal subset of tables/columns) 60.79 (−2.36); w/o semi-structured schema format (plain DDL instead) 61.56 (−1.59). Note: here the "Selector" is a schema selector, and it helped gpt-4o-mini — conflicting with E-SQL's finding; the difference may be that MCTS-SQL's selector output is used together with refinement, not as a hard filter (not verified). — [MCTS-SQL v1](https://arxiv.org/html/2501.16607v1)
- **TA-SQL** (arXiv 2405.15307; Findings of ACL 2024 — venue unverified) ablation (GPT-4, BIRD dev): full 56.19; w/o task-aligned schema linking (TASL) 49.77 (−6.42); w/o logical synthesis (TALOG) 52.41 (−3.78). Baseline GPT-4 46.35 — baseline is a weak zero-shot prompt, so gains are relative to a much lower start than Ours. — [TA-SQL](https://arxiv.org/html/2405.15307)
- **LinkAlign** (arXiv 2503.18596, v4 Sep 2025): schema linking with GLM-4-air; BIRD dev EX: simplified LinkAlign + GPT-4 61.6, + DeepSeek-V3 57.5, + Qwen-72B 53.4. Module ablations are on Spider/AmbiDB only, not BIRD; no full-schema baseline for BIRD; no small models. Designed for large multi-database schemas (Spider 2.0-style), not BIRD. — [LinkAlign](https://arxiv.org/html/2503.18596)
- **Solid-SQL** (arXiv 2412.12522): schema linking requires a fine-tuned Llama3-8B (not training-free); BIRD dev Solid-SQL + GPT-4 = 58.9; gpt-4o-mini only reported on Spider robustness variants (avg 77.1 EX round 2). — [Solid-SQL](https://arxiv.org/html/2412.12522)
- **ReFoRCE** (arXiv 2502.00675) explicitly says in its limitations that it generalizes poorly to BIRD and reports no BIRD numbers; its "DB info compression" (−3.65 when removed) matters for huge Spider 2.0 schemas. — [ReFoRCE](https://arxiv.org/html/2502.00675)

### Inferences
- With gpt-4o-mini and BIRD-sized schemas (avg ~76 columns), the evidence (E-SQL −8.21, Maamari −4.8 to −11.6) says hard pruning removes needed columns more often than it removes distractors. Ours' full-DDL choice is consistent with the literature.
- The only schema-linking variant with positive evidence for strong models is RSL-SQL's "binary selection": generate one SQL with full schema and one with simplified schema, then choose (+1.37/+1.63). For Ours, this is equivalent to adding a pruned-schema prompt as an extra *diversity source* in the candidate pool, not replacing the full schema. This is a cheap, untested idea for Ours (candidate pool diversity), but expected gain is small (~1 pt) and partially overlaps with Ours' existing base/plan diversity.
- MCTS-SQL's gpt-4o-mini selector gain (+2.36) conflicts with E-SQL; MCTS-SQL's ablation is not a clean full-schema vs pruned comparison inside an 8-sample vote, so it is weaker evidence.

### Gaps
- No paper found that tests schema pruning *inside a multi-sample voting pipeline* with gpt-4o-mini (i.e., whether a pruned-schema prompt adds useful diversity to the vote).
- Venues for E-SQL, CHESS, RSL-SQL, MCTS-SQL, LinkAlign, Solid-SQL not confirmed on the fetched pages (arXiv only). Maamari et al. may have appeared at a NeurIPS 2024 workshop (TRL) — unverified.

## Q2. Value retrieval (LSH / embedding / keyword extraction) and ablation deltas

### Takeaway
Value/entity retrieval is consistently worth +1.4 to +4.8 EX in ablations, but Ours already has value retrieval; the remaining upside is in *how* values are found (LLM keyword extraction + LSH fuzzy match + embedding similarity on column descriptions), which is untested for Ours.

### Cited Findings
- **CHESS**: removing retrieve_entity & retrieve_context (LLM keyword extraction → LSH + edit-distance/embedding value matching, plus description retrieval) drops 64.62 → 59.86 (−4.76) on subsampled BIRD dev (GPT-3.5/fine-tuned DeepSeek/GPT-4-turbo engine). — [CHESS](https://arxiv.org/html/2405.16755)
- **CHASE-SQL** (arXiv 2410.01943; ICLR 2025 — venue unverified on page): w/o LSH value retrieval 73.01 → 70.09 (−2.92), Gemini 1.5 Pro, BIRD dev. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **OpenSearch-SQL** (arXiv 2502.14913), Mini-Dev ablation (model not stated; main model GPT-4o-0513): full 70.6; w/o Values Retrieval 69.2 (−1.4); w/o Extraction (LLM extracts entities/keywords + values + columns) 67.4 (−3.2); w/o column filtering 68.6 (−2.0); w/o info alignment 68.6 (−2.0). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **Alpha-SQL** (arXiv 2502.17248; ICML 2025 per keywords line — unverified) action ablation (Qwen2.5-Coder, SDS subset): w/o Column Value Identification −0.4; w/o Column Function Identification −0.6; w/o Question Rephrasing −0.7; w/o Schema Selection −1.5. Small deltas when the rest of the MCTS pipeline is present. — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- **E-SQL** candidate predicate generation (CPG: executes LIKE-queries on the DB to find candidate predicate values from an initial SQL, then feeds them back): w/o CPG 61.60 → 59.58 (−2.02) with gpt-4o-mini. — [E-SQL](https://arxiv.org/html/2409.16751)

### Inferences
- E-SQL's CPG is the most relevant value-related technique with a gpt-4o-mini number: it is "value retrieval conditioned on a draft SQL" (look up actual values for the predicates the draft SQL used), which differs from Ours' question-based retrieval. It plausibly fixes wrong literal casing/format in WHERE clauses — a common BIRD error type. Worth testing as a targeted repair step.
- Gains in CHESS/CHASE are measured against pipelines with no other value grounding; since Ours already retrieves values, expected marginal gain from LSH upgrade is likely smaller than the reported −2.9/−4.8.

### Gaps
- No paper found isolating keyword-extraction LLM vs. BM25/n-gram value matching with gpt-4o-mini.

## Q3. Few-shot: online synthetic examples (CHASE-SQL), DAIL-SQL selection, skeleton-similarity

### Takeaway
CHASE-SQL's online synthetic example generator (OS) is the single strongest *single-candidate* generator in the literature (+9.34 over zero-shot CoT with Gemini 1.5 Pro), but in a full multi-generator pipeline removing it costs only −0.85. Few-shot itself is very large (+10 RSL-SQL, +4.6 OpenSearch-SQL); format of examples (question→CoT→SQL vs question→SQL) matters (+2.8 single-SQL).

### Cited Findings
- **CHASE-SQL** Table 4 (Gemini 1.5 Pro, BIRD dev, single candidate): zero-shot CoT baseline 57.75; Query-Plan CoT 63.62 (+5.87); Divide-and-Conquer CoT 63.92 (+6.17); Online Synthetic examples CoT 67.09 (+9.34); with query fixer: 61.58 / 65.51 / 65.77 / 68.02. Table 7 (full pipeline 73.01): w/o OS −0.85, w/o QP −0.65, w/o DC −1.24. Table 6: OS generator has the highest lower bound (60.43 at T=0.5) but lower upper bound (74.77) than QP/DC (78.55/78.42) — i.e., OS gives better individual samples but less diversity. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **OpenSearch-SQL** Table 5: few-shot in Query-CoT-SQL format 65.8 (single SQL) / 70.6 (final); Query-SQL format 63.0 / 69.2; no few-shot 59.6 / 66.0. Table 4: w/o few-shot in generation 70.6 → 66.0 (−4.6). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **RSL-SQL** Table IV: + few-shot examples 48.70 → 58.67 (+9.97, GPT-4o) and 42.96 → 55.48 (+12.52, DeepSeek). — [RSL-SQL](https://arxiv.org/html/2411.00073)
- **Solid-SQL**: two-round retrieval — question-skeleton embedding similarity, then SQL-skeleton edit distance (sqlglot) from a draft SQL; training-free part. N=7 examples best. No ablation of skeleton retrieval vs plain similarity, and no BIRD gpt-4o-mini numbers. — [Solid-SQL](https://arxiv.org/html/2412.12522)
- **DAIL-SQL** (arXiv 2308.15363, VLDB 2024 — unverified this session): question+SQL-skeleton similarity selection; BIRD dev with GPT-4 + self-consistency 54.76 (also cited in LinkAlign's table as 54.8). Its selection ablations are on Spider, not BIRD (unverified). — [LinkAlign table](https://arxiv.org/html/2503.18596)

### Inferences
- Ours uses BM25 question similarity from BIRD train. Untested upgrades with evidence: (a) CoT-annotated examples (question→reasoning→SQL), +2.8 single-SQL in OpenSearch-SQL; (b) draft-SQL skeleton retrieval (DAIL/Solid-SQL style second round); (c) CHASE-SQL OS examples synthesized *on the target DB schema* (covering SQL features like JOIN types, aggregation, ordering), which matters for BIRD because train DBs differ from dev DBs. OS is the strongest per-sample generator and could replace or join the base/plan prompts as a third diversity source.
- CHASE's Table 6 implies OS raises the per-sample floor but reduces upper bound; for a voting system like Ours, the gain may be larger than −0.85 suggests because Ours' vote (not a trained selector) benefits more from higher per-sample accuracy.

### Gaps
- No gpt-4o-mini reproduction of CHASE-SQL OS generator found.
- DAIL-SQL BIRD ablation for selection strategies not confirmed.

## Q4. SQL correction/refinement, execution-feedback agents, MCTS: deltas and cost

### Takeaway
Refinement is the biggest single ablation in most pipelines (CHESS −6.80, MAC-SQL −4.63, MCTS-SQL gpt-4o-mini −5.19, CHASE −3.78), but Ours already does one repair of greedy. The most relevant gpt-4o-mini evidence is MCTS-SQL (63.15 full, ≈ Ours@8 63.62) and CA-SQL (61.06) — both below Ours v9 65.06, so neither pipeline as a whole beats Ours; only specific modules are worth borrowing.

### Cited Findings
- **MCTS-SQL** (arXiv 2501.16607, v3 Nov 2025) BIRD dev: gpt-4o-mini 63.15 (VES 60.78), GPT-4o 69.40, Gemini 2.5 Pro 72.91, Qwen2.5-Coder-7B 53.61, 3B 46.71, 1.5B 40.69. gpt-4o-mini ablation: w/o MCTS-Refiner 57.96 (−5.19); w/o Selector 60.79 (−2.36). Default max rollouts 5, child nodes 2; more rollouts (6/7) gave 62.83/62.88 — no gain. Qwen-1.5B: prefix-cache reduces latency 6.12 s → 2.84 s and tokens 2274 → 864. No monetary cost reported. — [MCTS-SQL v1](https://arxiv.org/html/2501.16607v1); [MCTS-SQL v3](https://arxiv.org/html/2501.16607)
- **Alpha-SQL** (arXiv 2502.17248): zero-shot MCTS with Qwen2.5-Coder: 7B 66.8, 14B 68.7, 32B 69.7 BIRD dev. N_rollout=24, N_expansion=3 @T=0.8, N_reward=5 @T=1.0, N_revision=10. Reward = fraction of sampled SQL agreeing on execution result (self-consistency as reward). w/o SQL revision −1.8. No cost reported; no gpt-4o-mini. — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- **CA-SQL** (arXiv 2605.08057, May 2026, Petullo & Xue): complexity-aware inference-time exploration and compute budget allocation, gpt-4o-mini only, training-free: BIRD dev EX 61.06, challenging 51.72, Soft-F1 68.77. Ablation numbers/cost not on abstract page. — [CA-SQL](https://arxiv.org/abs/2605.08057)
- **CHESS**: w/o revise 64.62 → 57.82 (−6.80); 1-time revise 61.22 (−3.40) — i.e., multiple revisions beat one. — [CHESS](https://arxiv.org/html/2405.16755)
- **CHASE-SQL**: query fixer (up to β iterations on syntax errors/empty results): w/o fixer −3.78; per generator +2.0 to +3.8 (baseline 57.75 → 61.58; OS 67.09 → 68.02). — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **MAC-SQL** (arXiv 2312.11242, v6 Mar 2025; COLING 2025 — unverified) GPT-4 BIRD dev: full 59.39; w/o Selector 57.28 (−2.11); w/o Decomposer 55.54 (−3.85); w/o Refiner 54.76 (−4.63). MAC-SQL + GPT-3.5-Turbo 50.56. — [MAC-SQL](https://arxiv.org/html/2312.11242)
- **MAGIC** (arXiv 2406.12692; automatically generated self-correction guideline from failures on train): with DIN-SQL + GPT-4 on BIRD dev: no correction 56.52; DIN-SQL human-written guideline 57.76; MAGIC guideline (applied to incorrect SQLs) 59.13 (+2.61 vs none, +1.37 vs human). Applied to all SQLs: 58.55 vs human 55.80 (human guideline on all SQLs *hurts*: 55.80 < 56.52). — [MAGIC](https://arxiv.org/html/2406.12692)
- **OpenSearch-SQL**: w/o Refinement (execution-based) 70.6 → 67.0 (−3.6); w/o Correction 69.8 (−0.8); w/o self-consistency & vote 68.2 (−2.4); GPT-4o-mini reportedly peaks at 7 and 15 candidates (Fig. 4, numbers not readable). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **E-SQL** SQL refinement (execution-guided): stated −3.57 when removed along with QE and CPG (gpt-4o-mini; 58.34 → 58.03 isolates SR as only −0.31 once QE and CPG are already removed). — [E-SQL](https://arxiv.org/html/2409.16751)
- **RSL-SQL** multi-turn self-correction (on queries flagged as wrong): +0.78 (GPT-4o), +0.26 (DeepSeek). — [RSL-SQL](https://arxiv.org/html/2411.00073)
- **ReFoRCE** (Spider 2.0 only, no BIRD): column exploration (probe queries on DB) w/o −2.37 to −2.56 EX with o3; self-refinement averages 1.69 LLM calls/example; majority voting w/o −1.83 to −2.01. — [ReFoRCE](https://arxiv.org/html/2502.00675)

### Inferences
- Ours repairs only greedy once. CHESS (1 revise −3.40 vs multi) and CHASE (fixer per candidate) suggest multi-iteration fixing helps, but the user already found "repair every failed/empty sample before voting" did NOT help on their 300-Q split. That is consistent with E-SQL (SR isolated ≈ −0.31) and RSL-SQL (+0.26 to +0.78): once a strong vote exists, extra repair adds little. Refinement gains in ablations are largest when there is no voting.
- MAGIC-style guideline (mine Ours' own failures on BIRD train → a checklist of gpt-4o-mini error patterns, used in the repair prompt only for flagged SQLs) is training-free and untested for Ours; caveat from MAGIC: applying corrections to all SQLs can hurt.
- MCTS approaches with gpt-4o-mini (63.15) do not beat Ours@8 (63.62); MCTS cost is many more LLM calls (Alpha-SQL: 24 rollouts × multiple calls). Not cost-effective given Ours' budget (~$75 cap).

### Gaps
- DIN-SQL (arXiv 2304.11015, NeurIPS 2023) BIRD self-correction ablation not fetched; its BIRD dev GPT-4 score 50.7 is cited in LinkAlign/Solid-SQL tables. — [LinkAlign table](https://arxiv.org/html/2503.18596)
- SQL-CRAFT (arXiv 2402.14851) and SQL-o1 (arXiv 2502.11741, fine-tuned) not fetched; numbers unverified.
- No dollar-cost figures in MCTS-SQL, Alpha-SQL, CA-SQL.

## Q5. Evidence/hint handling and question decomposition (MAC-SQL, DIN-SQL, PURPLE, TA-SQL, E-SQL)

### Takeaway
Question enrichment (E-SQL QE, +1.11 to +1.89 with gpt-4o-mini) and decomposition (MAC-SQL Decomposer +3.85 with GPT-4; CHASE DC CoT +6.17 single-candidate) are the techniques with measured gains; for gpt-4o-mini, E-SQL QE is the only directly measured one.

### Cited Findings
- **E-SQL QE** (LLM rewrites the question, integrating evidence + relevant schema items + values into an enriched question), gpt-4o-mini: QE-G 58.80 vs G 57.69 (+1.11); in full pipeline w/o QE 59.71 vs 61.60 (−1.89); w/o QE & CPG 58.34 (−3.26). E-SQL also tested on small open models (Qwen2.5-Coder 7B/1.5B, DeepSeek-Coder 1.3B/7B) without fine-tuning (numbers not extracted). — [E-SQL](https://arxiv.org/html/2409.16751)
- **MAC-SQL** decomposer (sub-question CoT): −3.85 when removed (GPT-4), largest on simple/moderate. — [MAC-SQL](https://arxiv.org/html/2312.11242)
- **CHASE-SQL** Divide-and-Conquer CoT: +6.17 over zero-shot CoT single-candidate; in full pipeline −1.24 when removed (Gemini 1.5 Pro). — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **TA-SQL** (hallucination mitigation via task alignment: dummy-SQL-based schema linking + pandas-like logical synthesis): GPT-3.5-turbo 37.22 → 43.74 (+6.52); GPT-4 46.35 → 56.19; gains small for weaker open models (DeepSeek-33B +2.08, CodeLlama-34B +0.84). — [TA-SQL](https://arxiv.org/html/2405.15307)
- **RSL-SQL** Contextual Information Augmentation (generate per-element descriptions/conditions from question+evidence): +2.35 GPT-4o, +2.87 DeepSeek (cumulative). — [RSL-SQL](https://arxiv.org/html/2411.00073)
- **OpenSearch-SQL** "Info Alignment" (align extracted info/evidence with schema): −2.0 when removed; "Alignments" agents (style/function alignment post-generation): −1.0. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)

### Inferences
- Ours' "plan" prompt is similar to CHASE QP CoT. A Divide-and-Conquer CoT prompt (CHASE DC) is the most natural third prompt family to add for diversity; CHASE shows DC has a high upper bound (78.42 at T=0.5) comparable to QP.
- E-SQL's QE is cheap (1 extra call per question) and measured on the same model; it could be an additional prompt variant (enriched question) in the candidate pool rather than replacing the original question.

### Gaps
- PURPLE (arXiv 2403.20014, ICDE 2024 — unverified) BIRD numbers not fetched; mainly Spider-focused (unverified).
- DIN-SQL decomposition ablations on BIRD not confirmed.

## Q6. Output-format issues (wrong number/order of columns, extra columns) and normalization tricks

### Takeaway
Extra/missing projection columns are a large, well-documented error class (BIRD "projection error" is the largest category in one error study; 93% of output-format errors in a 2026 agent study are extra columns), but few papers report a clean ablation of a fix. The closest measured fixes are post-generation "alignment" agents (OpenSearch-SQL, −1.0 when removed) and selection/unit-test style checks; the user's column-count rule already failed on their split.

### Cited Findings
- A study of ICL text-to-SQL errors on BIRD lists "Projection Error" as the largest category in its error table, plus an "Output Ambiguity" category (question does not specify output format). — [Understanding, Detecting, and Repairing ICL Text-to-SQL Errors, arXiv 2501.09310](https://arxiv.org/html/2501.09310v1)
- "Both Ends Count!" (arXiv 2602.21480): 627 of the Output Format errors (93.16%) are additional columns; authors argue classic EX marks usable answers wrong. (Not BIRD-specific.) — [arXiv 2602.21480](https://arxiv.org/pdf/2602.21480)
- Codex-era Spider analysis defined "SELECT Extra Columns" (2.9% of predictions) and "SELECT Convention" (name vs ID) errors. — [Rajkumar et al., arXiv 2204.00498](https://arxiv.org/pdf/2204.00498)
- OpenSearch-SQL "Alignments" (style alignment agents after generation): w/o −1.0 (70.6 → 69.6, Mini-Dev). — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- CHESS unit tester / CHASE-SQL pairwise selection agent pick between candidates that differ in columns; CHASE: selection agent (fine-tuned Gemini Flash) beats self-consistency by +4.17, but a trained selector is NOT training-free; an untuned Gemini-1.5-Pro selector has only 63.98% binary accuracy and Claude-3.5-Sonnet 60.21%. — [CHASE-SQL](https://arxiv.org/html/2410.01943)

### Inferences
- Since BIRD EX compares result tuples (row order-insensitive set, column order matters per row tuple), one cheap normalization for voting is to cluster candidates by result set *after* canonicalizing column order (e.g., sort columns within the vote key) or by "projection-insensitive" overlap — this only changes the vote, not the output. Not found as a published ablation; would need to be tested.
- Instruction tricks used in public pipelines (e.g., "return only the columns asked, in the order mentioned; do not add IDs") are folklore with no ablation found.

### Gaps
- No paper found with a measured BIRD dev ablation specifically for column-order/extra-column normalization.

## Q7. Reproductions with gpt-4o-mini or similar small models (numbers specifically)

### Takeaway
On BIRD dev with gpt-4o-mini, the published training-free systems found are E-SQL 61.60, CA-SQL 61.06, MCTS-SQL 63.15 — all below Ours@8 63.62 and v9 65.06. Plain gpt-4o-mini baseline ≈ 58.8 (COAL-SQL table), matching Ours' baseline greedy 58.93.

### Cited Findings
- gpt-4o-mini plain baseline on BIRD Dev 58.8 (GPT-4o 61.9) per COAL-SQL's table (arXiv 2609.20842; snippet only, unverified). — [COAL-SQL](https://arxiv.org/pdf/2609.20842)
- E-SQL with gpt-4o-mini: 61.60 full; 57.69 plain generation; QE +1.11; schema filtering −8.21. — [E-SQL](https://arxiv.org/html/2409.16751)
- MCTS-SQL with gpt-4o-mini: 63.15; w/o MCTS-refiner 57.96; w/o selector 60.79; w/o semi-structured schema 61.56. — [MCTS-SQL](https://arxiv.org/html/2501.16607v1)
- CA-SQL with gpt-4o-mini: 61.06 (challenging 51.72). — [CA-SQL](https://arxiv.org/abs/2605.08057)
- Alpha-SQL with Qwen2.5-Coder-7B (training-free MCTS): 66.8; 14B 68.7; 32B 69.7 — a 7B open model beats gpt-4o-mini pipelines here, but with very high sampling budget (24 rollouts). — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- OpenSearch-SQL with gpt-4o-mini: only a curve (peaks at 7 and 15 candidates), exact numbers not extracted. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- CHESS all-GPT-3.5 49.65; all-Llama-3-70B 54.42 (subsampled dev). — [CHESS](https://arxiv.org/html/2405.16755)
- SDE-SQL (arXiv 2506.07245) is already a frozen baseline for the user; not re-reported here. — [SDE-SQL](https://arxiv.org/pdf/2506.07245)

### Inferences
- Ranked list of NOT-yet-used training-free ideas for Ours, by evidence strength with mini-class models:
  1. E-SQL Candidate Predicate Generation (draft-SQL-conditioned value lookup): −2.02 when removed, gpt-4o-mini. Cheap.
  2. E-SQL Question Enrichment as an extra prompt variant: +1.11 / +1.89, gpt-4o-mini. 1 extra call.
  3. CHASE-SQL Divide-and-Conquer CoT and Online Synthetic examples as new candidate generators (diversity source): +6.17 / +9.34 single-candidate, −1.24 / −0.85 in full pipeline (Gemini 1.5 Pro; no mini reproduction).
  4. CoT-annotated few-shot (Query-CoT-SQL): +2.8 single-SQL / +1.4 final (OpenSearch-SQL, GPT-4o).
  5. RSL-SQL binary selection (full-schema SQL vs pruned-schema SQL): +1.37 / +1.63 (GPT-4o/DeepSeek) — use pruned schema only as an extra candidate, never as a replacement.
  6. MAGIC-style self-correction guideline mined from train failures, applied only to flagged SQLs: +2.61 vs none, +1.37 vs human guideline (GPT-4).
- Not recommended: hard schema filtering (negative for gpt-4o-mini), MCTS (no gain over Ours at much higher cost), Spider-2.0 agents like ReFoRCE (no BIRD gains reported; authors say it generalizes poorly to BIRD), schema-linking models needing fine-tuning (Solid-SQL, CHASE trained selector).
- All deltas above come from pipelines without Ours' 8-sample vote; marginal gains on top of Ours' vote will likely be smaller, consistent with the user's own finding that repair-all and descriptions did not help.

### Gaps
- No exact gpt-4o-mini numbers for CHASE-SQL generators, OpenSearch-SQL, RSL-SQL, CHESS.
- CA-SQL ablation table not retrieved (only abstract).
- COAL-SQL 58.8 baseline is from a search snippet, unverified.
