# Training-free alignment and refinement techniques for BIRD text-to-SQL error classes (2023-2026)

Context: the baseline is GPT-4o-mini with the OmniSQL prompt on BIRD dev. It got 630 questions wrong: 236 had the right result shape but wrong values, 145 had the wrong column count, 104 had the wrong row count, 74 were execution errors (49 of them "no such column"), and 68 returned an empty result.

Error class -> technique map:

| Our error class (count) | Most relevant technique | Measured gain (setting) |
|---|---|---|
| Execution error (74) / "no such column" (49) | Execution-feedback fixer/refiner (MAC-SQL Refiner, CHASE query fixer, CHESS revise, OpenSearch Correction) | +4.63 (MAC-SQL+GPT-4, full dev); +3.78 (CHASE, Gemini/Claude, full dev); +3.83 single-generator; E-SQL refinement made 6.58% of non-executable queries executable (GPT-4o-mini) |
| Empty result (68) | Empty-result triggered rewrite with sample column values (Google "disambiguation"); candidate predicate augmentation (E-SQL CPG); value retrieval / agent alignment (OpenSearch) | +0.71 disambiguation (Gemini 1.5 Pro, full dev); CPG +2.02 (GPT-4o-mini, full dev); values retrieval +1.4 (GPT-4o, Mini-Dev) |
| Wrong values, same shape (236) | Question enrichment (E-SQL QE), CPG, sample column values, hints, SQLens semantic-error signals + auditor | QE +1.89; QE+CPG +3.26 (GPT-4o-mini); sample values +1.76 (Gemini); SQLens +3.47 net on a vanilla prompt (Claude 3.5 Sonnet) |
| Wrong column count (145) | Style/function alignment (OpenSearch), SELECT-column checks; partly an evaluation/annotation artifact (FLEX) | All OpenSearch alignments together: +1.0 (GPT-4o, Mini-Dev). No isolated measurement found for the column fix |
| Wrong row count (104) | Function/style alignment (MAX vs ORDER BY LIMIT 1, IS NOT NULL, DISTINCT); SQLens "Incorrect GROUP BY"/join signals | Same +1.0 aggregate; no isolated figure found |

---

## Q1. Alignment agents and steps that enforce output style (OpenSearch-SQL, CHESS revision, E-SQL QE/CPG, BIRD gold-SQL conventions, column-selection refinement)

### Takeaway
On BIRD, the alignment and enrichment steps with measured effects are each worth about +1 to +3.3 EX. E-SQL's question enrichment plus candidate predicate generation adds +3.26 with GPT-4o-mini on full dev, the setting closest to ours. OpenSearch-SQL's three alignments together add only +1.0 on Mini-Dev with GPT-4o. I found no paper that isolates the EX gain from fixing extra or missing SELECT columns.

### Cited Findings
- **OpenSearch-SQL has three alignment types.**
  - Agent Alignment makes columns and values match the database, for example correcting `'John'` to `'JOHN'`.
  - Function Alignment standardizes aggregates: inappropriate AGG use, nesting, and redundant JOINs. Example: `ORDER BY MAX(score)` becomes `GROUP BY ID ORDER BY score`.
  - Style Alignment adjusts the SQL to dataset conventions, such as adding `IS NOT NULL` or choosing between MAX and `LIMIT 1`.
  - — [OpenSearch-SQL, arXiv 2502.14913](https://arxiv.org/html/2502.14913)
- **OpenSearch-SQL ablation (Table 4), BIRD Mini-Dev, GPT-4o-0513, 21 candidates.**
  - The full system scores 70.6; it scores 69.3 on the full dev set.
  - w/o Alignments: 69.6 (−1.0).
  - w/o Info Alignment: 68.6 (−2.0).
  - w/o Correction: 69.8 (−0.8).
  - w/o Few-shot in Refinement: 69.4 (−1.2).
  - w/o Few-shot in Generation: 66.0 (−4.6).
  - w/o CoT: 69.2 (−1.4).
  - w/o Values Retrieval: 69.2 (−1.4).
  - w/o Column Filtering: 68.6 (−2.0).
  - w/o Extraction: 67.4 (−3.2).
  - w/o Self-Consistency & Vote: 68.2 (−2.4).
  - Temperatures: 0 for extraction, 0.7 for generation and refinement.
  - — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **OpenSearch-SQL candidate count.** GPT-4o's EX rises with more candidates (N ∈ {1, 3, 7, 15, 21}). GPT-4o-mini peaks at 7 and 15 candidates. Voting picks the answer with the highest execution consistency, and the shortest execution time breaks ties. Candidates that cannot be fixed or that return empty results are excluded from the vote. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **E-SQL with GPT-4o-mini, full BIRD dev (Table 5).**
  - Full E-SQL: 61.60.
  - w/o Question Enrichment (QE): 59.71 (−1.89).
  - w/o Candidate Predicate Generation (CPG): 59.58 (−2.02).
  - w/o QE & CPG: 58.34 (−3.26).
  - w/o QE & CPG & SQL Refinement: 58.03 (−3.57). Refinement alone is therefore worth about +0.31.
  - Adding schema filtering hurts: 56.06 (−5.54).
  - E-SQL with GPT-4o reaches 65.58 on dev. No GPT-4o ablation was found.
  - — [E-SQL, arXiv 2409.16751](https://arxiv.org/html/2409.16751)
- **E-SQL QE without filtering (Table 4, GPT-4o-mini).** Plain generation scores 57.69. QE-then-generate gives 58.80 (+1.11). Schema-filter-then-generate gives 49.48 (−8.21). Schema filtering hurts strong LLMs. — [E-SQL](https://arxiv.org/html/2409.16751)
- **E-SQL CPG targets predicate errors.** It addresses incomplete values (for example, "Fresno" instead of the full district name) and wrong predicate columns, which are cases 2-5 of six defined predicate error cases. It works by executing candidate predicates and augmenting the prompt with the values that actually exist in the database. — [E-SQL](https://arxiv.org/html/2409.16751)
- **E-SQL SQL Refinement (Table 7).**
  - GPT-4o-mini: corrected 5.35% of wrong queries, made 6.58% of non-executable queries executable, and changed 49.48% of candidates.
  - GPT-4o: 1.83%, 0.39%, and 23.20% respectively.
  - Refinement helps weaker models more.
  - — [E-SQL](https://arxiv.org/html/2409.16751)
- **CHESS revision ablation (Table 4).** This is on a 147-question subsampled dev set (SDS), not full dev.
  - All tools: 64.62.
  - w/o revise: 57.82 (−6.80).
  - 1-time revise: 61.22 (−3.40 vs. multi-sample revise).
  - w/o select_columns: 59.18 (−5.44).
  - w/o select_tables: 58.50 (−6.12).
  - w/o entity/context retrieval: 59.86 (−4.76).
  - Revision is triggered for queries that are "faulty (those containing syntactic errors or empty result)". More revision samples gave larger gains.
  - Caveat: the best CHESS setup uses a fine-tuned DeepSeek Coder 34B candidate generator, so it is not fully training-free.
  - — [CHESS, arXiv 2405.16755](https://arxiv.org/html/2405.16755)
- **CHESS model mixes on SDS.** All GPT-3.5-turbo: 49.65. GPT-3.5 + GPT-4-turbo + GPT-4-turbo: 55.78. Llama-3-70B throughout: 54.42. — [CHESS](https://arxiv.org/html/2405.16755)
- **Extra columns are treated as errors by EX.** FLEX shows EX marking a semantically correct query wrong because it returns an additional `score` column. The cause is that questions do not specify output columns and the ground truth is inconsistent. Re-scoring 50 models with FLEX raised performance by over 2.6 points on average and notably changed BIRD rankings. — [FLEX, arXiv 2409.19014](https://arxiv.org/html/2409.19014v2)
- **Some BIRD gold queries select columns the question never asked for.** — [arXiv 2412.07214](https://arxiv.org/pdf/2412.07214), via search snippet
- **MCI-SQL alignment stage.** MCI-SQL has a dedicated SQL alignment phase after candidate generation and reports 74.45% EX on BIRD dev and 76.41% on test. It also built "BIRD-clear" by correcting 412 annotation errors in BIRD dev. The contribution of the alignment step alone was not verified. — [MCI-SQL, arXiv 2603.13390](https://arxiv.org/pdf/2603.13390), via search snippet

### Inferences
- **Closest analog to our setting.** E-SQL with GPT-4o-mini on full dev is the nearest match. Its QE+CPG gain of about +3.3 EX (roughly 50 questions out of 1534) is a realistic upper target for value and predicate-side enrichment. CPG maps directly to our 236 "wrong values" and 68 "empty result" buckets.
- **Column-count errors (145).** The literature treats these mostly as convention or annotation artifacts, not reasoning errors. A deterministic "return only the columns the question asks for, in the order asked" rule plus style rules may recover some of them. However, OpenSearch's whole alignment block is worth only about 1 point on Mini-Dev, and part of the 145 are probably unrecoverable gold inconsistencies (see Q3).
- **Gold-SQL style conventions.** OpenSearch encodes them as few-shot examples: `ORDER BY ... LIMIT 1` vs. MAX, `IS NOT NULL`, no redundant JOINs. These map onto our row-count errors (104): ties, DISTINCT, GROUP BY.

### Gaps
- No paper found that isolates the EX gain of a "SELECT-column alignment" step on BIRD dev.
- The OpenSearch-SQL ablation is on Mini-Dev (500 questions) with GPT-4o. No GPT-4o-mini ablation was found.
- No per-sub-alignment ablation (style vs. function vs. agent) was found.
- The `CAST AS REAL` convention is widely known to be required by BIRD gold SQL for ratio and percentage questions. I found no source that quantifies its EX effect.

---

## Q2. Self-correction and refinement with execution feedback: gains on BIRD, how many iterations matter, and whether refining on empty results helps

### Takeaway
Execution-feedback fixers are among the most reliable training-free components on BIRD, worth about +2.8 to +4.6 EX on full dev. Up to 3 rounds is the common cap, and in practice most questions need about 1 round. Empty-result-triggered rewrites help, but modestly: about +0.7 EX in Google's ablation. Plain "self-reflection" without database signals gives near-zero net gain for strong pipelines.

### Cited Findings
- **MAC-SQL + GPT-4, full BIRD dev (Table 3).**
  - Full: 59.39.
  - w/o Refiner: 54.76 (−4.63), the largest component.
  - w/o Decomposer: 55.54.
  - w/o Selector: 57.28.
  - Max 3 correction rounds. Triggers are syntax errors, schema hallucinations (non-existent tables or columns), and empty results.
  - Limitation: if the SQL runs and returns non-empty results, the Refiner makes no correction.
  - — [MAC-SQL, arXiv 2312.11242](https://arxiv.org/html/2312.11242)
- **CHASE-SQL, full BIRD dev (Table 7).**
  - Full: 73.01.
  - w/o Query Fixer: 69.23 (−3.78).
  - Single-generator baseline: 57.75, rising to 61.58 with the fixer (+3.83).
  - The fixer is triggered by syntax errors or empty or unexpected results, with β = 3 attempts.
  - Models: Gemini 1.5 Pro and Claude 3.5 Sonnet. The selector is a fine-tuned Gemini Flash, so it is not training-free.
  - Oracle upper bound across all candidates: 82.79.
  - Replacing the selector with self-consistency: 68.84 (−4.17).
  - — [CHASE-SQL, arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- **"Is Long Context All You Need" (Gemini 1.5 Pro), full BIRD dev (Table 8), cumulative additions.**
  - All schema: 43.87.
  - + Hints: 60.23 (+16.36).
  - + Sample column values: 61.99 (+1.76).
  - + Self-correction: 64.80 (+2.81).
  - + Disambiguation: 65.51 (+0.71).
  - + Synthetic examples: 66.56 (+1.05).
  - + Verify & retry: 67.14 (+0.58).
  - — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- **Retries and empty-result disambiguation in the same paper.**
  - The pipeline retries up to 5 times with rising temperature, but averages about 1.01 attempts.
  - Disambiguation is triggered only when valid SQL returns an empty result. The model is then shown extensive sample column values and asked to rewrite the query.
  - The authors note a false-positive risk when the correct answer is genuinely empty.
  - Self-correction raised tokens per request from about 15.6k to 50.1k and latency by about 2.5×.
  - Retrieved few-shot examples barely helped: 61.60 with 0 examples vs. 62.52 with 100.
  - — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- **OpenSearch-SQL Correction.** It fixes SQL based on error details, including syntax errors and empty results, using separate few-shot examples per error type; a "Result: None" example covers empty results. Removing it costs only −0.8 on Mini-Dev, because self-consistency voting also excludes empty and failed candidates. — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- **CHESS revision.** One revise vs. none is worth +3.40 on SDS. Full multi-sample revise vs. none is worth +6.80. — [CHESS](https://arxiv.org/html/2405.16755)
- **MAGIC.** It builds a self-correction guideline from training-set failures using manager, correction, and feedback agents. Results on BIRD dev EX:
  - Zero-shot GPT-4: 40.18 → 48.19.
  - Few-shot CoT GPT-4: 45.56 → 50.38. One secondary source gives the baseline as 45.66.
  - MAC-SQL: 59.39 → 61.92.
  - MAGIC beats human-written guidelines, self-consistency, and multi-prompt self-correction baselines.
  - — [MAGIC, arXiv 2406.12692](https://arxiv.org/abs/2406.12692)
- **SQLens (Claude 3.5 Sonnet backbone, full BIRD dev).** It detects semantic errors with database and LLM signals aggregated by weak supervision, then fixes them iteratively, with an LLM auditor that rejects regressions.

  | Base system | Before | After | Fixed | Broken |
  |---|---|---|---|---|
  | Vanilla prompt | 59.07 | 62.54 | 66 | 16 |
  | MAC-SQL | 60.04 | 64.03 | 78 | 18 |
  | CHESS | 67.91 | 69.74 | 40 | 12 |
  | DIN-SQL | 39.49 | 59.99 | 303 | 20 |

  - Plain Self-Reflection nets only +1 (Vanilla), +12 (MAC-SQL), and +12 (CHESS).
  - Database signals: Abnormal Result, Empty Predicate, Incorrect Filter in Subquery, Incorrect GROUP BY, Incorrect Join Predicate, Suboptimal Join Tree, Table Similarity, Unnecessary Subquery, Value Ambiguity.
  - LLM signals: Column Ambiguity, Evidence Violation, Insufficient Evidence, LLM Self-Check, Question Clause Linking.
  - Semantic-error counts per base system (of 1534): Vanilla 589, DIN-SQL 835, MAC-SQL 601, CHESS 490.
  - — [SQLens, arXiv 2506.04494](https://arxiv.org/html/2506.04494v1)
- **DIN-SQL + GPT-4 on BIRD dev.** 50.72 EX, vs. 46.35 for a GPT-4 baseline. The self-correction ablation was reported only on Spider dev:
  - GPT-4: gentle prompt 74.2, none 73.3, generic 70.0.
  - CodeX: generic 69.9, gentle 68.7, none 67.3.
  - A "generic" prompt that assumes a bug exists hurts a strong model.
  - — [DIN-SQL, arXiv 2304.11015](https://arxiv.org/html/2304.11015)
- **SQL-CRAFT** (Interactive Correction loop plus Python-enhanced reasoning) reports at most a +1.9% improvement on BIRD dev, vs. +5.7% on Spider, over plain GPT-4. Its GPT-4 SQL-only baseline is 53.30 on BIRD. I could not verify the exact final table. — [SQL-CRAFT, arXiv 2402.14851](https://ar5iv.arxiv.org/html/2402.14851), via search snippet
- **ReFoRCE** caps self-refinement at 5 iterations for empty-result cases. It reports no BIRD numbers (Spider 2.0 only) and states it has "limited generalization" to simpler datasets like BIRD. — [ReFoRCE, arXiv 2502.00675](https://arxiv.org/html/2502.00675)

### Inferences
- **Execution errors (74, 49 of them "no such column")** are the most directly fixable bucket. MAC-SQL, CHASE, and E-SQL all show that an execution-feedback loop with ≤3 rounds recovers most of them. Feeding the exact error plus the real column list should be enough; more rounds add little, since average attempts are about 1.
- **Empty results (68)** are worth a dedicated rewrite that shows real sample or matching values (Google disambiguation, E-SQL CPG). Expect only a fraction to convert: +0.71 EX in Google's ablation is about 11 questions. The rewrite also needs a guard, because some gold answers are empty.
- **Wrong values with the right shape (236)** are invisible to execution feedback; the MAC-SQL limitation shows that. Only signal-driven detectors such as SQLens (+3.47 net on a vanilla prompt) or value-grounding (CPG) touch this bucket. A regression auditor (keep the original unless the fix is clearly better) matters: SQLens broke 12-20 queries per system.
- **Prompt tone matters.** The DIN-SQL "gentle" vs. "generic" result suggests the refiner prompt should not presume an error, or it will damage correct queries.

### Gaps
- No ablation was found that isolates "refine when the result is empty" for GPT-4o-mini on BIRD. The closest figure is Google's +0.71 with Gemini 1.5 Pro.
- SQLens's max_iter value is not stated.
- The exact SQL-CRAFT BIRD numbers were not verified from the full paper.
- No source was found reporting EX as a function of iteration count (1 vs. 2 vs. 3) on full BIRD dev. CHESS's 1 vs. multi comparison is on a 147-question subset.

---

## Q3. BIRD annotation noise and ambiguity, and the realistic ceiling of EX

### Takeaway
A large share of BIRD dev "errors" are not model errors. Audits find about 32-53% of Mini-Dev examples have annotation problems, and an estimated 30% of MAC-SQL's BIRD errors are gold errors. Realistically, only part of our 630 wrong answers is recoverable, and the column-count and value-mismatch buckets are especially contaminated.

### Cited Findings
- **Wretblad et al. 2024, noise by domain.**
  - Financial: 49% of 106 items noisy (41.5% noisy questions, 20.7% wrong gold SQL).
  - California Schools: 45% of 20 (40% wrong gold SQL).
  - Thrombosis: 40% (30% wrong SQL).
  - Toxicology: 35%.
  - Superhero: 15%.
  - Noise types: spelling/syntax, incorrect SQL, vague/ambiguous, capitalization, synonyms.
  - On corrected SQL, zero-shot GPT-3.5 outperformed DIN-SQL and MAC-SQL. Noise affects methods unequally.
  - — [Understanding the Effects of Noise in Text-to-SQL, arXiv 2402.12243](https://arxiv.org/html/2402.12243)
- **Arcwise (2024)** reported annotation errors in 32.3% of BIRD Mini-Dev, flagging 161 examples. — cited by [Jin et al., arXiv 2601.08778](https://arxiv.org/html/2601.08778v2) and [DDKang Substack](https://ddkang.substack.com/p/pervasive-annotation-errors-break)
- **Jin et al. (VLDB 2026), "Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards."**
  - Error rate: 52.8% of the 498 Mini-Dev examples (263) have errors.
  - Categories:
    - E1, question-SQL logic mismatch: 29.28%.
    - E2, limited understanding of data or schema: 57.79%.
    - E3, domain knowledge errors: 10.65%.
    - E4, ambiguity: 29.66%.
  - Full dev sample: 48 of 100 randomly sampled BIRD dev examples needed corrections (41 SQL, 19 questions, 17 evidence).
  - Leaderboard effect on the corrected subset: relative changes range from −7% to +31%, and rank shifts from −9 to +9.
    - CHESS went from 62% to 81%.
    - OpenSearch-SQL fell from 2nd to 11th.
  - Rank correlation with full dev is r = 0.85 on the uncorrected subset but only 0.32 on the corrected one.
  - — [arXiv 2601.08778](https://arxiv.org/html/2601.08778v2); [VLDB vol. 19 p931](https://www.vldb.org/pvldb/vol19/p931-jin.pdf)
- **MAC-SQL error analysis on BIRD dev.** Gold Error 30% of errors, Semantic Correct 14%, Schema Linking Error 2%. — [MAC-SQL](https://arxiv.org/html/2312.11242)
- **CHESS** notes that ambiguous questions and incorrect gold SQL reflect dataset problems where "the data formats expected from the questions were ambiguous". Its error taxonomy includes "Incorrect gold SQL" subtypes: Evidence, Description, Aggregation, Column, Filtering, NULL/DISTINCT/GROUP BY. — [CHESS](https://arxiv.org/html/2405.16755)
- **NL2SQL-BUGs** found 106 previously unnoticed annotation errors (6.91%) in BIRD. — [NL2SQL-BUGs, arXiv 2503.11984](https://arxiv.org/abs/2503.11984)
- **FLEX** finds EX underestimates models mainly because of annotation quality. Average gain is over 2.6 points under expert-level evaluation. — [FLEX](https://arxiv.org/html/2409.19014v2)
- **Oracle ceilings.** CHASE-SQL's oracle across its candidates is 82.79 on BIRD dev. The human expert figure cited is 92.96, vs. 65.45 for the best system as of Feb 2024. — [CHASE-SQL](https://arxiv.org/html/2410.01943); [Wretblad et al.](https://arxiv.org/html/2402.12243)

### Inferences
- If roughly 14% (semantically correct) plus 30% (gold error) of a system's BIRD errors are unfixable under EX, as in MAC-SQL's analysis, then perhaps around 40% of our 630 wrong answers are not realistically recoverable. That is a rough transfer from a different system.
- "Wrong column count" and "same shape, wrong value" are the buckets most inflated by gold inconsistencies: FLEX's extra-column false negatives, and E2/E4 ambiguity. Gains there will be noisy.
- Methods that over-fit gold conventions (style alignment) may look good on original dev but lose ground on corrected data. OpenSearch-SQL fell from 2nd to 11th on the corrected subset.

### Gaps
- No full-dev-set (1534) audited error rate was found; audits cover Mini-Dev or 100-example samples.
- Wretblad et al. give per-model accuracy on corrected data only as a chart, with no exact numbers.
- The CIDR 2026 and arXiv versions of Jin et al. report different Spider 2.0 rates (66.1% vs. 62.8%). The BIRD numbers above come from the arXiv v2 and VLDB versions.

---

## Q4. Error taxonomies on BIRD, and which errors are fixable

### Takeaway
The taxonomies agree on a few points:
- Schema linking, JOIN, filtering/predicate, and aggregation/GROUP BY dominate model errors.
- Execution-detectable errors (syntax, hallucinated columns, empty results) are fixable with feedback loops.
- Semantic errors that execute fine are fixable only with targeted signals, and with a regression guard.

### Cited Findings
- **NL2SQL-BUGs taxonomy.** 9 main categories and 31 subcategories: attribute, table, operator, condition, function, clause, subquery, and other. The benchmark has 2,018 expert-annotated instances. LLMs reach only 75.16% average semantic-error detection accuracy. — [NL2SQL-BUGs](https://arxiv.org/abs/2503.11984)
- **CHESS taxonomy (147-question SDS).** Incorrectly predicted SQL splits into Column, Table, Entity, Revision, Malformed Date, Evidence, NULL/DISTINCT/GROUP BY, Operation, and SELECT. Other buckets are vague question and incorrect gold. For the vanilla GPT-4 baseline, 57.1% of incorrect SQL came from schema-linking issues. Incorrect column linking was only 5.4% of CHESS's own errors. — [CHESS](https://arxiv.org/html/2405.16755)
- **DIN-SQL taxonomy (Spider train, CodeX).** Schema linking is the largest category, then JOIN, GROUP BY, nesting/set operations, invalid SQL, and miscellaneous. — [DIN-SQL](https://arxiv.org/html/2304.11015)
- **Google long-context analysis.** Error categories are vague question, incorrect generated SQL (join, logic, aggregation), and incorrect golden SQL. Joins, filtering, and aggregation contributed most. — [arXiv 2501.12372](https://arxiv.org/html/2501.12372)
- **E-SQL predicate taxonomy.** Six predicate error cases, including incomplete values and wrong predicate column. CPG targets cases 2-5. — [E-SQL](https://arxiv.org/html/2409.16751)
- **SQLens signals as a fixability taxonomy.** Signal-level fixes were measured on MAC-SQL (Table 5); exact per-signal counts were not extracted. These signals map to our buckets:
  - Empty Predicate and Value Ambiguity map to empty results and wrong values.
  - Incorrect GROUP BY and Incorrect Join Predicate map to row count.
  - Column Ambiguity maps to column count.
  - Evidence Violation maps to wrong values.
  - — [SQLens](https://arxiv.org/html/2506.04494v1)

### Inferences
- **Fixability ranking for our buckets, most to least fixable:**
  1. Execution errors (74): deterministic trigger, documented +3.8 to +4.6 EX fixer gains.
  2. Empty results (68): deterministic trigger, value-grounded rewrite, small but positive gains.
  3. Row count (104): partially fixable with style/function rules for ties, DISTINCT, and LIMIT, but ambiguity is high.
  4. Wrong values (236): needs value retrieval, CPG, or SQLens-like signals.
  5. Column count (145): heavily confounded by gold inconsistency.
- **Realistic total.** Combining an execution fixer, empty-result disambiguation, and QE/CPG-style value grounding on GPT-4o-mini could plausibly add about +3 to +6 EX. This is inferred by summing roughly non-overlapping published deltas: E-SQL's +3.57 for QE+CPG+SR with GPT-4o-mini, plus part of the fixer effect. It is not a measured number for our setup.

### Gaps
- No exact percentage breakdown of error types for GPT-4o-mini on BIRD dev was found in these sources; most percentages are in figures that could not be extracted.
- The per-signal fix counts in SQLens Table 5 were not extracted.
