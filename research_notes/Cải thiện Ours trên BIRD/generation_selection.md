# Training-free candidate generation diversity and candidate selection for LLM text-to-SQL on BIRD dev (2023-2026)

All numbers are BIRD **dev** execution accuracy (EX, %) unless explicitly marked "test", "Mini-Dev" (500-question subset), "SDS" (147-question subsampled dev from CHESS), or "Spider".

## Q1. Generation diversity: what each method contributes (ablation EX points, number of candidates/calls)

### Takeaway
Generator diversity helps, but the gain from any single extra generator is small (about 0.6-1.3 EX in CHASE-SQL ablations). The bigger contributors are (a) having more than one generator family, especially an ICL generator plus a differently trained or fine-tuned generator (+1.3 to +4.9), and (b) per-candidate quality steps: few-shot, a query fixer, and schema/value retrieval (+2 to +5 each). For GPT-4o-mini specifically, the only hard published numbers are single-pipeline results (E-SQL 61.60; OmniSQL baseline 58.8 greedy and 61.5 with majority vote over 8 samples).

### Cited Findings
**CHASE-SQL (Gemini 1.5 Pro / Claude 3.5 Sonnet)**
- Overall: 73.01 dev / 73.0 test (Gemini 1.5 Pro); 69.53 dev (Claude 3.5 Sonnet) — [CHASE-SQL 2410.01943](https://arxiv.org/html/2410.01943)
- Single-candidate generators, Gemini 1.5 Pro, without/with query fixer: baseline BIRD prompt + zero-shot CoT 57.75/61.58; Query-Plan CoT 63.62/65.51; Divide-and-Conquer CoT 63.92/65.77; Online Synthetic examples 67.09/68.02. The fixer is worth about +1 to +3.8 per generator — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Leave-one-out ablation of the full system (73.01): w/o QP -0.65, w/o OS -0.85, w/o DC -1.24, w/o Query Fixer -3.78, w/o LSH value retrieval -2.92 — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Online synthetic example guidelines: zero-shot 57.75, R_f only 65.45, R_t only 66.75, R_f+R_t 67.09 — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Budget: 7 candidates per generator x 3 generators = 21 candidates. In the per-generator selection study, 10 samples per generator at T=0.5 and T=1.8. Selector, fixer, column filter and keyword extraction are extra calls — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- An independent cost comparison lists CHASE at "100+" LLM calls and $0.44 per query (quoted there as 74.9 EX with a fine-tuned selector), against CHESS at 31.83 average calls and $0.46 per query — [N-rep 2505.14174](https://arxiv.org/html/2505.14174v1)

**CHESS (2405.16755)**
- CHESS(IR,CG,UT) with Gemini-1.5-pro, 20 candidates and 10 unit tests: 68.31 dev / 71.10 test. The paper labels 68.31 as dev in Table 1 but as the SDS score in Table 6, which is inconsistent — [CHESS](https://arxiv.org/html/2405.16755)
- CHESS(IR,SS,CG) proprietary: 65.00 dev / 66.69 test, using a fine-tuned DeepSeek Coder for generation, GPT-3.5-turbo for column filtering and GPT-4-turbo for the rest. Open LLMs (fine-tuned DeepSeek + Llama-3-70B): 61.5 — [CHESS](https://arxiv.org/html/2405.16755)
- SDS ablation (full 64.62): w/o retrieval -4.76, w/o column filter -2.72, w/o table select -6.12, w/o column select -5.44, w/o revise -6.80, revise limited to once -3.40 — [CHESS](https://arxiv.org/html/2405.16755)
- Engine swap on SDS: all GPT-3.5-turbo 49.65; GPT-4-turbo as generator 55.78; vanilla GPT-4-turbo 46.25. A weak generator dominates the outcome — [CHESS](https://arxiv.org/html/2405.16755)

**MCS-SQL (GPT-4, 2405.07467)**
- Final result 63.4 dev (Alpha-SQL's table quotes MCS-SQL+GPT-4 as 64.4, and a search snippet cites 65.5 test) — [MCS-SQL](https://arxiv.org/html/2405.07467); [Alpha-SQL](https://arxiv.org/html/2502.17248)
- Cumulative ablation: zero-shot 50.7, +schema linking 52.8, +sample contents 55.2, +few-shot (masked-question similarity) 60.0, +MCS with 1 prompt and n=20 62.1 (+2.1), +MCS with 5 prompts (shuffled schema/few-shot order) and n=20 63.4 (+1.3) — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Multiple shuffled prompts in schema linking raise recall from 77.1 (1 prompt, n=20) to 89.8 (3 prompts, n=20). No EX ablation for shuffling alone — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Same paper's baselines (GPT-4): zero-shot 46.4, DIN-SQL 50.7, DAIL-SQL 54.8, MAC-SQL 57.7 — [MCS-SQL](https://arxiv.org/html/2405.07467)

**XiYan-SQL (2411.08599)**
- 73.34 dev (5 candidates) / 75.63 test. 3-candidate system: 71.58 — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- Ablation on the 3-candidate system: w/o fine-tuned generator -2.91 (68.67), w/o ICL generator (GPT-4o) -1.31 (70.27), w/o refiner -0.55, w/o selection model -2.74 (68.84) — [XiYan-SQL](https://arxiv.org/html/2411.08599)

**Alpha-SQL (MCTS, zero-shot, 2502.17248)**
- Qwen2.5-Coder-7B 66.8, 14B 68.7, 32B 69.7 dev; versus RSL-SQL+GPT-4o 67.2. Spider dev: 7B 84.0, 14B 87.0 — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- Budget: 24 MCTS rollouts, 3 expansions, 5 reward samples. Final selection uses execution-result consistency. No pass@k numbers in the text — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- SDS: Qwen2.5-Coder-7B 47.6 rising to 64.6 (+17.0); Phi-4 43.5 rising to 60.0. Action ablation: w/o rephrasing -0.7, w/o schema selection -1.5, w/o value identification -0.4, w/o function identification -0.6, w/o SQL revision -1.8 — [Alpha-SQL](https://arxiv.org/html/2502.17248)

**OpenSearch-SQL (GPT-4o, 2502.14913)**
- 69.30 dev / 72.28 test. Single SQL without self-consistency: 67.80 dev — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- Mini-Dev ablation (full 70.6): w/o few-shot -4.6, w/o extraction -3.2, w/o refinement -3.6, w/o self-consistency & vote -2.4, w/o CoT -1.4, w/o column filter -2.0 — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- Structured CoT gives a larger gain after correction than no CoT (+6.2 vs +1.6 from EX_G to EX_V) — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)

**RSL-SQL (2411.00073)**
- GPT-4o 67.21; DeepSeek 63.56. Cumulative GPT-4o ablation: base 48.70, +few-shot +9.97, +data samples +3.39, bidirectional schema linking +0.65, contextual augmentation +2.35, binary selection between 2 candidates (full vs simplified schema) +1.37, multi-turn self-correction +0.78. No GPT-4o-mini numbers. GPT-4o cost $62.06 for dev, from 21.9M input tokens — [RSL-SQL](https://arxiv.org/html/2411.00073)

**E-SQL (2409.16751)**
- GPT-4o-mini 61.60; GPT-4o 65.58; Qwen2.5-Coder-7B 53.59. Single candidate, about 3 calls. GPT-4o-mini ablation: w/o question enrichment -1.89, w/o candidate predicate generation -2.02, w/o both -3.26, w/o refinement -3.57; adding schema filtering hurts (-5.54) — [E-SQL](https://arxiv.org/html/2409.16751)

**OmniSQL (2503.02240): majority vote with 8 samples at T=0.8, grouped by execution result**
- GPT-4o-mini 58.8 greedy, 61.5 majority (+2.7); GPT-4o 61.9 to 64.0 (+2.1); Qwen2.5-Coder-7B 50.9 to 61.3 (+10.4); 14B 61.5 to 66.1; 32B 64.5 to 67.0; OmniSQL-7B 63.9 to 66.1; OmniSQL-32B 64.5 to 67.0 — [OmniSQL](https://arxiv.org/html/2503.02240)

**Agentar-Scale-SQL (2509.24403)**
- 74.90 dev / 81.67 test. Candidate pool: 9 ICL candidates (Gemini-2.5-Pro at T=0.5/1.8 plus GPT-5 minimal) and 8 candidates from a GRPO-tuned OmniSQL-32B. W/o reasoning generator -4.89; w/o ICL generator -3.78 — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)

**SIRIUS-SQL (2606.01246)**
- Matched-budget pools: a single generalist (Qwen3-Coder) pool reaches 72.08, while mixed specialist+generalist pools reach 72.4-74.5. SIRIUS+Coder 74.51; full system with Gemini-3.1-Pro 75.88 — [SIRIUS-SQL](https://arxiv.org/html/2606.01246)
- Execution-grounded lifecycle (screen, execute, repair) is worth +0.71 under majority voting (74.32 to 75.03) — [SIRIUS-SQL](https://arxiv.org/html/2606.01246)

**N-rep consistency (2505.14174): diversity from multiple schema representations (DDL, MAC-Schema, M-Schema)**
- 69.25 dev with a median of 8 calls (10.9 on average) and $0.039 per query. Qwen3-8B 44.98 to 57.04, 14B 53.46 to 61.67, 32B 56.71 to 64.02. About +2 over CoT self-consistency at the same candidate count. Final configuration: 5 candidates with Gemini 1.5 Flash — [N-rep](https://arxiv.org/html/2505.14174v1)

**Divide-and-conquer prompting in an agentic workflow (2510.10885), Mini-Dev**
- Baseline vs DC 3-shot: Gemini 1.5 Flash 54.6 to 59.8; GPT-4o 55.0 to 60.0; o4-mini 51.6 to 61.4 — [Rethinking Agentic Workflows](https://arxiv.org/html/2510.10885v1)

### Inferences
- Diversity from the same model with different prompts (QP/DC/OS, shuffled prompts, schema representations) is worth about 1-2 EX over a single prompt family. Diversity from a genuinely different generator (fine-tuned or RL-trained plus ICL) is worth 3-5 EX. A training-free GPT-4o-mini setup only has the first kind available, unless an open model such as OmniSQL or Qwen-Coder is added as a second generator.
- Per-candidate quality steps (few-shot, fixer, value retrieval) are at least as large as the diversity gains and should come before diversity work.

### Gaps
- No primary-source BIRD dev numbers were found for DIN-SQL, DAIL-SQL, MAC-SQL, PURPLE, SuperSQL, Distillery or TA-SQL ablations beyond the GPT-4 baselines quoted in MCS-SQL and CHASE-SQL (SuperSQL 58.5, Distillery+GPT-4o 67.21, PURPLE-RED+GPT-4o 68.12). These papers' own ablation tables were not fetched.
- ReFoRCE targets Spider 2.0. No BIRD dev ablation was found.
- No published CHASE-SQL-style multi-generator pipeline run with GPT-4o-mini was found.

## Q2. EX scaling with number of candidates: oracle upper bound vs selected; majority-vote saturation

### Takeaway
The oracle upper bound over about 20-32 candidates is 80-84 EX, while selected accuracy is 68-76. That leaves a selection gap of roughly 8-14 points. Majority vote saturates early: around 8 candidates, and with 32 candidates it can even drop slightly. Pass@k gains also shrink after about 8 candidates.

### Cited Findings
- CHASE-SQL (Gemini 1.5 Pro, 21 candidates): single query 63.01, self-consistency 68.84 (+5.84), upper bound 82.79 (+19.78) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- CHASE-SQL per generator with 10 samples: upper bound 74.77-80.44 versus self-consistency 64.41-67.34. Higher temperature (T=1.8) raises the upper bound (QP 78.55 to 80.44) but lowers the lower bound and self-consistency slightly — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Agentar-Scale-SQL: upper bound ICL 81.36, reasoning 75.88, combined 84.29, against 74.90 selected. Pass@k gains are largest up to 8 candidates and diminish beyond (range 1-16 tested) — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- SIRIUS-SQL Oracle@k: SIRIUS+Qwen3-Coder pool 82.66, Qwen3-Coder only 80.18, SIRIUS only 78.42, against 74.5-75.9 selected — [SIRIUS-SQL](https://arxiv.org/html/2606.01246)
- MaP-SQL: majority vote at 8 vs 32 candidates goes Agentar 71.38 to 70.93 and Arctic 70.08 to 69.95. Majority vote does not improve, and slightly drops, from 8 to 32 — [MaP-SQL 2609.00834](https://arxiv.org/html/2609.00834)
- OpenSearch-SQL: GPT-4o EX rises consistently over N = {1, 3, 7, 15, 21}. GPT-4o-mini peaks at 7-15 candidates (no exact values in the text) — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- N-rep: self-consistency without CoT plateaus after 3 candidates — [N-rep](https://arxiv.org/html/2505.14174v1)
- CHESS: accuracy rises up to 10 unit tests, then plateaus (figure only) — [CHESS](https://arxiv.org/html/2405.16755)
- Mini-Dev, 5-way parallel majority vote vs single DC 3-shot: Gemini 1.5 Flash 59.8 to 59.4, GPT-4o 60.0 to 59.2, Gemini 2.5 Flash 65.0 to 63.0; only o4-mini improves (61.4 to 62.6). Small-k majority vote over one prompt can be neutral or negative — [Rethinking Agentic Workflows](https://arxiv.org/html/2510.10885v1)

### Inferences
- For GPT-4o-mini, 7-15 candidates looks like the sweet spot. Beyond that, extra samples mainly raise the oracle bound, which only a better selector can exploit.

### Gaps
- No exact pass@k curves (numeric) for GPT-4o-mini on BIRD dev were found. Alpha-SQL, Agentar, OpenSearch and N-rep give them only as figures.

## Q3. Selection beyond majority vote: measured gains

### Takeaway
Fine-tuned selectors add about +1.8 to +4.2 over self-consistency: CHASE-SQL +4.17 with a fine-tuned Gemini-Flash pairwise selector, XiYan +2.74, Agentar tournament +1.82. Untrained pairwise LLM judges are weak. Their pairwise accuracy is about 58-64% against 71% when tuned, and in MaP-SQL untrained CHASE-style pairwise selection is at or below majority vote. The best training-free selectors found are listwise with memory or permutation aggregation (+1.2 to +2.7 over majority vote, with fewer calls) and confidence-gated hybrids that fall back to majority vote (+0.85).

### Cited Findings
- CHASE-SQL full system: replacing the selector with self-consistency costs -4.17 (73.01 to 68.84); a ranker agent costs -7.5 (65.51) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- CHASE-SQL per generator, selection agent vs self-consistency: QP 71.7 vs 65.78; DC 71.31 vs 66.43; OS 70.4 vs 67.34 (+3 to +6) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- The CHASE-SQL selector is Gemini 1.5 Flash fine-tuned with LoRA (r=16, 10 epochs, 3.8K BIRD-train pairs). Pairwise binary accuracy: untuned Claude 3.5 Sonnet 60.21, untuned Gemini 1.5 Pro 63.98 (58.01 in the paper text, an internal inconsistency), tuned Gemma-2-9B 64.28, tuned Gemini 1.5 Flash 71.01 — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL: selection model vs self-consistency gives 71.58 vs 68.84 (+2.74), fine-tuned — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- Agentar-Scale-SQL: tournament selection with an RL-trained Qwen2.5-Coder-32B selector vs majority vote gives 74.90 vs 73.08 (+1.82) — [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403v6)
- MCS-SQL (GPT-4, training-free): majority vote 62.8; multiple-choice selection without confidence filter 62.5; with confidence filter (T=0.2) 63.4 (+0.6 over majority vote) — [MCS-SQL](https://arxiv.org/html/2405.07467)
- CHESS: the unit-tester selector (Gemini-1.5-pro, 10 generated unit tests, 20 candidates) gives 68.31 vs 66.78 when one candidate is scored with all tests. There is no direct comparison to majority vote — [CHESS](https://arxiv.org/html/2405.16755)
- MaP-SQL (training-free; Qwen3-Coder-30B-A3B selector), n=8, Agentar candidates: greedy 69.95, majority 71.38, pointwise RM 71.45, untrained CHASE-style pairwise 71.25 (6.11 calls), untrained R3-SQL 71.51 (14.11 calls), listwise+memory 72.23 (0.71 calls), MaP-SQL 72.62 (2.97 calls). With n=32: majority 70.93, pairwise 71.06 (129.93 calls), MaP 73.08 — [MaP-SQL](https://arxiv.org/html/2609.00834)
- MaP-SQL with Arctic-7B candidates: n=8 majority 70.08, pairwise 69.30 (below majority), MaP 72.16. With n=32: majority 69.95, pairwise 68.12, MaP 72.62. MaP ablation (n=8, Agentar): w/o permutation 72.23, w/o memory 71.94, w/o both 71.64 — [MaP-SQL](https://arxiv.org/html/2609.00834)
- MaP-SQL vs fine-tuned R3-SQL (OmniSQL-7B, n=32): majority 68.45, fine-tuned R3-SQL 71.84, MaP-SQL 71.90. Training-free listwise matches the fine-tuned selector — [MaP-SQL](https://arxiv.org/html/2609.00834)
- With gpt-5.1-codex-mini as selector, listwise selection goes 71.90 to 72.23 with memory (Agentar) and 70.01 to 70.40 (Arctic) — [MaP-SQL](https://arxiv.org/html/2609.00834)
- SIRIUS-SQL selector comparison: frequency 74.97, majority 75.03, pairwise RM alone 74.32 (below majority), merged majority+RM 75.68, merged plus confidence gate 75.88 (+0.85 over majority) — [SIRIUS-SQL](https://arxiv.org/html/2606.01246)
- N-rep (Gemini 1.5 Flash): regular voting 67.2 (0 extra calls); LLM-based voting 67.9 (6,178 calls); confidence-aware voting, where the LLM is called only on low-agreement questions, 68.8 (2,436 calls) — [N-rep](https://arxiv.org/html/2505.14174v1)
- RSL-SQL: binary selection between 2 candidates gives +1.37 (GPT-4o) and +1.63 (DeepSeek) — [RSL-SQL](https://arxiv.org/html/2411.00073)
- CSC-SQL: merge-revision of the top-2 execution groups, then self-consistency again, gives +0.72 to +5.54 over self-consistency, but with GRPO-trained 3B/7B models (test: 7B 71.72, 32B 73.67) — [CSC-SQL 2505.13271](https://arxiv.org/html/2505.13271v2); [GitHub](https://github.com/CycloneBoy/csc_sql)

### Inferences
- Plain untrained pairwise judging (CHASE-style) is unreliable without fine-tuning. It is often at or below majority vote and very expensive at large n (130-185 calls at n=32). Training-free gains come from (a) calling the judge only when agreement is low, (b) listwise selection over execution-result groups with permutation aggregation, and (c) adding explicit selection criteria or memory distilled from training data.

### Gaps
- No direct measurement was found of an untuned gpt-4o-mini acting as a pairwise or listwise selector on BIRD dev.

## Q4. Which methods work training-free with gpt-4o-mini?

### Takeaway
Published evidence is thin. Confirmed for GPT-4o-mini: majority vote over 8 samples (+2.7, from 58.8 to 61.5) and E-SQL-style enrichment and refinement (61.60, single candidate). OpenSearch-SQL reports that its multi-candidate vote helps GPT-4o-mini up to about 7-15 candidates. Everything else is extrapolated from Gemini-Flash, GPT-4o or Qwen results.

### Cited Findings
- GPT-4o-mini majority vote: 58.8 to 61.5 (8 samples, T=0.8) — [OmniSQL](https://arxiv.org/html/2503.02240)
- GPT-4o-mini E-SQL: 61.60 (refinement +3.57, candidate predicate generation +2.02, question enrichment +1.89) — [E-SQL](https://arxiv.org/html/2409.16751)
- OpenSearch-SQL: GPT-4o-mini is best at 7 and 15 candidates (qualitative) — [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- Small and cheap models gain from diverse generation plus voting: Gemini 1.5 Flash with N-rep reaches 69.25 at $0.039 per query, and confidence-aware voting adds +1.6 over regular voting — [N-rep](https://arxiv.org/html/2505.14174v1)
- In CHESS's engine study, an all-GPT-3.5-turbo pipeline reaches only 49.65 on SDS, so a weak generator limits the whole pipeline — [CHESS](https://arxiv.org/html/2405.16755)
- NL2SQLBench (2604.16493) benchmarks modular NL2SQL methods using gpt-4o-mini on BIRD dev (Pass@1 for multi-candidate methods). Its numbers were not retrieved — [NL2SQLBench](https://arxiv.org/pdf/2604.16493)

### Inferences
- A plausible training-free stack for gpt-4o-mini: 2-3 prompt variants (DC/QP CoT, shuffled or alternate schema representations, few-shot); about 8-15 candidates in total; an execution-based fixer; grouping by execution result. For selection, use majority vote and call an LLM judge (listwise, with permutations) only when agreement is low. Based on N-rep, MaP-SQL and SIRIUS-SQL, the expected gain over plain majority vote is about +1 to +2.5 EX, not the +4 that fine-tuned CHASE-SQL reports.

### Gaps
- NL2SQLBench's gpt-4o-mini tables were not fetched; they may hold the most direct numbers.
- No study was found running CHASE-SQL, CHESS-UT or MCS-SQL selection with a gpt-4o-mini judge.
