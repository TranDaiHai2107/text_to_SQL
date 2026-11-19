# Official CLINSQL scoring protocol vs our adapted re-implementation

Sources used (all local paths are relative to `d:\Github\text_to_SQL`):
- PAPER = `paper baseline/2026.eacl-long.64.pdf` (EACL 2026 camera-ready; text extracted with `pdftotext -layout`; page numbers are the printed proceedings pages). arXiv 2601.09876 has only v1 (14 Jan 2026, "Accepted by EACL 2026") — [arXiv abs](https://arxiv.org/abs/2601.09876)
- SCORER = `external/clinsql_official/evaluation/clinical_rubric_scorer.py` (repo HEAD `1d819960eb3ce3ac0e9beb4e801810a05735fd58`)
- RELEASED = `external/clinsql_official/outputs/evaluation/gpt-5-mini/validation/{scoring_results.json,detailed_grading.json}` and `external/clinsql_official/outputs/inference/gpt-5-mini/validation/...`
- OURS = `src/ehrqa/clinsql/rubric_judge.py`, `src/ehrqa/clinsql/rubric_evaluation.py`, `scripts/run_validation_v10.py`, `scripts/score_execution_accuracy.py`, `docs/markdown/CLINSQL_RESULT_COMPARISON_POLICY.md`
- [GitHub README](https://github.com/Barryshen1/ClinSQL), [GitHub issues](https://github.com/Barryshen1/ClinSQL/issues)

## Q1. Exact judge: model, deployment, API version, decoding, max tokens, parsing, retries

### Takeaway
The released scorer hard-codes Azure OpenAI deployment `gpt-5-chat`, API version `2024-12-01-preview`, `temperature=0.2`, 1024 max (completion) tokens, one user message, no system prompt, no seed, no retries on failure, and a permissive parser that falls back to "score 1 if the character '1' appears anywhere in the response". The paper only says "GPT-5" and does not state temperature, seed, or number of judge runs.

### Cited Findings
- Only supported judge: `SUPPORTED_MODELS = {"gpt-5-chat": {"client": "azure", "model_name": "gpt-5-chat"}}` — SCORER L34-36; CLI `--judge-model` choices are only that key — SCORER L821.
- Azure client `openai.AzureOpenAI`; endpoint/key from `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY`; default `azure_api_version="2024-12-01-preview"` — SCORER L25-26, L101-118, L824.
- A new `AzureOpenAI` client is built for every leaf call — SCORER L326-330.
- Request: `client.chat.completions.create(model="gpt-5-chat", messages=[{"role":"user","content":prompt}], temperature=0.2, max_completion_tokens=1024)`; on any exception it retries once with `max_tokens=1024` instead; there is no other retry or backoff — SCORER L331-343.
- If both attempts raise, the "response" becomes the string `f"Error: {exc}"`, which is then parsed as a grade — SCORER L342-343, L312-320.
- Rate limit: a fixed 0.8 s gap between calls — SCORER L323-325, L344-345.
- Parsing: split the response at the first newline, take `float()` of the first token after `:` on line 1 as the score, and the text after `:` on line 2 as the explanation. On any exception the fallback is `score = 1.0 if "1" in response else 0.0` — SCORER L311-320. So a malformed answer, or an API error string, that contains the digit 1 anywhere (e.g. "ICD-10", "HTTP 401") is scored as a pass. There is also no check that the score is 0 or 1.
- Paper text says only "employing GPT-5 as the judge" and "The same GPT-5 judge issues decisions and concise rationales" — PAPER p.1372 §4.1-4.2. Appendix E lists `gpt-5-chat-2025-08-07` as the API version of the *evaluated* model "GPT-5", not as the judge config — PAPER p.1390-1391 Table 7.
- A search of the extracted paper text finds no "temperature", "seed" or judge run count for the judge. README gives only `python evaluation/clinical_rubric_scorer.py full <model_name>` and does not name the judge model, temperature, seed or runs — [README](https://github.com/Barryshen1/ClinSQL). The repo has 0 issues — [issues](https://github.com/Barryshen1/ClinSQL/issues).

### Inferences
- `gpt-5-chat` is an Azure deployment name, not a dated snapshot, so the exact model version behind the paper's judge cannot be pinned. With temperature 0.2 and no seed, even an identical setup is not deterministic.
- The permissive fallback parser and the "Error:" path bias towards 1 (lenient). Their effect on the released numbers cannot be measured: in RELEASED, none of the 4,424 leaf explanations start with "Error". But a fallback-parsed answer stores the whole raw response as the explanation, so it can't be told apart afterwards.

### Gaps
- The paper reports no judge decoding parameters, seed, judge snapshot/date, or number of repeated judge runs. Nothing on judge variance between runs was found in the paper, README or issues.

## Q2. Prompts: released code vs paper Appendix O

### Takeaway
The prompt in the released code and the prompts printed in the paper (Appendix O, Figures 25/26) are two different prompts. The released code uses one generic template for both trees. The paper shows separate SQL and Results templates that include the **gold SQL** and the **gold results**. The released inference directories contain no gold files, so running the released code on the released inputs never shows the judge gold references.

### Cited Findings
- Released template (`_build_prompt`, SCORER L280-309), the same for `evaluation_type` "sql" and "results", joined with blank lines:
  `"You are an expert clinical data QA judge assessing SQL-based answers."`, `"Follow the rubric requirements precisely. Respond with JSON on two lines:"`, `"Score: <0 or 1>"`, `"Explanation: <brief reason>"`, `"---"`, `"Rubric node requirements:\n{node.requirements}"`, `"Evaluation target: {sql|results}"`, then `"Clinical question: {query}"`, `"Model SQL:\n```sql\n{test_sql}\n```"`, optional `"Reference SQL:..."` (only if `gold_sql.sql` exists), `"Model results rows (JSON):\n{json.dumps(test_results, indent=2)}"`, optional `"Reference results rows (JSON):..."` (only if `gold_results.csv` exists), and finally `"Output strictly as: Score: <0 or 1>\nExplanation: <text>"`. The template contradicts itself: it asks for "JSON on two lines" and then for plain `Score:/Explanation:` lines.
- Gold inputs are loaded only from files named `gold_sql.sql` / `gold_results.csv` in the sample dir — SCORER L178-184. `find outputs/inference -name "gold*"` returns nothing, and the benchmark dirs store gold as `sql_NNN.sql` / `result_NNN.csv` (e.g. `data/benchmark/Diagnostic_Procedures/easy_level_queries/016/`).
- Paper Figure 25 (SQL): "You are evaluating SQL queries for clinical data analysis based on specific requirements. Evaluation Criteria: {node.requirements} Clinical Question: {query} SQL to Evaluate (fenced): {test_sql} Gold Standard SQL: {gold_sql} Instructions: 1. Evaluate if the SQL meets the specific requirement: "{node.requirements}". 2. Focus on whether the implementation satisfies the requirement, not on syntactic perfection. 3. Use the gold standard SQL as reference for best practices and expected approach. 4. Score: 1 if requirement is fully met, 0 if not met. 5. Provide a brief explanation of your assessment. Response Format: Score: [0 or 1] Explanation: [...]" — PAPER p.1410 App. O.
- Paper Figure 26 (Results): "...Results to Evaluate: {test_results} Gold Standard Results: {gold_results} Instructions: ... 2. For "CSV File Exists" requirements: if results data is shown above and not empty, it means a CSV file exists. 3. Use the gold standard results as reference for expected format and values. 4. Consider clinical plausibility, data format, and completeness. ..." — PAPER p.1410.
- Paper §4.1: the judge is used "to compare rubric text, gold SQL, and schema hints". §4.2: the judge works "by comparing the CSV with the rubric and gold references" — PAPER p.1372.
- RELEASED evidence that the paper's prompts (with gold) were used, not the released code: 2,010 of 4,424 leaf explanations mention "gold" (576/2,326 SQL leaves, 1,434/2,098 results leaves). Examples: "...matches the gold standard approach" (SQL) and "Although the data matches the gold standard values..." (results) — RELEASED `detailed_grading.json` (counted with a local script).
- RELEASED evidence of a different code path: the `csv-file-exists` leaf has the fixed explanation `"CSV file present with rows"` in all 189 samples. That string does not appear anywhere in SCORER. It is also given (score 1) to the 7 samples whose SQL failed to execute, whose CSV is just `result\n""` (12 bytes) — e.g. `outputs/inference/gpt-5-mini/validation/Diagnostic_Procedures/medium_level_queries/049/`.
- RELEASED `sample_path` values are `/mnt/c/Clinical_Benchmark/experiments_CoT/gpt-5-mini/validation/...`, which is an internal path, not the public repo layout.

### Inferences
- The paper's numbers (e.g. GPT-5-mini 42.30 / 75.16) were produced by an internal scorer that (i) put gold SQL and gold results in the prompt, (ii) used the Appendix O wording, and (iii) scored `csv-file-exists` deterministically or by a special rule. The public `clinical_rubric_scorer.py` at HEAD is not that scorer, so running the public code (even on Azure gpt-5-chat) would not reproduce the paper exactly.

### Gaps
- The internal scorer version (commit, prompt, csv-exists rule) is not public. It is unknown whether `{test_results}` was the full CSV or truncated in the internal version.

## Q3. What data the judge receives (data-egress relevance)

### Takeaway
In the official protocol, raw MIMIC-IV result rows are sent to the LLM. The **entire** predicted result CSV (all rows, no truncation) is serialized as JSON into **every leaf prompt of both trees**, the SQL tree included. Per the paper, the full gold result rows are sent as well. Our setup forbids this, which is why we can't compute the Execution Score at all.

### Cited Findings
- `files["test_results"] = pd.read_csv(result_files[0]).to_dict(orient="records")` loads all rows, with no row cap — SCORER L174-176. `_build_prompt` adds `Model results rows (JSON)` whenever `test_results is not None`, whatever `evaluation_type` is — SCORER L303-304. So SQL-tree leaves also receive the predicted rows.
- Results scoring runs only if a `result_*.csv` exists. Otherwise `results_score = 0.0` — SCORER L144-150. SQL scoring runs only if `sql_*.sql` exists.
- Every leaf is sent to the judge, including leaves that the aggregation later short-circuits (gating happens only in aggregation, not in calls) — SCORER L193-232.
- Size in practice: the largest gpt-5-mini validation predicted CSV is 176 lines (Medication_Management/hard/047). The 6 domains × 190 dirs total 833 CSV lines (`wc -l` over RELEASED inference).
- Paper Fig. 26 includes `{gold_results}` (full gold rows) — PAPER p.1410.
- Our policy: "không truyền reference/result rows cho LLM" (do not send reference/result rows to any LLM) — `docs/markdown/CLINSQL_RESULT_COMPARISON_POLICY.md` L15. The v10 authorization says "no result rows to any LLM" — `scripts/run_validation_v10.py` L240-245. Our results tree is marked `execution_status = 'UNSCORED_DATA_EGRESS'` — `scripts/run_validation_v10.py` (score() grade dict, about L292-298).

### Inferences
- An exact official SQL Score also needs rows: the official SQL-leaf prompt includes the predicted result rows. Our row-free SQL prompt is therefore a different input distribution even for the SQL tree.

### Gaps
- None for the released code. For the paper's internal scorer the exact row handling is unknown.

## Q4. Aggregation formulas, and whether ours matches

### Takeaway
Leaves are binary (0/1). Internal nodes use either "critical-first" (non-sequential nodes) or "sequential" weighted gating. Our adapted scorer subclasses and reuses the official module's tree traversal and aggregation unchanged, so aggregation is identical to the released code. Recomputing the released gpt-5-mini validation sample scores from their released leaf scores with the official functions reproduces all 189×2 scores exactly (0 mismatches). The paper's Algorithm 1 differs slightly from the code.

### Cited Findings
- Rubric node fields: `id`, `requirements`, `weight` (default 1), `sequential` (default False), `critical` (default False), `scoring` (default "1/0", parsed but never used in scoring) — SCORER L82-92.
- `_calculate_node_score`: leaf → judge score. Sequential node → `_calculate_sequential_score`. Otherwise → `_calculate_critical_first_score` — SCORER L237-243.
- Critical-first: if any critical child scores < 1.0, return 0. If there are no non-critical children, return 1.0. Otherwise return the weighted mean of the non-critical children (weights = child `weight`; total weight 0 → 1.0) — SCORER L245-262. Critical children do not enter the mean.
- Sequential: iterate children in order, accumulating `weight*score` and `weight`, and `break` after the first child with score < 1.0. Return weighted_sum/total_weight over the children **evaluated so far** (skipped children are excluded from the denominator, not counted as 0). Critical flags are ignored inside sequential nodes — SCORER L264-275.
- Per-split metric = unweighted mean over samples of `sql_score` and `results_score`, rounded to 6 decimals — SCORER L475-489. RELEASED gpt-5-mini validation: `average_sql_score 0.422969`, `average_results_score 0.751649`, `total_samples 189`. This matches paper Table 4 validation 42.30 / 75.16 (test 42.72 / 74.67) — PAPER p.1373 Table 4 and p.1397-1398 Tables 8/9.
- Paper Algorithm 1 (PAPER p.1371): leaf → "LLM judge evaluation score ∈{0,1}". For critical children, "if score[c] ≠ 1 then return 0". If there are no non-critical children, return 1. Then a loop over **non-critical** children computes sum += W[c]·score[c] and total_weight += W[c], with "if S[c] = true ∧ score[c] = 0 then break"; return sum/total_weight. Paper prose: weights 1-3 (1 supportive, 2 standard, 3 critical elements) — PAPER p.1371.
- OURS: `CheckpointedScorer(native)` subclasses the verified official class loaded via `load_verified_native_scorer`. It overrides only `__init__`, `score_sample` (adds validation), `_load_sample_files` (requires files), and `_evaluate_leaf` (routes through our judge/ledger). It inherits `_evaluate_tree`, `_build_prompt`, `_calculate_*`, and uses the official `_build_split_summary` / `_build_scenario_breakdown` — `src/ehrqa/clinsql/rubric_evaluation.py` L128-212. The row-free path `score_sql_without_results` calls the official `_evaluate_tree` and `_calculate_score` — L149-164.
- Consistency check (our script, read-only): rebuilding each released sample's tree from `outputs/inference/gpt-5-mini/validation/.../{sql,results}_rubric_tree.json`, inserting the released leaf scores, and applying the official `_calculate_score` gave 0 SQL and 0 results mismatches over 189 samples. Leaf scores are strictly binary: 2,939 ones and 1,485 zeros out of 4,424 leaves.

### Inferences
- Aggregation is not a source of difference between our scores and the official ones. The differences come from the judge and its inputs.
- Paper vs code: in the paper, gating depends on the *child's* sequential flag and on score = 0, and it applies only among non-critical children. In the code, gating depends on the *parent's* `sequential` flag and on score < 1, and critical flags are ignored under sequential parents. With fractional child scores these can give different results. The released numbers match the code's formula, not necessarily Algorithm 1.

### Gaps
- None material.

## Q5. Judge validation against humans and run variance

### Takeaway
The paper reports one human-GPT agreement study (100 sampled validation/test examples, 2 annotators) at leaf level and pass/fail level. GPT-5 vs annotator agreement is about 82-87% at the leaf level. No run-to-run judge variance, seed, or repeated-run results are reported.

### Cited Findings
- Appendix K: "We randomly sample 100 CLINSQL validation/test examples and re-score them with two medically trained annotators ... independently evaluate rubric leaf nodes for the SQL and results trees ... without access to GPT-5 scores" — PAPER p.1402.
- Table 13 (columns: Leaf SQL / Leaf results / Pass-fail SQL / Pass-fail results; the pdftotext layout is shifted, so the row assignment is my reconstruction): GPT-5 vs Annotator 1 = 83.4 / 87.1 / 90.2 / 92.3. GPT-5 vs Annotator 2 = 82.1 / 85.9 / 88.7 / 91.0. Annotator 1 vs Annotator 2 = 86.8 / 89.5 / 92.4 / 94.1 — PAPER p.1402. The paper says disagreements "are largely concentrated in borderline, partial-credit cases, and do not materially change relative model rankings". No kappa is given for the judge.
- "Pass/fail" is not defined numerically in the paper (no threshold is stated).
- Appendix L (rubric/gold IAA, not about the judge): gold SQL double-annotation 46/50 identical results (92%), 3/50 near-miss, 1/50 distinct. Rubric leaf presence and criticality agreement 91%, Cohen's κ = 0.82. Critical-first pass/fail agreement 47/50 (94%). Validators accepted 87% as-is, 9% with minor edits, 4% major/reject — PAPER p.1402-1403 Table 14.
- Appendix M: across models, Pearson r = 0.8597 and Spearman ρ = 0.8554 between SQL Score and Execution Score. 40 sampled outliers with a gap of at least 20 points: about 95% have high Exec and low SQL — PAPER p.1403-1404.

### Inferences
- About 13-18% leaf-level disagreement with humans means a different judge (gpt-5-mini) can shift scores by several points without either judge being "wrong". There is no published variance estimate to use as a tolerance band.

### Gaps
- No judge temperature/seed/repeat study. No agreement figures were published for gpt-5-mini or any other judge.

## Q6. Is our Execution Accuracy (strict EX) related to anything in the paper?

### Takeaway
No. The paper's "Execution Score" is the LLM-judged results-rubric score (format + plausibility/acceptable-range checks). It is not a match against the gold result table. Our strict/relaxed EX is a separate, supplementary deterministic metric. The paper uses "identical result tables" only in its manual IAA study.

### Cited Findings
- §4.2: "The execution-level evaluation examines CSV outputs ... Format compliance is first enforced, including file presence, exact column names, absence of nulls, and basic type checks; clinical plausibility is then assessed using per-column value ranges ... Plausible bands admit clinically equivalent answers, whereas acceptable bands tighten tolerance" — PAPER p.1372. Example leaves: `Clinically Plausible ([0, 10])`, `Acceptable Range ([1, 3])`, `Primary Column Exists (e.g., percentile_75th_ecg_telemetry, p75_ecg_count)` — `external/clinsql_official/data/benchmark/Diagnostic_Procedures/easy_level_queries/016/results_rubric_tree.json`. In that tree, the Output Format group has weight 1 and the Output Feature group has weight 2, both sequential.
- Our `ex_strict`: same row and column counts, unordered multiset row equality, column names ignored, numeric tolerance 1e-8 + 1e-6·|x|, NULL equals only an empty reference cell. `ex_relaxed`: maps each reference column by values to a distinct predicted column. The docstring calls it "a supplementary metric, not the official CLINSQL Execution Score" — `scripts/score_execution_accuracy.py` L1-19, L50-98.
- Official gpt-5-mini validation predictions score 0/189 on our strict EX (figure supplied by the caller from our earlier run; not re-run here) but 75.16 official Execution Score. Example from RELEASED: the judge's own explanation says the values "match the gold standard" while it still fails `primary-column-exists` and `clinically-plausible`. The official score gives partial credit and is far more lenient than exact match, and failed executions still get about 0.167 (from the csv-exists leaf).

### Inferences
- The two metrics measure different things and are not comparable. The 0 vs 75 gap is expected, not a bug.

### Gaps
- I did not check why strict EX is exactly 0 for all official predictions (e.g. CSV encoding or float formatting of released CSVs). It is worth a sanity check that the released CSV formatting (pandas output) and our CSV reader agree.

## Q7. Complete list of differences: official scoring vs ours

### Takeaway
Our aggregation and tree traversal are byte-for-byte the official code. Every other component differs: judge model, decoding, parser and retries, inputs (no rows, no gold), and coverage (no Execution Score). On top of that, the released code itself differs from the paper's internal scorer. Exact reproduction of 42.30/75.16 is impossible for three reasons: the judge deployment and internal prompt are not public, MIMIC rows can't leave our environment, and judge decoding is not deterministic.

### Cited Findings (tagged)
- (a) judge model — Official: Azure deployment `gpt-5-chat` (SCORER L34-36); paper calls it "GPT-5" (PAPER p.1372). Ours: OpenAI public API `gpt-5-mini-2025-08-07`, pinned snapshot, endpoint `https://api.openai.com/v1`, `models.retrieve` check and returned-model equality check (`rubric_judge.py` L112-120, L160-164, L202; `run_validation_v10.py` L138-140). A judge that is smaller and also the same family as the evaluated model (gpt-5-mini) adds possible self-preference bias.
- (a) API surface — Official: Azure, api_version `2024-12-01-preview`. Ours: OpenAI v1 Chat Completions (`rubric_judge.py` L136-137, L151-157).
- (b) decoding — Official: `temperature=0.2`, max_completion_tokens 1024 (fallback max_tokens 1024) (SCORER L331-338). Ours (v10): no temperature (reasoning models reject non-default values), `adapted_max_completion_tokens=None` so no token cap, `store=False`, and `reasoning_effort` not set (None → provider default; the caller describes this as medium) (`rubric_judge.py` L89-103; `run_validation_v10.py` L138-140). Ours also requires `finish_reason == 'stop'` and no refusal before accepting text (`rubric_judge.py` L202-206).
- (b) retries/failure — Official: one alternate-parameter retry. An API error becomes the text "Error: ..." and gets graded (pass if it contains "1"). Ours: fail-closed. `LeafLedger` retries only RATE_LIMITED and (v10) INVALID_JUDGE_RESPONSE, up to `retry_limit=3` with exponential sleep `2**attempt`. Otherwise the leaf, and so the sample, is INCOMPLETE and not silently scored (`rubric_evaluation.py` L15-93; `run_validation_v10.py` judge ledger lines about L266-268). Ours also uses a 60 s timeout and `max_retries=0` on the SDK (`rubric_judge.py` L152-157).
- (b/e) parsing — Official: lenient split plus a `"1" in response` fallback (SCORER L311-320). Ours: `parse_grade` requires exact `Score: [01]\nExplanation: ...` (`rubric_judge.py` L23-28). v10 uses `parse_adapted_grade`, which accepts fenced, JSON, one-JSON-per-line, and markdown-bold variants but rejects ambiguous text (L31-69). It never uses the digit-search fallback.
- (c) inputs, SQL tree — Official released code: rubric leaf + question + model SQL + **all predicted result rows** (+ gold SQL/gold rows only if `gold_*` files exist; they don't in the released dirs) (SCORER L163-186, L280-309). Paper: rubric + question + model SQL + **gold SQL** (Fig. 25). Ours: rubric + question + model SQL only (`score_sql_without_results`, `rubric_evaluation.py` L149-164). Ours actively rejects samples containing `gold_sql.sql` or `gold_results.csv` (`UNEXPECTED_REFERENCE_FILE`, L110-111).
- (c) inputs, results tree — Official: predicted rows (+ gold rows per paper Fig. 26). Ours: not scored (`UNSCORED_DATA_EGRESS`).
- (d) aggregation — Identical to the released code (inherited methods; verified with 0/378 recompute mismatches on RELEASED). Both differ from paper Algorithm 1 on the sequential-gating condition (parent flag and score < 1 in the code, vs child flag and score = 0 in the paper).
- (d) coverage/denominator — Official released summary averages over **189** validation samples. `Vital_Signs_Monitoring/easy_level_queries/012` has full inference files and rubrics but is absent from RELEASED `scoring_results.json` for gpt-5-mini, gpt-5-chat and gemini-2.5-pro, although the released `iter_samples` would include it (SCORER L393-419). Ours scores all 190 validation questions (`scripts/run_validation_v10.py` authorization text) and keeps INCOMPLETE cases explicit instead of averaging (`rubric_evaluation.py` L186-212). Official missing-result rule: results_score 0 if no CSV (SCORER L149-150).
- (e) prompts — Ours uses the released `_build_prompt` text unchanged (inherited), not the paper's Appendix O templates. The paper's internal prompts (Fig. 25/26, with gold references and a CSV-exists instruction) differ from both.
- (e/g) csv-file-exists — Official released outputs use the fixed explanation "CSV file present with rows" for all 189, including failed executions with a placeholder CSV `result\n""`. That rule is absent from the public code. Ours: not applicable (no results tree).
- (f) data/egress — Official sends raw predicted MIMIC-IV result rows (and, per paper, gold rows) to Azure OpenAI for every leaf of both trees. Ours sends no rows to any LLM (`CLINSQL_RESULT_COMPARISON_POLICY.md` L15; v10 authorization). Ours also sets `store=False`.
- (g) Execution metric — Official "Execution Score" = LLM-judged results rubric. Ours replaces it with deterministic local `ex_strict` / `ex_relaxed` against gold CSV (`scripts/score_execution_accuracy.py`). These are different constructs.
- (g) labels — Ours labels adapted scores `ADAPTED_CLINSQL_SQL_SCORE` / `ADAPTED_CLINSQL_EXECUTION_SCORE` to keep them distinct from official numbers (`rubric_evaluation.py` L192-194). Ours also has a NATIVE mode that replicates the official Azure settings (`gpt-5-chat`, temperature 0.2, 1024 tokens, api 2024-12-01-preview; `rubric_judge.py` L91-92, L105-111, L151-155), but it was not used.
- (g) determinism/provenance — Official: no seed, temperature 0.2, unversioned deployment, new client per call. Ours: hash-pinned config/prompt/sample per leaf in a SQLite ledger with resume (`rubric_evaluation.py` L172-181). That makes it reproducible as a record, but sampling is still nondeterministic.

### Inferences
- Even a perfect replication of the public code (NATIVE mode on Azure `gpt-5-chat`) would not reproduce the paper exactly. The published numbers come from a different internal scorer (gold references in the prompts, a special csv-exists rule, 189-sample denominator), and Azure `gpt-5-chat` may have changed.
- For the thesis: our "Adapted SQL Score" is best described as "official rubric trees + official aggregation, judged by gpt-5-mini on a row-free, gold-free prompt". It should only be compared within our own experiments (all methods judged the same way), never number-to-number with Table 4.
- A cheap way to calibrate the absolute offset of our judge without sending any rows: re-score the released official gpt-5-mini *SQL* outputs with our adapted row-free judge, then compare with the released per-sample `sql_score` (mean 42.30) and per-leaf agreement against RELEASED leaf decisions. This uses only released model SQL. Note that the official SQL prompt also had rows (and, per the explanations, gold), so the offset combines judge and input effects.

### Gaps
- The internal scorer that produced the released and paper numbers is unpublished. I found no statement explaining the missing sample 012 or the csv-exists rule.
- I could not confirm from the paper whether `{test_results}` in the internal prompt was full or truncated.
