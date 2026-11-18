# Pipeline structure, LLM-call budgets and ablation design in agentic Text-to-SQL (2023-2026)

## Q1. Per-question LLM call counts and cost/latency

### Takeaway
The best controlled comparison is NL2SQLBench (2026), which re-ran 10 systems under one harness. Compact pipelines with 3-8 calls reach about 60-62% correct rate on BIRD dev. Multi-candidate systems use 29-80 calls to gain about 2-8 points, and on a second domain (ScienceBenchmark) that gain often disappears. A budget of 4-7 calls fits inside the "compact" band.

### Cited Findings
- NL2SQLBench, Table 9 (BIRD dev, DeepSeek-V3; correct rate / tokens / calls / $ per query) — [NL2SQLBench, arXiv 2604.16493](https://arxiv.org/pdf/2604.16493):
  - C3-SQL: 37.94% / 27.7K / 40 / 0.0126
  - DIN-SQL: 59.97% / 19.0K / 3 / 0.0038
  - MAC-SQL: 60.82% / 7.6K / 4 / 0.0019
  - CHESS (IR,SS,CG): 63.43% / 311K / 80.6 / 0.0604
  - CHESS (IR,CG,UT): 64.28% / 341K / 41.8 / 0.0816
  - TA-SQL: 59.71% / 6.8K / 3 / 0.0017
  - GSR: 61.54% / 6.1K / 4 / 0.0015
  - E-SQL: 57.50% / 38.9K / 3 / 0.0074
  - RSL-SQL: 61.93% / 20.5K / 8 / 0.0041
  - OpenSearch-SQL: 68.19% / 113K / 28.6 / 0.0242
- With GPT-4o-mini on the same benchmark, OpenSearch-SQL scores 64.47% with 10.7 calls, RSL-SQL 60.63% with 8 calls and MAC-SQL 55.08% with 4 calls — [NL2SQLBench](https://arxiv.org/pdf/2604.16493)
- On ScienceBenchmark (DeepSeek-V3), TA-SQL leads with 59.53% using 3 calls. CHESS (IR,SS,CG) scores 45.30% with 92.6 calls and OpenSearch-SQL 37.79% with 31 calls. The authors' wording is "no universal winner"; the best method depends on both dataset and backbone — [NL2SQLBench](https://arxiv.org/pdf/2604.16493)
- NL2SQLBench's practical guide: "latency-critical applications should favor approaches with minimal LLM calls (≤5)". It contrasts CHESS (63.43%, 310K tokens, 80 calls) with MAC-SQL (60.82%, 7.5K tokens, 4 calls), a cost difference of about 40x — [NL2SQLBench](https://arxiv.org/pdf/2604.16493)
- CHESS describes itself as reaching 71.10% on BIRD test, within 2% of the leading proprietary method, with about 83% fewer LLM calls — [CHESS, arXiv 2405.16755](https://arxiv.org/html/2405.16755v3)
- CHASE-SQL setup on BIRD dev:
  - 3 generators x 7 candidates = 21 candidates per question
  - the query fixer retries up to β = 3 times
  - the pairwise selector compares candidates two at a time in both orders and skips pairs whose execution results match
  - the paper reports no total call count. My derivation: up to 210 pairs (≤420 comparisons) for 21 candidates, so the budget is well over 21 calls
  - [CHASE-SQL, arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- SDE-SQL (ACL 2026) latency on BIRD dev with Qwen2.5-72B under vLLM:
  - 35.19 s per question on average
  - per stage: schema linking about 1.3 s, pre-generation exploration about 18 s (the largest share), generation about 8.7 s, refinement about 7 s
  - on a sampled subset: 34.67 s for SDE-SQL vs 49.67 s for MAG-SQL and 38.25 s for CHESS
  - [SDE-SQL, ACL 2026](https://aclanthology.org/2026.acl-long.116.pdf)
- A vendor paper's table (SQLConductor, Qwen2.5-Coder-32B) lists about $0.109 per query for CHESS and $0.024 for DeepEye-SQL. This is self-reported — [SQLConductor, arXiv 2606.23537](https://arxiv.org/pdf/2606.23537)

### Inferences
- MAC-SQL (4 calls), GSR (4), DIN-SQL (3) and RSL-SQL (8) mark the 4-7 call target zone. They sit about 6-7 points below OpenSearch-SQL on BIRD and are competitive or better on an out-of-domain benchmark.
- Because CHASE-SQL-style pairwise selection grows quadratically with the number of candidates, a 4-7 call budget allows only about 2-3 candidates, with execution-based dedup or majority vote instead of pairwise LLM selection.

### Gaps
- I found no verified per-question call counts in primary sources for DAIL-SQL (usually described as single-call generation with retrieved few-shot examples), MAGIC, ReFoRCE, Alpha-SQL (MCTS rollouts) or OpenSearch-SQL's own paper. Only NL2SQLBench's re-runs are verified, and I did not fetch those primary papers.

## Q2. How ablations are structured and typical contribution sizes

### Takeaway
The standard format is one table: the full system, then "w/o X" rows reporting BIRD dev EX by difficulty level, with the delta. Typical drops when removing one component:
- selection: 4-7.5 points
- execution-guided fixing or refinement: 2-4 points
- value retrieval (LSH): about 3 points
- individual chain-of-thought (CoT) or few-shot generators: under 1.3 points
- schema linking: anywhere from slightly positive to harmful

### Cited Findings
- CHASE-SQL, Table 7 (BIRD dev; full system 73.01%) — [CHASE-SQL](https://arxiv.org/html/2410.01943):
  - self-consistency instead of the pairwise selector: 68.84 (−4.17)
  - ranker agent instead of the selector: 65.51 (−7.50)
  - w/o LSH value retrieval: 70.09 (−2.92)
  - w/o query fixer: 69.23 (−3.78)
  - w/o query-plan CoT: −0.65
  - w/o online synthetic few-shot: −0.85
  - w/o divide-and-conquer CoT: −1.24
- SDE-SQL, Table 1 (BIRD dev, Qwen2.5-72B; full system 67.67%) — [SDE-SQL](https://aclanthology.org/2026.acl-long.116.pdf):
  - w/o soft schema linker: −0.79
  - w/o exploration before generation: −1.96
  - w/o refinement module: −2.22
  - w/o exploration in refinement: −1.70
  - w/o target checking: −1.37
  - w/o exploration in both generation and refinement: −3.20
  - with SFT: +0.52
  - the ablation rows are split by difficulty: Simple / Moderate / Challenging
- E-SQL found that adding schema filtering lowered EX at every difficulty level, by up to 8.21% on BIRD dev, and dropped it from the final pipeline. Question enrichment helped small models: DeepSeek-Coder-7B reached 56.45% without fine-tuning — [E-SQL, arXiv 2409.16751](https://arxiv.org/abs/2409.16751)
- RSL-SQL schema linking:
  - bidirectional linking reaches 92% strict recall and cuts columns from about 76 to 13 per query
  - with GPT-4o, bidirectional linking gives the best downstream EX
  - with DeepSeek, backward-only linking is slightly better, because the extra recall adds noise
  - the system hedges by generating from both the full and the simplified schema and letting an LLM pick
  - [RSL-SQL, arXiv 2411.00073](https://arxiv.org/pdf/2411.00073)
- NL2SQLBench measures revision with these metrics: CI (Correct-Improvement), I2C (Incorrect-to-Correct), E2C (Error-to-Correct), C2I (Correct-to-Incorrect) and C2E (Correct-to-Error). Its findings — [NL2SQLBench](https://arxiv.org/pdf/2604.16493):
  - current revision mostly fails to fix SQL that runs but means the wrong thing
  - the gap between Pass@5 and the post-revision result makes selection and revision the bottleneck
  - it recommends a conservative revision policy: if the original SQL succeeded and the revision changes its results, require extra validation before accepting the revision

### Inferences
- For the thesis, report each ablation as "w/o X" with an EX delta and the change in calls and tokens, split by difficulty level. Add C2I and I2C rates for the repair and verification stages, because repair can break SQL that was already correct.

### Gaps
- I did not retrieve primary-source ablation numbers for DIN-SQL, MAC-SQL, CHESS or DAIL-SQL few-shot selection. DAIL-SQL reports that similarity-based example selection helps, but I did not verify its exact numbers.

## Q3. Which stages can be merged into a single call

### Takeaway
The evidence for merging is indirect but consistent:
- single-call methods that put linking, planning and generation in one prompt (TA-SQL, DIN-SQL in NL2SQLBench's accounting, E-SQL enrichment) stay competitive at about 3 calls
- separate schema filtering can hurt strong LLMs
- CoT-style plan variants inside the generation call add little on their own (under 1.3 points)

### Cited Findings
- NL2SQLBench: TA-SQL and DIN-SQL "deliver near-top F1 with a single call" for schema selection. It also recommends Preliminary-SQL and Few-shot CoT generation strategies "without multiple calls" for resource-constrained settings — [NL2SQLBench](https://arxiv.org/pdf/2604.16493)
- E-SQL links the schema directly by enriching the question rather than pruning it, and found explicit filtering harmful — [E-SQL](https://arxiv.org/abs/2409.16751)
- In CHASE-SQL, the query-plan and divide-and-conquer CoT generators each contribute only 0.65-1.24 points. Diversity across generators matters more than any one reasoning style — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- SDE-SQL does part of its work without the LLM: a SQLGlot-based decomposer splits the SQL into sub-queries for diagnosis. Its soft schema linker adds only 0.79 points — [SDE-SQL](https://aclanthology.org/2026.acl-long.116.pdf)

### Inferences
- A proposed 4-7 call design:
  1. Linking, decomposition and plan in one call, using a structured JSON output.
  2. Generate 2-3 candidates. Diversity comes from different prompts or temperatures, sent as parallel calls or as an n-sample request.
  3. Repair only on execution error or an empty result, at most 1-2 calls (early stop).
  4. Run verification and selection together in one call, after execution-based dedup.
- Keep every retrieval layer free of LLM calls (embedding or lexical retrieval) and switch each one on or off with a flag, so it can be ablated at no call cost.

### Gaps
- I found no paper that directly ablates "merged linking+decomposition call" vs "separate calls" while holding the backbone fixed. This is a possible thesis contribution.

## Q4. Clinical/EHR text-to-SQL specifics

### Takeaway
CLINSQL (EACL 2026) — the benchmark of 633 expert-annotated tasks on MIMIC-IV v3.1 — shows that most errors are cohort/code-set errors. Adding clinically validated ICD filters and expected output columns ("schema hints") targets these errors, and self-refinement is limited to 2 rounds driven by execution errors. This supports giving clinical dictionary and code-set RAG its own ablatable layer.

### Cited Findings
- CLINSQL benchmark:
  - 633 expert-annotated tasks on MIMIC-IV v3.1, with gold SQL executable in BigQuery
  - best results: GPT-5-mini 74.7% execution score, DeepSeek-R1 69.2% (best open model)
  - Gemini-2.5-Pro drops from 85.5% (Easy) to 67.2% (Hard)
  - [CLINSQL, arXiv 2601.09876](https://arxiv.org/abs/2601.09876v1); [ACL Anthology 2026.eacl-long.64](https://aclanthology.org/2026.eacl-long.64)
- CLINSQL evaluation protocol: Direct and CoT prompting, with up to 2 refinement rounds that feed back the previous SQL and the BigQuery error. A "Schema-Hinted" setting adds ICD filters and expected output column names. Error breakdown: cohort specification and coding 54%, output schema and formatting 24%, aggregation 14%. This comes from a secondary summary and is not checked against the PDF — [Moonlight review](https://www.themoonlight.io/review/patient-similarity-cohort-reasoning-in-clinical-text-to-sql)
- Discrepancy in model count: arXiv v1 says 22 models, the EACL version says 20 — [ACL preview](https://preview.aclanthology.org/credits/2026.eacl-long.64)
- EHRSQL context:
  - questions over MIMIC-III and eICU; the 2024 shared task moved to the MIMIC-IV demo database
  - EMR-AGENT uses a separate Code Mapping Agent
  - arXiv 2601.10020 decomposes the task into sub-tasks with on-demand tools and evaluates on EHRSQL (I saw only its abstract)
  - [EHRSQL shared task paper](https://aclanthology.org/2024.clinicalnlp-1.63.pdf); [arXiv 2601.10020](https://web3.arxiv.org/pdf/2601.10020); [FHIR-AgentBench](https://arxiv.org/html/2509.19319v1)

### Inferences
- In this domain, code-set retrieval (ICD/LOINC/itemid) likely matters more than few-shot retrieval. That makes it the key ablation for the clinical dictionary RAG layer.
- Bounding repair at 2 rounds matches CLINSQL's protocol and keeps the 4-7 call budget.

### Gaps
- I did not verify, from the CLINSQL PDF, the exact EX gain from schema hints or from refinement rounds. Its Tables should be read directly.
