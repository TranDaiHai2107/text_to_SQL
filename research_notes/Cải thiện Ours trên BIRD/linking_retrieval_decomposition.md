# Schema linking, value retrieval, few-shot retrieval and decomposition on BIRD dev: what helps or hurts (focus: GPT-4o-mini-class models, 2023-2026)

Scope note: all numbers are BIRD dev EX (%) unless stated. "SDS" = the 147-question subsampled dev set used by CHESS / Alpha-SQL / Death-of-Schema-Linking. SDS numbers are not comparable with full-dev numbers. Pipelines differ in evidence use, sampling, and self-correction, so cross-paper numbers are only roughly comparable.

## Q1. When the full schema fits in context, does schema linking reduce EX for strong models? Recall vs precision

### Takeaway
For strong models (GPT-4o class), hard schema filtering on BIRD dev usually hurts or adds less than 1 point, because lost recall costs more than the noise it removes. For GPT-4o-mini the evidence is mixed. A hard filter in E-SQL's GPT-4o-mini pipeline cost 5.5 to 8.2 points. In a single-call zero-shot setup with no correction, a high-recall retriever (~90% recall) gained 5.4 points over the full schema. Soft or high-recall linking (keep the full schema but highlight, or a bidirectional union) is the safe pattern.

### Cited Findings
- **Death of Schema Linking (Maamari et al., 2408.07702), SDS EX.**
  - Full pipeline without schema linking: ft:GPT-4o 67.35, Gemini-1.5-Pro 60.54, Llama-3.1-405B 59.18.
  - Adding table-level linking (TCSL): 62.58 / 55.78 / 56.46, which is −4.77 / −4.76 / −2.72.
  - Adding column-level linking (SCSL): 55.78 / 55.10 / 54.42, which is −11.57 / −5.44 / −4.76.
  - Bare full-schema base model with no other techniques: 59.18 / 57.82 / 53.74.
  - SCSL and HySCSL used GPT-4o-mini as the linker. TCSL and HyTCSL used GPT-4o.
  - The paper's headline is 71.83% on full BIRD dev, a separate result.
  - [Source](https://arxiv.org/html/2408.07702)
- **Death of Schema Linking, recall vs filtering trade-off.** SLR = share of queries where every required column is kept. FPR = false-positive rate of kept columns.
  - Full schema: SLR 100, FPR 94.62.
  - HySCSL: SLR 90.36, FPR 82.08.
  - SCSL: SLR 88.77, FPR 67.23.
  - HyTCSL: SLR 83.00, FPR 19.85.
  - TCSL: SLR 77.44, FPR 9.79.
  - Even ~89-90% per-query recall loses 10-11% of questions outright.
  - [Source](https://arxiv.org/html/2408.07702)
- **E-SQL (2409.16751), GPT-4o-mini.**
  - Full E-SQL: 61.60 dev (GPT-4o: 65.58). Adding schema filtering (SF) drops it to 56.06 (−5.54).
  - Basic pipeline: generation only 57.69. SF→G 49.48 (−8.21). SF→QE→G 55.34. QE→G 58.80.
  - The authors say SF hurt at every difficulty level, wherever it was placed, and dropped it: "schema filtering can result in performance degradation when the latest generation LLMs are employed."
  - E-SQL test: 59.81 EX with GPT-4o-mini (search snippet).
  - [Source](https://arxiv.org/html/2409.16751)
- **RSL-SQL (2411.00073), cumulative ablation.**
  - GPT-4o path: full-schema base 48.70, +few-shot 58.67, +data samples 62.06, +bidirectional schema linking 62.71 (+0.65), +contextual info augmentation 65.06, +binary selection 66.43, +multi-turn self-correction 67.21.
  - DeepSeek path: linking adds +1.17 (57.63 → 58.80).
  - Schema size: the full schema averages 7.44 tables / 76.28 columns per question. RSL with GPT-4o keeps 5.40 tables / 13.02 columns, with strict recall (SRR) 94.32 and non-strict recall 97.69.
  - Forward-only linking SRR is 84.74. Backward-only SRR is 90.48 (GPT-4o).
  - RSL's binary selection step chooses between the full-schema SQL and the linked-schema SQL, a hedge against recall loss.
  - [Source](https://arxiv.org/html/2411.00073)
- **CHESS (2405.16755), SDS.**
  - Full CHESS: 64.62. Without filter_column: 61.90. Without select_tables: 58.50. Without select_columns: 59.18.
  - The engines were GPT-3.5 / fine-tuned DeepSeek / GPT-4-turbo, weaker than 4o.
  - The authors state that for small schemas with highly capable LLMs, the Schema Selector creates a precision-recall trade-off that can hurt accuracy, and omitting it can be better.
  - [Source](https://arxiv.org/html/2405.16755)
- **"Rethinking Schema Linking" bidirectional retrieval (2510.14296), zero-shot single call, no correction.**
  - GPT-4o-mini: full schema 45.70, retrieved schema 51.11 (+5.41), oracle schema 56.84.
  - Gemini-2.0-flash: 52.09 / 57.86 / 60.69.
  - DeepSeek: 53.80 / 56.80 / 63.82.
  - Qwen-2.5-7B: 37.13 / 40.16 / 48.44.
  - Retriever with GPT-4o-mini: recall 90.60, FPR 25.29.
  - Published recall / FPR of other linkers: CHESS 97.12 / 30.57, RSL-SQL 93.28 / 68.23, DIN-SQL 63.58 / 11.11, TA-SQL 71.90 / 9.76.
  - The same table lists baselines with refinement: Solid-SQL + GPT-4o-mini 58.9, E-SQL + GPT-4o-mini 56.6, MAC-SQL + GPT-4o-mini 50.6.
  - [Source](https://arxiv.org/html/2510.14296)
- **MCTS-SQL (2501.16607), GPT-4o-mini.**
  - Full pipeline: 63.15.
  - Without its Selector (schema selection): 60.79 (−2.36).
  - Without its special schema format (plain DDL): 61.56 (−1.59).
  - Without MCTS-Refiner: 57.96 (−5.19).
  - So for 4o-mini inside a refine-heavy pipeline, linking was net positive.
  - [Source](https://arxiv.org/html/2501.16607v1)
- **MAC-SQL + GPT-4 (2312.11242).**
  - Full: 59.39. Without Selector: 57.28 (−2.11, almost all on challenging questions: 40.28 → 35.14).
  - MAC-SQL's selector only prunes large DBs, so it is a mild linker.
  - [Source](https://arxiv.org/html/2312.11242)
- **Alpha-SQL (2502.17248), SDS, Qwen2.5-Coder-7B.**
  - Removing the Schema Selection action: 64.6 → 63.1 (−1.5).
  - [Source](https://arxiv.org/html/2502.17248)
- **CodeS (2402.16347), fine-tuned small models, 3-shot, BIRD dev.**
  - Without its schema filter: 1B 25.42 → 23.53, 3B 31.23 → 30.64, 7B 33.44 → 33.83 (better without), 15B 35.14 → 33.57.
  - Filtering helps the smallest models most and is neutral for 7B.
  - [Source](https://arxiv.org/html/2402.16347)
- **LinkAlign (2503.18596), BIRD dev single-DB linking.**
  - Precision / Recall / EM: LinkAlign Agent 77.1 / 79.4 / 29.0, RSL-SQL 78.1 / 77.5 / 27.7, MCS-SQL 79.6 / 76.9, DIN-SQL 79.9 / 55.7, MAC-SQL 76.3 / 56.2.
  - On BIRD, a simplified LinkAlign (its filtering and rewriting steps removed) with GPT-4 scored 61.6, below RSL-SQL at 67.2. The paper argues those steps are less needed for small schemas, and its gains appear in multi-DB settings and Spider 2.0-Lite (33.09 with DeepSeek-R1).
  - No GPT-4o-mini numbers.
  - [Source](https://arxiv.org/html/2503.18596)
- **Solid-SQL (2412.12522).**
  - BIRD dev with GPT-4: 58.9 (GPT-4 alone 46.2, DIN-SQL 50.7, DAIL-SQL 54.8, MAC-SQL 50.6).
  - Its ablations of schema linking and retrieval are on Spider variants only.
  - [Source](https://arxiv.org/html/2412.12522)
  - Conflict: 2510.14296 attributes 58.9 to "Solid-SQL + GPT-4o-mini" ([Source](https://arxiv.org/html/2510.14296)), but Solid-SQL's own table gives 58.9 for GPT-4. A search snippet suggests Solid-SQL has GPT-4o-mini columns, but they could not be verified ([Source](https://arxiv.org/pdf/2412.12522)).

### Inferences
- On BIRD dev (about 7.4 tables / 76 columns per question), dropping any required column is an unrecoverable error. A linker at ~89% strict recall loses about 11% of questions by construction, while the noise it removes is worth only a few points for 4o-class models. That explains −5 to −11 for hard filters, and +0.6 to +1.2 for high-recall soft or union linking.
- GPT-4o-mini sits near the crossover point. A hard filter hurt it in E-SQL (−5.5 / −8.2). Selection helped in MCTS-SQL (+2.4) and in the single-call 2510.14296 setup (+5.4 at 90.6% recall). The result depends on recall: recall at or above ~95% plus a fallback to the full schema (RSL-style binary selection) is the low-risk design.
- The 2510.14296 full-schema baseline for GPT-4o-mini (45.70) is far below OmniSQL's GPT-4o-mini greedy (58.8, see Q5). Prompt format, evidence use, and example values matter more than linking.

### Gaps
- No paper found with a clean GPT-4o-mini A/B of full schema vs. soft linking (full schema plus highlighted columns) on full dev with a strong prompt such as OmniSQL's.
- Column-level precision numbers for E-SQL's SF were not retrieved.
- Solid-SQL's GPT-4o-mini numbers on BIRD are unverified.

## Q2. How much does value retrieval add, and does it still help when the prompt already has example values?

### Takeaway
Value retrieval is consistently worth about +2 to +3 EX on BIRD dev for strong pipelines, and up to about +5 on SDS for CHESS. CodeS shows it helps on top of representative example values, with both kept in its prompt. The marginal gain is smaller when evidence is used and the model is strong.

### Cited Findings
- **CHASE-SQL (Gemini 1.5 Pro, full dev).** Without LSH value retrieval: 73.01 → 70.09 (−2.92). — [Source](https://arxiv.org/html/2410.01943)
- **CHESS (SDS).** Without retrieve_entity and retrieve_context (LSH value retrieval plus description retrieval): 64.62 → 59.86 (−4.76). — [Source](https://arxiv.org/html/2405.16755)
- **E-SQL (GPT-4o-mini).** Without candidate predicate generation, which uses DB values to build predicates: 61.60 → 59.58 (−2.02). — [Source](https://arxiv.org/html/2409.16751)
- **RSL-SQL.** Adding data samples (example values) to the full-schema prompt: +3.39 with GPT-4o (58.67 → 62.06) and +2.15 with DeepSeek. Its later "contextual information augmentation" step adds +2.35 / +2.87. — [Source](https://arxiv.org/html/2411.00073)
- **CodeS (fine-tuned, 3-shot; prompt has representative values plus BM25-coarse / LCS-fine retrieved values).**
  - Without value retriever: 1B 25.42 → 22.23, 3B 31.23 → 29.27, 7B 33.44 → 30.96, 15B 35.14 → 33.31, about −1.8 to −3.2.
  - Without representative values: 15B 35.14 → 31.94, 7B → 30.77.
  - Each component helps independently, so retrieval adds on top of example values.
  - [Source](https://arxiv.org/html/2402.16347)
- **Alpha-SQL (SDS, Qwen-7B).** Removing the "Column Value Identification" action: 64.6 → 64.2 (−0.4). Its value retrieval itself was not ablated. — [Source](https://arxiv.org/html/2502.17248)
- **OmniSQL prompt.** Each column carries a comment with its description, two representative values, and question-relevant values retrieved from the DB, a method cited to CodeS. The paper reports no ablation of these elements. — [Source](https://arxiv.org/html/2503.02240)
- **Death of Schema Linking.** Its "Augmentation" step, which is value/keyword retrieval plus column descriptions: −2.72 when removed for ft:GPT-4o, 0.00 for Gemini, +0.68 for Llama-405B (SDS). This shows model-dependent, sometimes zero, benefit. — [Source](https://arxiv.org/html/2408.07702)

### Inferences
- Expect about +1.5 to +3 EX from question-matched value retrieval on top of static example values for GPT-4o-mini. Most of the gain is in WHERE-literal errors (casing, abbreviations, codes) on moderate and challenging questions.
- The Death of Schema Linking result (0 to +0.7 for some models) warns that the benefit depends on the model and prompt. Value retrieval should be ablated locally, not assumed.

### Gaps
- No clean published ablation of value retrieval for GPT-4o-mini with an OmniSQL-style prompt (values already embedded).
- CodeS Table 9 setting details, such as whether external knowledge or evidence was used, were not confirmed.

## Q3. Does cross-database few-shot from BIRD train (BM25 / embedding / DAIL) help GPT-4o-mini-class models?

### Takeaway
Few-shot is one of the largest single gains in prompt pipelines on BIRD: about +10 to +12.5 EX over a bare zero-shot prompt in RSL-SQL, and +9.3 from schema-aware synthetic examples in CHASE-SQL. Selection quality matters: on Spider, masked-question or structure similarity beats random, while random examples sometimes hurt GPT-3.5. Once a pipeline has strong generators and selection, the marginal value of few-shot shrinks to under 1 point. No paper found isolates GPT-4o-mini zero-shot vs. few-shot on BIRD dev.

### Cited Findings
- **RSL-SQL, BIRD dev.** Adding few-shot examples to the full-schema base prompt: GPT-4o 48.70 → 58.67 (+9.97), DeepSeek 42.96 → 55.48 (+12.52). This is the largest step in the cumulative ablation. — [Source](https://arxiv.org/html/2411.00073)
- **CHASE-SQL (Gemini 1.5 Pro), single generator, BIRD dev.**
  - Zero-shot CoT baseline: 57.75.
  - Online synthetic examples: 67.09 (+9.34), above query-plan CoT 63.62 and divide-and-conquer CoT 63.92.
  - Synthetic example sets: R_f (common SQL features over the whole DB) 65.45, R_t (filtered, schema-aware columns) 66.75, mixed 67.09. 75 examples were generated per set.
  - In the full system, removing OS examples costs only −0.85 (73.01 → 72.16).
  - [Source](https://arxiv.org/html/2410.01943)
- **DAIL-SQL (Spider dev EX, not BIRD).**
  - GPT-4: 0-shot 72.3. 1-shot random 77.4, masked question similarity 79.1, DAIL selection 80.2. 5-shot DAIL 82.4.
  - GPT-3.5-turbo: 0-shot 74.4, 1-shot random 73.9, 3-shot random 73.6. Random examples hurt.
  - The authors note that adding examples lowered EX in some GPT-3.5 / davinci settings.
  - DAIL organization (question-SQL pairs only) gives similar accuracy at several-times lower token cost than full-information organization.
  - [Source](https://arxiv.org/html/2308.15363)
- **DAIL-SQL + GPT-4 on BIRD dev.** Reported as 54.8 by Solid-SQL and LinkAlign, and 55.9 by Alpha-SQL. The sources conflict. — [Solid-SQL](https://arxiv.org/html/2412.12522); [LinkAlign](https://arxiv.org/html/2503.18596); [Alpha-SQL](https://arxiv.org/html/2502.17248)
- **CodeS (fine-tuned) in-context shots, BIRD dev.** 15B: 1-shot 34.09, 3-shot 35.14, 5-shot 37.03. 7B: 30.77 / 33.44 / 34.49. More shots help, and no 0-shot row is reported. — [Source](https://arxiv.org/html/2402.16347)
- **Solid-SQL (Spider family, Llama3-70B).** Number of retrieved examples: N=1 avg 76.83, N=3 77.17, N=7 77.43. The curve is flat after 1-3 examples. — [Source](https://arxiv.org/html/2412.12522)
- **Weak non-standard evidence.** An access-control BIRD variant reports GPT-4o-mini rising from 17.79 zero-shot to 30.47 few-shot ([Source](https://arxiv.org/pdf/2510.07642)). A financial-subset GPT-4o study reports 59.31 zero-shot, 65.26 few-shot, and 69.48 retrieved few-shot (search snippet, [Source](https://www.mdpi.com/2076-3417/15/10/5306)). Neither is standard BIRD dev.

### Inferences
- For GPT-4o-mini with a bare prompt, expect a large gain (likely several points) from similarity-selected BIRD-train examples, given RSL-SQL's +10 for GPT-4o and DeepSeek. With an already-strong OmniSQL-style prompt (58.8 greedy), the gain is probably smaller. CHASE's −0.85 inside a strong system suggests gains shrink as other components saturate.
- Prefer masked-question or SQL-skeleton similarity (DAIL) over raw question BM25. Random examples can hurt mid-tier models (GPT-3.5 data).
- CHASE results suggest examples on the same database (schema-aware, synthetic) beat generic ones (66.75 vs 65.45). BIRD dev DBs are disjoint from train, so same-DB examples can only be synthetic. A cross-DB-only variant was not ablated.

### Gaps
- No controlled GPT-4o-mini zero-shot vs. k-shot ablation on BIRD dev found.
- DAIL selection results on BIRD are only end-to-end.
- No cross-DB vs. synthetic same-DB comparison with the same model.

## Q4. Do decomposition / plan prompts help or hurt on BIRD for small models?

### Takeaway
On BIRD, structured CoT (query-plan or divide-and-conquer) helps a single generator by about +6 over zero-shot CoT with Gemini 1.5 Pro. MAC-SQL's decomposer is worth +3.85 with GPT-4. In ensembles, each CoT variant adds only 0.65 to 1.24. No primary source shows decomposition clearly hurting GPT-4o-mini on BIRD. Refinement and self-correction are consistently the bigger lever (−3.6 to −5.2 when removed).

### Cited Findings
- **CHASE-SQL single generator (Gemini 1.5 Pro).**
  - Zero-shot CoT baseline 57.75. Query Plan CoT 63.62 (+5.87). Divide-and-Conquer CoT 63.92 (+6.17).
  - With query fixer: baseline 61.58, QP 65.51, DC 65.77.
  - In the full system: without QP −0.65, without DC −1.24, without query fixer −3.78.
  - [Source](https://arxiv.org/html/2410.01943)
- **MAC-SQL + GPT-4.**
  - Without Decomposer: 59.39 → 55.54 (−3.85). Simple 65.73 → 61.51, moderate 52.69 → 48.82, challenging 40.28 → 38.89.
  - Without Refiner: 54.76 (−4.63).
  - BIRD dev run cost: about 10M tokens.
  - [Source](https://arxiv.org/html/2312.11242)
- **MAC-SQL + GPT-4o-mini.** 50.6 on BIRD dev, as reported in 2510.14296 (below E-SQL 56.6 and Solid-SQL 58.9 in the same table). The multi-agent decomposition pipeline transfers poorly to 4o-mini. — [Source](https://arxiv.org/html/2510.14296)
- **DIN-SQL + GPT-4.** 50.7 BIRD dev vs. plain GPT-4 46.2 ([Source](https://arxiv.org/html/2412.12522)). Its stage-wise ablations are on Spider with CodeX ([Source](https://arxiv.org/abs/2304.11015v3)). DIN-SQL's linker has low recall: 63.58 recall / 11.11 FPR ([Source](https://arxiv.org/html/2510.14296)).
- **E-SQL (GPT-4o-mini).**
  - Question enrichment, a form of question rewriting and decomposition with an explicit reasoning plan: removing it costs −1.89 (61.60 → 59.71).
  - In the basic pipeline: QE→G 58.80 vs. G 57.69 (+1.11).
  - SQL refinement is the larger lever: 58.03 without it.
  - [Source](https://arxiv.org/html/2409.16751)
- **Alpha-SQL (SDS, Qwen-7B).** Question rephrasing −0.7 when removed, SQL revision −1.8. Divide-and-conquer was not ablated. — [Source](https://arxiv.org/html/2502.17248)
- **MCTS-SQL (GPT-4o-mini).** Removing the MCTS-Refiner costs −5.19 (63.15 → 57.96). This is the largest component for 4o-mini. — [Source](https://arxiv.org/html/2501.16607v1)
- **Decomposition and fine-tuned small open models.** For DTS-SQL (decomposition plus fine-tuning, which helps small open models), only secondary summaries were found ([Source](https://arxiv.deeppaper.ai/papers/2402.01117v1)).

### Inferences
- For GPT-4o-mini, lightweight planning (E-SQL question enrichment, a QP or DC CoT inside one call) gives about +1 to +2. Heavy multi-agent decomposition (MAC-SQL at 50.6 with 4o-mini, DIN-SQL) underperforms simpler direct-generation pipelines plus refinement (E-SQL 61.6, MCTS-SQL 63.15).
- Decomposition's main benefit appears to be diversity of candidates for selection, as in CHASE, more than single-shot accuracy.

### Gaps
- No primary evidence on QPL (Query Plan Language) on BIRD dev was retrieved.
- No paper found that ablates DIN-SQL- or MAC-SQL-style decomposition specifically with GPT-4o-mini.
- No direct "decomposition hurts small proprietary model" BIRD result found.

## Q5. Reported GPT-4o-mini results on BIRD dev, their pipelines, and cost / latency per technique

### Takeaway
GPT-4o-mini BIRD dev results range from about 46 (bare single call) to 58.8 greedy / 61.5 majority (OmniSQL prompt), 61.6 (E-SQL) and 63.15 (MCTS-SQL). Gains above about 59 come mainly from refinement, self-correction and candidate selection, not from linking. Cost data is sparse. RSL-SQL is the only paper with clean token and dollar totals.

### Cited Findings
- **OmniSQL (2503.02240) baseline table.**
  - GPT-4o-mini: greedy 58.8, majority vote 61.5.
  - GPT-4o: 61.9 / 64.0. GPT-4-Turbo: 62.0 / 63.6. DeepSeek-V3: 63.2 / 63.8.
  - OmniSQL-7B: 63.9 / 66.1. OmniSQL-32B: 64.5 / 67.0. Qwen2.5-Coder-32B: 64.5 / 67.0.
  - Prompt: CREATE TABLE DDL with per-column comments (description, two representative values, question-relevant matched values).
  - [Source](https://arxiv.org/html/2503.02240)
- **E-SQL + GPT-4o-mini.**
  - 61.60 dev (59.81 test). Pipeline: question enrichment, candidate predicate generation, SQL refinement, no schema filtering.
  - With GPT-4o: 65.58.
  - [Source](https://arxiv.org/html/2409.16751)
- **MCTS-SQL + GPT-4o-mini.** 63.15 dev (61.39 in its "text EX" column). Pipeline: selector, direct generator with few-shot, and an MCTS refiner. — [Source](https://arxiv.org/html/2501.16607v1)
- **Other GPT-4o-mini numbers (from 2510.14296).**
  - Solid-SQL 58.9* and MAC-SQL 50.6.
  - E-SQL 56.6, which conflicts with E-SQL's own 61.60. The listed number may come from a different configuration.
  - Bidirectional retrieval single call: 51.11. Full schema: 45.70. Oracle schema: 56.84.
  - [Source](https://arxiv.org/html/2510.14296)
- **Alpha-SQL, ReFoRCE, SQL-o1.** No GPT-4o-mini rows were found in Alpha-SQL. ReFoRCE and SQL-o1 GPT-4o-mini numbers were not retrieved. — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- **Cost and latency.**
  - RSL-SQL full BIRD dev run: 21.90M input + 0.73M output tokens. That is $62.06 with GPT-4o vs. $3.27 with DeepSeek, about $0.04 per question with GPT-4o over 1534 questions. — [Source](https://arxiv.org/html/2411.00073)
  - MAC-SQL + GPT-4: about 10M tokens for the BIRD dev run. — [Source](https://arxiv.org/html/2312.11242)
  - DAIL-SQL: DAIL organization costs several times fewer tokens than full-information organization at similar accuracy. Self-consistency adds only +0.4 on Spider. — [Source](https://arxiv.org/html/2308.15363)
  - CHASE-SQL: about 3 generators × 7 to 10 samples plus pairwise selection. Self-consistency over candidates 68.84, selection agent 73.01, upper bound 82.79, single query 63.01. — [Source](https://arxiv.org/html/2410.01943)
  - Alpha-SQL reports no cost, only that it ran on 8×80GB GPUs. — [Source](https://arxiv.org/html/2502.17248)

### Inferences
- An OmniSQL-style prompt with GPT-4o-mini (58.8 greedy) is already a strong base. The documented ways to go higher with 4o-mini are:
  - refinement or self-correction: E-SQL refinement worth about +3.6, MCTS-SQL refiner +5.2;
  - majority voting: +2.7 in OmniSQL;
  - question-matched value or predicate hints: about +2.
- Hard schema filtering is the most likely component to hurt, unless recall is at least ~95% with a full-schema fallback.
- Ranked expected value for a GPT-4o-mini "Ours" on BIRD dev (inference):
  1. execution-guided refinement and self-correction;
  2. sampling plus vote or selection;
  3. value / predicate retrieval;
  4. similarity-selected few-shot (if not already present);
  5. a light plan CoT;
  6. schema linking only as soft highlighting or a union with the full schema.
- Per-technique cost (inference): schema linking and decomposition add 1 to 3 LLM calls per question. Value retrieval (LSH / BM25) is near-zero LLM cost but needs an offline index build. Few-shot adds about 1-3k prompt tokens per example set. Sampling multiplies generation cost by N.

### Gaps
- No per-technique latency figures were found for any paper.
- No dollar costs were found for GPT-4o-mini pipelines.
- ReFoRCE, SQL-o1 and Alpha-SQL GPT-4o-mini rows were not found or verified.
- Solid-SQL's GPT-4o-mini 58.9 attribution conflicts with Solid-SQL's own GPT-4 attribution.
