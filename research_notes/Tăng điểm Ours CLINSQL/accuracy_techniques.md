# Fixed-model, low-call-count accuracy techniques for LLM Text-to-SQL (2024-2026)

Scope: no fine-tuning, fixed LLM (gpt-5-mini, reasoning=medium), about 2-4 calls per question, no ReAct loops, no patient rows sent to the LLM. Numbers are execution accuracy (EX, %) unless stated. "Derived" means my own subtraction from reported figures.

## 1. Which prompting/generation techniques give the largest gains for a fixed model?

### Takeaway
Under controlled single-model ablations, three things give the largest gains. First, structured decomposition in one call (divide-and-conquer or query-plan CoT): about +6 EX on Gemini-1.5-Pro and about +9.4-9.8 EX on o4-mini. Second, relevant few-shot examples: +4.8 EX in MCS-SQL, and online synthetic examples +9.3 EX in CHASE-SQL. Third, an execution-based query fixer: +1-4 EX. Multi-candidate generation plus selection adds a further +2 to +6 EX but needs many calls (20-100 candidates). Most of that gain disappears below about 5 candidates, unless the candidates come from diverse prompts and the final pick uses a selector rather than majority vote.

### Cited Findings
**CHASE-SQL (ICLR 2025, Gemini-1.5-Pro, BIRD dev)**
- Single-generator ablation (no fixer to with fixer): baseline zero-shot CoT 57.75 to 61.58; Query-Plan CoT 63.62 to 65.51; Divide-and-Conquer CoT 63.92 to 65.77; Online Synthetic examples 67.09 to 68.02 — [CHASE-SQL arXiv](https://arxiv.org/html/2410.01943v1)
  - So in a single call, DC-CoT is +6.17 and QP-CoT +5.87 over the baseline. The query fixer adds +3.83 to the baseline but only +0.9-1.9 once a structured CoT is in place (derived).
- Full-system ablation (73.01): self-consistency instead of the trained selection agent gives 68.84 (−4.17); w/o query fixer 69.23 (−3.78); w/o LSH value retrieval 70.09 (−2.92); w/o DC 71.77 (−1.24); w/o OS 72.16 (−0.85); w/o QP 72.36 (−0.65) — [CHASE-SQL](https://arxiv.org/html/2410.01943v1)
- Single query 63.01 vs self-consistency 68.84 (+5.84) vs oracle upper bound 82.79 (+19.78). The pool is 21 candidates (7 per generator), and gains plateau at about 20 candidates. The fixer allows up to 3 attempts — [CHASE-SQL](https://arxiv.org/html/2410.01943v1)
- Pairwise selection accuracy with an untuned LLM is low: Claude-3.5-Sonnet 60.21, Gemini-1.5-Pro 63.98, against 71.01 for a fine-tuned Flash. So an off-the-shelf LLM-as-selector is only modestly better than chance on hard pairs — [CHASE-SQL](https://arxiv.org/html/2410.01943v1)
- The paper reports no per-query cost, call counts or latency (flag) — [CHASE-SQL](https://arxiv.org/html/2410.01943v1)

**Rethinking Agentic Workflows (arXiv 2510.10885, BIRD Mini-Dev, 500 questions)**
- o4-mini (reasoning model): CoT+ReAct baseline 51.6; DC+ReAct 61.0; DC 3-shot+ReAct 61.4; DC 3-shot ×5 parallel (majority vote) 62.6; DC 3-shot+Verification 59.4; Retrieval+DC 3-shot 60.6 — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- Gemini-2.5-Flash: 62.8 to 65.0 (DC 3-shot). GPT-4o: 55.0 to 60.0. Gemini-1.5-Flash: 54.6 to 59.8 — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- Latency for o4-mini: baseline 11.45 s; DC 3-shot 17.12 s; ×5 parallel 15.57 s; verification 26.68 s (the slowest, and it lowers accuracy). Tokens for o4-mini: baseline 4.60k in / 0.74k out; DC 3-shot 5.02k / 1.35k — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- Error analysis: "Wrong Query Logic" is the dominant failure. Retrieval increased schema-linking errors for o4-mini (10.4% to 12.2%). The paper's text and tables disagree on several numbers (flag) — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)

**MCS-SQL (COLING 2025, GPT-4, BIRD dev, cumulative ablation)**
- Zero-shot 50.7; + schema linking 52.8 (+2.1); + sample table contents 55.2 (+2.4); + few-shot by masked-question similarity 60.0 (+4.8); + multi-choice selection over 20 samples from 1 prompt 62.1 (+2.1); 5 prompts × 20 samples 63.4 (+1.3) — [MCS-SQL](https://arxiv.org/html/2405.07467v1)
- Few-shot selection: random 57.0; question similarity 59.3; masked-question similarity 60.0 — [MCS-SQL](https://arxiv.org/html/2405.07467v1)
- Selection: majority vote 62.8; MCS without confidence filter 62.5; MCS with confidence filter 63.4. LLM multiple-choice gives only +0.6 over majority vote — [MCS-SQL](https://arxiv.org/html/2405.07467v1)
- Schema-linking recall: single prompt, greedy 61.3; single prompt, 20 samples 77.1; multiple prompts 89.8. Cost is high: up to 100 SQL candidates per question, and no cost is reported — [MCS-SQL](https://arxiv.org/html/2405.07467v1)

**DAIL-SQL (VLDB 2024)**
- Selects examples by question similarity plus SQL-skeleton similarity and drops cross-domain knowledge to save tokens. It reaches Spider test 86.2 (GPT-4), or 86.6 with self-consistency voting, at about 1,600 tokens per question — [DAIL-SQL GitHub](https://github.com/beachwang/dail-sql); [VLDB paper](https://www.vldb.org/pvldb/vol17/p1132-gao.pdf)
- I could not reliably read the per-strategy ablation (random vs question-similarity vs masked vs DAIL), because the extracted table was garbled. Verify in the paper (gap).

**RSL-SQL (bidirectional schema linking, BIRD dev, GPT-4o)**
- 67.21 EX. Bidirectional linking (forward LLM pick plus backward extraction of the columns a preliminary SQL uses) gives a strict recall of 92% (94% with about 83% fewer columns, in a later version) — [RSL-SQL](https://arxiv.org/html/2411.00073v1); [v2 PDF](https://arxiv.org/pdf/2411.00073v2)
- With GPT-4o, bidirectional beat forward-only and backward-only. With DeepSeek, backward-only was slightly better, because bidirectional adds noise — [RSL-SQL](https://arxiv.org/html/2411.00073v1)

**"The Death of Schema Linking?" (2024)**
- Newer models use relevant schema elements well even when irrelevant ones are present. Skipping schema linking when the full schema fits in context, and relying on augmentation, selection and correction, reached 71.83 on BIRD (first at the time). The abstract gives no per-component numbers — [arXiv 2408.07702](https://arxiv.org/abs/2408.07702)

**ReFoRCE (Spider 2.0, o1-preview)**
- Self-refinement, format restriction, column exploration, 3 parallel threads with result voting: Snow 31.26, Lite 30.35 (v3), against Spider-Agent 23.58 / 23.03. The v1 preprint reported 26.69 / 24.50. There is no per-component ablation (flag) — [ReFoRCE v3](https://arxiv.org/html/2502.00675v3)
- Voting rule: compare the 3 threads' results programmatically first, and fall back to the LLM judging the results only if unresolved. Within a run, stop when the same "reasonable" result appears twice. Empty or all-zero results don't count as votes — [ReFoRCE](https://arxiv.org/html/2502.00675v3)

**Alpha-SQL (ICML 2025)**
- Zero-shot MCTS with a 32B open model reaches 69.7 on BIRD dev, +2.5 over the prior best zero-shot (GPT-4o based). The reward is self-consistency of execution results across high-temperature samples. It uses many calls, so it is not low-budget — [Alpha-SQL](https://arxiv.org/html/2502.17248v2); [PMLR](https://proceedings.mlr.press/v267/li25dt.html)

**BAPPA (arXiv 2511.04153, BIRD Mini-Dev, open models)**
- A Planner-Coder pipeline (a reasoning model plans, a coder writes SQL) lifts Gemma-3-27B from 52.4 to 56.4, Qwen2.5-7B from 32.2 to 45.8, and Gemma-3-4B from 32.0 to 48.2. Multi-agent discussion plateaus after round 2 and can hurt: Qwen2.5-Coder-14B fell from 49.6 zero-shot to 39.0. The abstract's claims don't match its tables (flag). No cost figures are given — [BAPPA](https://arxiv.org/html/2511.04153v1)

**XiYan-SQL / OmniSQL**
- XiYan-SQL appears at 73.3 on BIRD in Alpha-SQL's comparison table, but it uses fine-tuned models, so it is not applicable here. I could not verify OmniSQL's numbers in this session (gap) — [Alpha-SQL table](https://arxiv.org/html/2502.17248v2)

### Inferences
- Under a 2-4 call budget, the best-supported stack for a fixed reasoning model is:
  - Call 1: one structured generation call with DC or query-plan CoT and 3 retrieved examples (about +6-10 EX in two independent studies, including o4-mini).
  - Call 2: execution-error-driven fixing (+1-4 EX; it gives the most when the base prompt is weak).
  - Calls 3-4, optional: one or two extra candidates from a *different* prompt style (e.g., QP-CoT vs DC-CoT), resolved by an execution-result agreement rule.
- An LLM verifier or judge call on top of a reasoning model is the weakest use of an extra call: it hurt o4-mini by −2.0 EX and added +9.6 s latency.
- Example selection by masked-question or skeleton similarity beats random by about +3 EX (MCS-SQL). Synthetic examples generated from the schema (CHASE OS) gave the single largest one-call gain (+9.34), and they need no patient rows (only schema, and SQL can be generated synthetically).

### Gaps
- No source reported per-question dollar cost for CHASE-SQL, MCS-SQL or ReFoRCE.
- I found no per-component ablation for ReFoRCE.
- I did not retrieve E-SQL (question enrichment) numbers.
- I did not retrieve or verify the OmniSQL and XiYan-SQL papers.

## 2. Which techniques fix output-shape mismatch and wrong cohort definitions?

### Takeaway
The most direct evidence-backed fix for output shape is ReFoRCE's "format restriction": declare the expected answer columns and rows up front, then re-check them during refinement. It is described qualitatively, with no isolated gain number. For cohorts, the evidence points to decomposition (DC/QP-CoT, where sub-questions map naturally to cohort CTEs), schema-only planning, and execution-feedback checks on result shape. No paper isolates "cohort-definition accuracy" as a metric.

### Cited Findings
- ReFoRCE format restriction: the prompt asks the model to state the expected answer format first, as CSV-style with each column explicitly defined and one record per row. It handles special cases (superlatives, percentages, coordinates, "answer in one row" for single-max questions), and self-refinement reinforces it. Spider 2.0 tolerates extra columns — [ReFoRCE](https://arxiv.org/html/2502.00675v3)
- Strict EX variants require identical result dimensions and a unique content match for every column in both directions. Under these, any extra or missing column fails — [arXiv 2506.09359](https://arxiv.org/pdf/2506.09359v1)
- BIRD-style scorers compare positional value tuples and ignore column names. So a fused or extra "helpful" column breaks equality even when the content is right (practitioner blog, not peer-reviewed) — [DEV Community](https://dev.to/omer_hochman/your-llm-fused-the-two-columns-you-asked-for-and-the-eval-marked-it-wrong-5gge)
- Execution accuracy itself has an 11.3% false-positive and 13.9% false-negative rate, against 0.1% / 2.6% for ESM+ — [Ascoli et al., arXiv 2407.07313](https://arxiv.org/abs/2407.07313v2)
- Soft execution F1 and execution precision/recall have been proposed to separate over-prediction (extra columns or rows) from under-prediction — [arXiv 2506.13785](https://arxiv.org/html/2506.13785v1); [Polytechnique Montréal thesis](https://publications.polymtl.ca/71174/36/2025_MohammadhosseinMalekpour.pdf)
- In the agentic-workflow study, Soft-F1 consistently exceeds EX by 3-5 points for o4-mini (e.g., 61.4 EX vs 65.53 Soft-F1). That is a sizable share of answers that are partially right, as in shape or row mismatches — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- Clinical context: on CLINSQL (633 MIMIC-IV tasks, EACL 2026), GPT-5-mini reportedly scores about 74.7% test execution score, the top result. I only saw this via a search snippet/aggregator, not the paper's table (flag) — [ACL Anthology preview](https://preview.aclanthology.org/credits/2026.eacl-long.64); [benchmarklist](https://benchmarklist.com/benchmarks/patient_similarity_cohort_reasoning_in_clinical_text_to_sql/)
- CELEC sends schema-only metadata to the LLM (o3) and executes SQL locally. It reports EHRSQL-subset EX "comparable to prior systems", with no number in the snippet — [CELEC](https://arxiv.org/html/2511.00772v1)
- EMR-AGENT reports cohort-selection F1 0.940 on MIMIC-III, but it iterates against the live DB, which the constraints rule out — [EMR-AGENT notes](https://en.papernotes.org/ICLR2026/medical_nlp/emr-agent_automating_cohort_and_feature_extraction_from_emr_databases/)

### Inferences
- Zero-call fix for shape: have the generation call emit a structured "answer contract" (output column list with semantics, row granularity such as one row per patient or a single row, units and percent conventions) before the SQL. Then deterministically compare the executed result's column count and names and its row count against the contract, using only result shape, never rows. This is ReFoRCE's format restriction adapted to the privacy constraint.
- One-call fix: if the shape check fails, feed back only the error class and the shape diff (expected vs actual columns, row count) to a repair call. This is consistent with CHASE's fixer (+1.9-3.8 EX) but targets shape errors.
- Cohort definitions: DC-CoT that forces one sub-question or CTE per inclusion/exclusion criterion fits the "Wrong Query Logic" failure mode that dominates errors.
- Back-linking (RSL-SQL) can check that every criterion column the plan names actually appears in the SQL.
- These clinical-specific mappings are my inference. I found no paper that measures them on cohort tasks.

### Gaps
- No isolated gain number exists for format restriction or output-column alignment.
- No 2024-2026 paper measures cohort-definition error rates separately from overall EX.
- I could not verify CLINSQL's full leaderboard and method breakdown from the primary paper in this session.

## 3. Does elaborate multi-agent scaffolding still help reasoning models?

### Takeaway
Moderately structured prompting still helps reasoning models a lot: o4-mini gained +9.8 EX from DC plus 3 examples. Heavier scaffolding (verification agents, retrieval, multi-agent debate) gives diminishing or negative returns. The best low-cost configuration in the one direct study was DC 3-shot, optionally with 5 parallel samples (+1.2 EX more).

### Cited Findings
- o4-mini on BIRD Mini-Dev: unstructured CoT+ReAct 51.6 vs DC 3-shot 61.4. Adding a verification step lowered it to 59.4, and retrieval to 60.6. Five parallel samples with voting gave 62.6, the best result. The authors conclude that "even specialized models benefit from explicit, procedural guidance" — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- For Gemini-2.5-Flash, the scaffolding gain shrinks to +2.2 EX (62.8 to 65.0), and its unscaffolded baseline beats GPT-4o's best workflow. The stronger the model, the smaller the scaffolding gain — [arXiv 2510.10885](https://arxiv.org/html/2510.10885v1)
- Reasoning models are most useful as planners or aggregators for weaker coders (BAPPA). Multi-agent discussion plateaus after 2 rounds and can degrade accuracy — [BAPPA](https://arxiv.org/html/2511.04153v1)
- Thinking Machines argues that scaffolded systems still trail humans by about 11 points, and that RL-trained single models without scaffolding close the gap. That route requires training, so it does not apply here — [Thinking Machines](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/)
- Strong models handle the full schema without explicit linking, so linking-heavy scaffolding matters less — [arXiv 2408.07702](https://arxiv.org/abs/2408.07702)
- Hard debugging tasks remain hard: o3-mini scores 38.87% on BIRD-CRITIC-PG — [arXiv 2510.14808 (search snippet)](https://arxiv.org/html/2510.14808v1)

### Inferences
- For gpt-5-mini (medium), expect the structured prompt to give most of the attainable gain. A selector or judge agent is unlikely to pay off, since an untuned LLM's pairwise selection is only 60-64% accurate in CHASE.
- Execution-result agreement across 2-3 diverse candidates is the cheapest selection signal that has evidence behind it (+1.2 EX for o4-mini, and the basis of ReFoRCE's and Alpha-SQL's selection).

### Gaps
- I found no 2025-2026 paper that measures scaffolding gains specifically on GPT-5-family models.
- I found no direct comparison on Spider 2.0 of o3 or gpt-5 with and without scaffolding.

## 4. Prompt caching and structured outputs with OpenAI reasoning models

### Takeaway
Caching is automatic for prompt prefixes of 1,024 tokens or more. It requires an exact prefix match and gives about 90% off cached input. So a static prefix (instructions, then schema, then examples), with the question last, cuts the input cost of calls 2-4 sharply. Output schemas and tools are part of the cached prefix. I found no quantitative evidence on how structured outputs affect SQL accuracy.

### Cited Findings
- Requirements and rules: a prefix of at least 1,024 tokens (on older models the minimum varies with tools, output schemas and reasoning effort); an exact full-prefix match; static content first and dynamic content last; stable tool definitions and ordering — [OpenAI prompt caching guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- Retention: on pre-5.6 models, `prompt_cache_retention` is `in_memory` (about 5-10 min of inactivity, up to 1 h) or `24h` (supported on gpt-5, gpt-5.4, gpt-5.5, gpt-4.1); non-ZDR orgs default to 24h. Use `prompt_cache_key` to route related requests together (about 15 req/min per key) — [OpenAI guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- Output schemas (`text.format`) and tool definitions are part of the cached prefix. Changing the schema between calls breaks reuse — [OpenAI guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- On GPT-5.6+, cache reads cost 0.1× the input rate and writes 1.25× (30 min) or 2.5× (12 h). For the earlier GPT-5 family the guide says only "model-dependent", so check the pricing page — [OpenAI guide](https://developers.openai.com/api/docs/guides/prompt-caching)
- gpt-5-mini pricing per third-party aggregators (not official): $0.25/M input, about $0.025/M cached (−90%), $2.00/M output. The batch tier is half price — [devtk](https://devtk.ai/en/models/gpt-5-mini/); [OpenRouter batch](https://openrouter.ai/openai/gpt-5-mini%3Abatch)
- The guide gives no numeric latency reduction; it says only that caching reduces input processing time and time to first token — [OpenAI guide](https://developers.openai.com/api/docs/guides/prompt-caching)

### Inferences
- With schema plus examples at about 4-8k tokens (o4-mini used 4.6-5k prompt tokens on BIRD) and a byte-identical prefix across all 2-4 calls, extra calls cost mostly output and reasoning tokens. Reasoning output ($2/M) dominates cost, so extra calls are cheap on input but not on output.
- Using the same JSON schema across all calls keeps the cache valid. Per-call schema variants break it.

### Gaps
- I found no published study measuring the effect of strict structured outputs (JSON schema) on text-to-SQL accuracy for reasoning models.
- I found no official cached-token rate for gpt-5-mini in the docs I read.

## 5. Cheap (at most 1 extra call) vs expensive techniques

### Takeaway
The cheap, well-evidenced techniques are DC/QP-CoT, few-shot by masked-question or skeleton similarity, synthetic examples, value retrieval, an answer-format contract, and an execution-error fixer. Multi-candidate selection (MCS, CHASE), MCTS (Alpha-SQL) and verification agents are expensive.

### Cited Findings
| Technique | Extra LLM calls | Reported gain | Source |
|---|---|---|---|
| DC-CoT / QP-CoT in a single prompt | 0 (replaces the base prompt) | +5.9 to +6.2 (Gemini-1.5-Pro); +9.4 (o4-mini, DC) | [CHASE](https://arxiv.org/html/2410.01943v1), [2510.10885](https://arxiv.org/html/2510.10885v1) |
| 3-shot examples on top of DC | 0 (retrieval is non-LLM) | +0.4 (o4-mini); masked-question similarity vs random +3.0 (GPT-4) | [2510.10885](https://arxiv.org/html/2510.10885v1), [MCS-SQL](https://arxiv.org/html/2405.07467v1) |
| Online synthetic examples | 1 per DB or cacheable, not per question | +9.34 | [CHASE](https://arxiv.org/html/2410.01943v1) |
| Sample values / LSH value retrieval | 0 LLM calls (rows must not go to the LLM under these constraints, so the evidence applies only to non-patient value vocabularies) | +2.4 (MCS); −2.92 when removed (CHASE) | [MCS-SQL](https://arxiv.org/html/2405.07467v1), [CHASE](https://arxiv.org/html/2410.01943v1) |
| Query fixer on execution error | 0-3 (conditional) | +0.9 to +3.8 | [CHASE](https://arxiv.org/html/2410.01943v1) |
| Format restriction / answer contract | 0 | not isolated (flag) | [ReFoRCE](https://arxiv.org/html/2502.00675v3) |
| 5 parallel samples + vote | +4 | +1.2 (o4-mini); single to SC +5.84 at 21 candidates (CHASE) | [2510.10885](https://arxiv.org/html/2510.10885v1), [CHASE](https://arxiv.org/html/2410.01943v1) |
| LLM verification step | +1 or more | −2.0 (o4-mini), +9.6 s | [2510.10885](https://arxiv.org/html/2510.10885v1) |
| Retrieval-augmented schema step | +1 | −0.8 (o4-mini) | [2510.10885](https://arxiv.org/html/2510.10885v1) |
| Multi-choice selection (MCS) | 20-100 candidates | +2.1 to +3.4; only +0.6 vs majority vote | [MCS-SQL](https://arxiv.org/html/2405.07467v1) |
| Trained selection agent vs SC | pairwise comparisons over 21 candidates, fine-tuned (not allowed) | +4.17 | [CHASE](https://arxiv.org/html/2410.01943v1) |
| MCTS (Alpha-SQL) | many | 69.7 zero-shot BIRD | [Alpha-SQL](https://arxiv.org/html/2502.17248v2) |

### Inferences
- A cost-efficient 2-4 call design that the evidence supports:
  1. One generation with DC/QP plan, answer contract and SQL, using the cached static prefix.
  2. A deterministic execution plus shape check, with no LLM call.
  3. A conditional repair call that receives only the error class and shape diff.
  4. Optionally, one alternative-style candidate, with agreement by result hash or shape, never by sending rows.

### Gaps
- Most papers do not report call counts or dollar costs. The call counts above are derived from the method descriptions.
