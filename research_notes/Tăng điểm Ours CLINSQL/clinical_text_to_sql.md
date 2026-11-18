# Clinical / EHR Text-to-SQL: methods, failure modes, and score levers for CLINSQL (2023-2026)

Notes for the report writer. "Local validation split" means the official CLINSQL release checked out at `d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation` (190 tasks). I counted gold-SQL patterns with grep on the **validation split only**. The test split was not opened, so nothing here comes from tuning on test.

## Q1. What does the CLINSQL paper report (baselines, models, scores, error categories, rubric)?

### Takeaway
On CLINSQL, gpt-5-mini with CoT and two execution-feedback refinement rounds is already the best model on Execution Score (74.67 test), but its SQL Score is only 42.72. In the authors' error analysis, more than half of gpt-5-mini's failures are cohort-specification or coding errors, for example keyword heuristics used where ICD or itemid constraints were needed. A further 24% are output-schema errors. Hints that give the ICD patterns and the output column names raise validation execution score by 3 to 10 points, which shows that these two areas are the main levers.

### Cited Findings
- **Paper and data.** The paper is "Patient-Similarity Cohort Reasoning in Clinical Text-to-SQL" (Shen, Zhao, Ou, Huang, Cohan), EACL 2026 long paper. It has 633 expert-annotated tasks on MIMIC-IV v3.1 run on BigQuery, each with two tree-structured rubrics (SQL and results). GPT-5 is the judge, making binary leaf decisions with "critical-first" aggregation — [arXiv 2601.09876](https://arxiv.org/abs/2601.09876); [ACL Anthology](https://preview.aclanthology.org/ingest-eacl/2026.eacl-long.64)
- **Splits.** Validation has 190 tasks and test has 443. There are 6 domains (Diagnostic Procedures, Disease Diagnosis & Outcomes, Lab Results, Medication Management, Demographics & Admissions, Vital Signs) and 3 difficulty levels at roughly a 3:4:3 ratio. The scorer is `evaluation/clinical_rubric_scorer.py`; code is at github.com/Barryshen1/ClinSQL — [HF dataset card](https://huggingface.co/datasets/yifeis02/ClinSQL/blob/main/README.md)
- **Baselines.** There are two prompting regimes, Direct Output and CoT. Both allow up to 2 self-refinement rounds in which the question, the previous SQL and the BigQuery error are fed back. 22 models were tested: 10 proprietary (GPT-5 family, Gemini-2.5 Pro/Flash, GPT-4.1, o4-mini, Grok-4-Fast, Mistral-Medium) and 12 open (DeepSeek-R1/V3.1, Qwen3, Llama-4, SQLCoder-7B-2, MedGemma-27B, Baichuan-M2-32B) — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Test scores (SQL / Execution %).** GPT-5-mini 42.72 / 74.67 (best execution). Gemini-2.5-Pro 47.28 / 73.73. DeepSeek-R1 44.91 / 69.15 (best open model; the abstract rounds this to 69.2). SQLCoder-7B-2 gets 0% execution in every scenario. Grok-4-Fast-Non-Reasoning has high SQL Score but low Execution Score — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Scores by difficulty.** GPT-5-mini execution on validation is Easy 81.31, Medium 73.46, Hard 69.69. Gemini-2.5-Pro falls from 85.46 on Easy to 67.22 on Hard — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Error categories (60 GPT-5-mini failures, 10 per scenario).**
  - Cohort specification and coding: **54%**. Examples are ICD or itemid constraints replaced by keyword heuristics, and relaxed joins that broaden the cohort.
  - Output schema and formatting: **24%**, such as missing columns and name mismatches.
  - Aggregation and clinical statistics: **14%**, such as wrong denominators and missing normalization.
  - Other: temporal-boundary errors, and quartile buckets used where APPROX_QUANTILES percentile offsets were needed.
  — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **SQL rubric structure.** The SQL rubric has four dimensions: Patient Cohort Construction, Medical Concept Implementation, Database Integration, and Clinical Analytics. A failed **critical** node zeroes its parent. Non-critical nodes are averaged with weights 1 to 3. In a **sequential** node, an early failure short-circuits the later checks — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Results rubric structure.** Format compliance is checked first: file present, exact column names, nulls, types. Clinical plausibility, judged by value ranges, comes after. "Equivalent valid formulations" are allowed. The rubric penalizes relaxed cohort criteria, wrong columns or formats, and implausible statistics — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **SQL Score vs Execution Score.** The two correlate strongly across models (Pearson 0.86, Spearman 0.855). In 40 outliers with a large gap between the scores, about 95% had high execution but low SQL Score. The usual causes were missing exclusion criteria, incomplete temporal logic, and wrong aggregation granularity — [arXiv HTML, App. M](https://arxiv.org/html/2601.09876)
- **Schema-hinted inference (gpt-5-mini, validation).** The hints are ICD filters parsed from the gold SQL plus the expected output column names from the gold result header.
  - Execution score: Easy 79.96 → 82.74, Medium 75.63 → 85.85, Hard 69.83 → 77.03.
  - SQL Score: about +3.5 to 4.7 per tier.
  - The authors warn that the hints come from gold answers.
  - The refinement prompt says "Modify only what is necessary; preserve previously correct logic" and asks for Reasoning followed by fenced SQL.
  — [arXiv HTML, Figs 19-20](https://arxiv.org/html/2601.09876)
- **Example rubric leaf (validation, Disease Dx medium 007).** "Heart Failure Diagnosis Selection: The query must identify patients with a heart failure diagnosis using an EXISTS subquery on `diagnoses_icd` with ICD-9 ('428%') and ICD-10 ('I50%') codes." It is marked `critical: true`. Gender and age-range leaves are also critical — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation/Disease_Diagnosis_and_Outcomes/medium_level_queries/007/sql_rubric_tree.json)
- **Other validation rubric leaves.**
  - Version handling: "Correctly separates filtering logic for ICD-9 and ICD-10 codes by checking the `pr.icd_version` column" (id `icd-version-handling`).
  - Code lists: "applying appropriate `LIKE` patterns to `pr.icd_code` for both ICD-9 (e.g., '35%', '36%', '37%') and ICD-10 (e.g., '02%')".
  - Per-admission counts: "Groups data per hospitalization … include `hadm_id` … in the `GROUP BY`".
  — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation)

### Inferences
- Critical gating means one wrong cohort leaf (gender, age, or ICD set) zeroes the whole "Patient Cohort Construction" branch, which has weight 3. Getting those three leaves exactly right is worth more than polishing the analytics.
- The rubric leaves often name a **specific implementation**, for example "using `p.anchor_age BETWEEN 63 AND 73`" or "EXISTS subquery … '428%' / 'I50%'". The judge is GPT-5 and the paper allows equivalent formulations, but an LLM judge matching against a literal pattern probably favours SQL that looks like the gold. That is a reason to imitate gold conventions where nothing is lost by doing so.
- The 24% output-schema failures can be fixed without clinical knowledge. The model should copy the column names and order requested in the question exactly and avoid extra or missing columns. This is likely the cheapest gain available.

### Gaps
- I could not read the per-scenario tables (Tables 8-9) reliably because the HTML extraction scrambled the columns.
- The paper does not give a quantitative ICD-coverage analysis, for example how often the model used only ICD-10 or LIKE on long_title. The 54% category is described qualitatively.

## Q2. Clinical concept → code mapping: LIKE on long_title vs explicit code lists vs prefix patterns

### Takeaway
CLINSQL gold SQL almost never uses `long_title` text search: 1 of 190 validation queries. It uses ICD code-prefix `LIKE` patterns split by `icd_version` (116/190), and sometimes explicit `IN` lists (26/190). LLMs are poor at recalling exact codes; GPT-4 reproduces only about 34-46% of codes exactly. So the safest method is to get prefixes from a deterministic public code file (CMS ICD-9/ICD-10 hierarchies) and emit version-split prefix patterns for **both** ICD-9 and ICD-10.

### Cited Findings
- **Validation gold-SQL counts (190 queries).**
  - Code patterns: `icd_code LIKE` or STARTS_WITH in 116; `icd_code IN (...)` in 26; `icd_version` referenced in 103; `long_title` in only 1; `REGEXP_CONTAINS` in 2.
  - Other concept filters: `itemid` in 79 (labs and vitals); drug-name `LIKE` in 30.
  - Typical form: `icd_version = 9 AND pr.icd_code LIKE '36.1%'` / `icd_version = 10 AND pr.icd_code LIKE '021%'`.
  — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation)
- **Paper example (Appendix N).** ICD-10 imaging matched with `'B%'`, `'3E0%'`, `'BW%'`, `'B3%'`, and ICD-9 diagnostic radiology with `'87%'`, `'88%'`. Questions use patterns such as 410\*/I21\* — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Keyword heuristics are the top failure.** The paper's leading error is "ICD or itemid constraints replaced by keyword heuristics" — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **Possible gold-SQL inconsistency.** The validation gold contains both `pr.icd_code = '88.72'` (dotted) and `pr.icd_code = '8872'` for echocardiography. A rubric leaf says the ICD-9 code "is '88.72'" — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation)
- **LLM code recall (Soroush et al., NEJM AI 2024).** GPT-4 got the highest exact match: ICD-9-CM 45.9%, ICD-10-CM 33.9%, CPT 49.8%. All models were below 50%, and they often produced imprecise or fabricated codes — [Healthcare IT News](https://www.healthcareitnews.com/news/llms-are-not-ready-automate-clinical-coding-says-mount-sinai-study); [techchannel summary](https://techchannel.news/llms-are-highly-error-prone-when-mapping-medical-codes)
- **Earlier preprint.** A 2023 preprint found only 13% exact ICD-10-CM codes for GPT-4 and none for ICD-10-PCS — [medRxiv](https://medrxiv.org/content/10.1101/2023.07.07.23292391.full.pdf)
- **Symbolic verification reduces hallucinated codes.** Neuro-symbolic verification against a knowledge base is proposed to cut ICD-10 hallucinations. I did not verify its method in detail — [Hybrid-Code v2, arXiv 2512.23743](https://arxiv.org/pdf/2512.23743)
- **Entity retrieval for medical text-to-SQL.** CBR-to-SQL (2026, MIMICSQL) separates logical-structure retrieval from entity retrieval and normalizes entity mentions to standard codes — [arXiv 2603.05569](https://arxiv.org/html/2603.05569v1)

### Inferences
- For CLINSQL, a good design is: concept → candidate codes from CMS files by deterministic lookup (category-level prefixes, e.g. 3-character ICD-10 categories and 3-digit ICD-9 categories) → the LLM picks or confirms prefixes → the system emits `(icd_version=9 AND icd_code LIKE 'xxx%') OR (icd_version=10 AND icd_code LIKE 'Yyy%')`. This matches the gold style and the rubric wording.
- LIKE on `long_title` gives a different cohort from the prefix sets and does not match the rubric's phrasing. It is likely to fail the critical ICD leaf even when the result looks plausible.
- Prefer the **category prefix** (e.g. 'I50%', '428%') over long explicit lists of leaf codes. Gold usually checks the prefix, and long lists risk omissions.
- Unverified: MIMIC-IV stores codes without dots. If so, dotted gold forms like '88.72' match nothing. Our system should keep the undotted format (correct data) but expect rubric noise on such items.

### Gaps
- I could not fetch the official MIMIC-IV diagnoses_icd page (404), so I cannot cite the "codes without decimal" convention here. It should be checked against the d_icd_* tables in BigQuery.
- I found no published head-to-head comparison of LIKE-on-title vs prefix vs list for MIMIC-IV text-to-SQL. The evidence above is indirect.
- I found no UMLS-based text-to-SQL result on MIMIC-IV.

## Q3. Clinical knowledge injection (evidence notes, guidelines) and measured gains

### Takeaway
Knowledge injection gives the largest gains reported in this literature. EHRAgent's "medical information" module roughly doubles success on hard MIMIC-III questions (33.66 → 58.97 overall). BIRD-style evidence is reported to give about +20 points for GPT-4. Automatically generated evidence (SEED) can match human evidence. On CLINSQL, gold-derived hints worth +3 to +10 execution points set an upper bound for what correct code and column knowledge can give.

### Cited Findings
- **EHRAgent ablation (MIMIC-III).** Full system: success rate 71.58 / 66.34 / 49.70 / 49.14 on Levels I-IV, 58.97 overall. Without medical information: 68.42 / 33.33 / 29.63 / 20.00, 33.66 overall. EHRAgent also uses execution-feedback debugging and long-term memory of past successful cases with only 4 demonstrations — [EHRAgent, EMNLP 2024](https://arxiv.org/html/2401.07128)
- **BIRD evidence effect.** Reported as GPT-4 about 34.88% without evidence vs 54.89% with it. This comes from secondary summaries only; the BIRD abstract gives ChatGPT 40.08% vs human 92.96% — [Liner review](https://liner.com/review/can-llm-already-serve-as-a-database-interface-a-big); [BIRD arXiv](https://arxiv.org/abs/2305.03111)
- **SEED (automatic evidence).** SEED builds evidence from the schema, description files and values. It "significantly improves" no-evidence accuracy and sometimes beats human BIRD evidence. It also found 9.65% of BIRD dev items had no evidence and 6.84% had wrong evidence — [SEED arXiv 2506.07423](https://arxiv.org/html/2506.07423v1)
- **Mixed effect with CoT.** One review notes that ChatGPT+CoT sometimes gains little from evidence — [Liner review](https://liner.com/review/can-llm-already-serve-as-a-database-interface-a-big)
- **CLINSQL hints.** Gold-derived ICD and column hints give +2.8 / +10.2 / +7.2 execution points on Easy / Medium / Hard (validation) — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **EHRSQL 2024 shared task (MIMIC-IV demo).**
  - Leaders used fine-tuning or self-training plus abstention. Top RS(10): LG AI/KAIST 81.32, PromptMind 74.89 (agreement of a 3-model ensemble with general and medical retrievers), ProbGate 74.21.
  - The organizers name time expressions and complex SQL as the core difficulties, and table and column mappings differ between EHR databases.
  - Not directly comparable to CLINSQL, because it allows fine-tuning and abstention.
  — [EHRSQL 2024 overview](https://arxiv.org/html/2405.06673v2); [ACL](https://aclanthology.org/2024.clinicalnlp-1.62)
- **Older medical text-to-SQL.** MedT5SQL fine-tunes T5 on MIMICSQL, and a 2025 study of LLMs on MIMIC-III SQL highlights weaknesses with medical terminology — [MedT5SQL PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11233734/); [MDPI Algorithms 2025](https://mdpi.com/1999-4893/18/3/124)

### Inferences
- Under our constraints (gpt-5-mini, no fine-tuning, no patient rows), the most promising form of injection is a compact, per-question "evidence note" built from public resources, in the spirit of SEED. It would hold the CMS-derived ICD-9/10 prefix sets, the relevant itemids from d_items/d_labitems (schema metadata, not patient rows), the age convention, and the exact output column list. This approximates the gold-hint setting without leaking gold.
- The gold-hint gain is largest on Medium and Hard tasks, so knowledge injection should be prioritized there.

### Gaps
- I did not retrieve the primary BIRD ablation table, so the ~20-point figure is secondary.
- I found no published CLINSQL method other than the paper's baselines and the oracle hint setting, so there is no reported non-oracle knowledge-injection gain on CLINSQL.
- I could not find usable sources on TREQS or EHR-SeqSQL methods within the call budget.

## Q4. CLINSQL gold-SQL conventions and whether aligning with them helps

### Takeaway
Gold uses `anchor_age` almost always (181/190). About half of the tasks compute age at admission as `anchor_age + EXTRACT(YEAR FROM admittime) - anchor_year`, and the rest use bare `p.anchor_age BETWEEN a AND b`. Gender is always filtered (190/190). Percentiles use `APPROX_QUANTILES(x, 100)[OFFSET(k)]` (135 occurrences with 100 buckets, 37 with 4). `SAFE_DIVIDE`/`COUNTIF` are used for rates, and DATE/DATETIME_DIFF for durations. The rubric leaves restate these conventions literally, so aligning with them should lower judge mismatch.

### Cited Findings
- **Validation counts (190 gold queries).**

  | Pattern | Count |
  |---|---|
  | `anchor_age` | 181 |
  | `anchor_age +` (age at admission) | 99 |
  | bare `anchor_age BETWEEN` | 68 |
  | gender literal filter | 190 |
  | `hospital_expire_flag` | 79 |
  | `dod` | 8 |
  | DATE/DATETIME/TIMESTAMP_DIFF | 139 |
  | `APPROX_QUANTILES` | 108 |
  | `PERCENTILE_CONT` | 3 |
  | explicit `NTILE(n)` | 22 (n = 3, 4, 5, 10) |
  | `SAFE_DIVIDE` | 38 |
  | `COUNTIF` | 40 |
  | window functions | 71 |
  | `ROW_NUMBER` | 34 |
  | ICU dataset | 61 |
  | `COUNT(DISTINCT hadm_id)` | 25 |
  | `COUNT(DISTINCT subject_id)` | 13 |
  | `LOWER`/`UPPER` | 45 |

  APPROX_QUANTILES bucket arguments: 100 (135 occurrences), 4 (37), 2 (7), 0 (4) — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation)
- **Rubric age leaves.** They say, for example, "Filters for patients aged 84 to 94 using `p.anchor_age BETWEEN 84 AND 94`". Other leaves ask to "calculate and filter patient age at admission", which matches the computed form — [Local validation split](d:/Github/text_to_SQL/external/clinsql_official/data/splits/validation)
- **Gold conventions in the paper.** Gold uses anchor_age/anchor_year for age, DATE_DIFF for LOS, charttime filters, explicit null handling, and clinical range validation. One error category is "quartile buckets where APPROX_QUANTILES percentile offsets were needed" — [arXiv HTML](https://arxiv.org/html/2601.09876)
- **MIMIC-IV age semantics.** Patients over 89 in their anchor year have anchor_age = 91. Each subject has one anchor_year, so stays must be aligned using their dates, e.g. admittime — [MIMIC-IV patients docs](https://mimic.mit.edu/docs/IV/modules/hosp/patients.html); [PhysioNet MIMIC-IV 3.1](https://physionet.org/content/mimiciv/3.1)

### Inferences
- **Age rule.** When the question says "aged X-Y" without "at admission", use `p.anchor_age BETWEEN X AND Y`. When it mentions admission or stay context, use `anchor_age + EXTRACT(YEAR FROM admittime) - anchor_year`. Either is probably judged acceptable if the range is right, but a literal match with the leaf is safest.
- **Percentile rule.** Use `APPROX_QUANTILES(x, 100)[OFFSET(p)]` for the p-th percentile and `APPROX_QUANTILES(x, 4)[OFFSET(1..3)]` for quartiles. Do not substitute NTILE buckets unless the question asks for strata or deciles.
- **Rate rule.** Use `SAFE_DIVIDE(COUNTIF(cond), COUNT(*))` or COUNT DISTINCT at the stated unit, admission vs patient. Denominator errors (14% of failures) usually come from choosing the wrong unit of analysis.
- Always include both ICD versions with explicit `icd_version` (103/190 gold queries reference it; the rubric has an `icd-version-handling` leaf).

### Gaps
- No ablation shows that aligning with gold conventions improves the SQL Score. The support for it is the literal wording of the rubric leaves plus the oracle-hint gains.
- Validation counts may not reflect the test distribution exactly. This is expected to be similar, since the splits share domains and difficulty ratios, but I did not verify it, by design.
