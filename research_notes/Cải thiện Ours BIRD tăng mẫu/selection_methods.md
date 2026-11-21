# Candidate selection / verification methods for LLM text-to-SQL beyond majority voting (2023–2026), vs oracle (pass@k) on BIRD

Scope note: numbers are BIRD dev (1,534 questions) unless marked otherwise. "Gap closed" = (selector − SC) / (oracle − SC). I computed it from the cited numbers; it is not reported by the papers. Relevant context for Ours: about 17 candidates, result-set grouping, a non-empty preference, and a gated gpt-4o-mini selector on about 10% of questions.

## Q1. Which selection methods exist, and which are training-free?

### Takeaway
The strongest selectors on BIRD are fine-tuned or RL-trained pairwise/listwise models: CHASE-SQL, XiYan-SQL, Agentar-Scale-SQL, MSc-SQL and GradeSQL ORM. These are excluded for Ours. The training-free options with measured BIRD results are:
- confidence-gated prompted pairwise adjudication (DeepEye-SQL);
- DPC: a distinguishing test DB plus a Python cross-check;
- MBR / execution-similarity voting (Query and Conquer);
- top-2 "merge revision" re-generation (CSC-SQL; the untuned variant exists);
- LLM-predicted test cases (Li & Xie 2024; Spider only);
- plain vote with tie-breaks (OpenSearch-SQL).

### Cited Findings

**Pairwise tournament, fine-tuned (CHASE-SQL, arXiv 2410.01943, ICLR 2025)**
- The selector compares 2 candidates at a time with a binary classifier.
- Each pair is evaluated in both orders to reduce order bias.
- If two candidates have the same execution result, the winner is assigned with no LLM call. Each pairwise win gives +1, and the argmax wins.
- The model is Gemini-1.5-Flash fine-tuned with LoRA rank 16 on about 3.8K BIRD-train pairs.
- Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)

**Listwise "ranker agent" (CHASE-SQL ablation)**
- All candidates go into one prompt and the model ranks them.
- This gave 65.51, which is 7.5 below the full CHASE-SQL at 73.01 and below self-consistency at 68.84.
- Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)

**XiYan-SQL (arXiv 2411.08599)**
- Candidates are grouped by execution-result consistency.
- A fine-tuned selection model picks among representatives of the inconsistent groups.
- The base model is not stated in the text I read.
- Source: [XiYan-SQL](https://arxiv.org/html/2411.08599)

**Agentar-Scale-SQL (arXiv 2509.24403)**
- Candidates are deduplicated by execution result. Representatives then compete in a pairwise round-robin.
- The "Reasoning Selector" is Qwen2.5-Coder-32B-Instruct, RL-trained on 8.5K samples with a binary reward.
- The default pool is 17 candidates: 9 ICL and 8 reasoning. This is the same size as Ours.
- Source: [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403)

**CSC-SQL (arXiv 2505.13271)**
- It takes the top-2 execution-result groups by vote.
- A "merge revision" model generates 8 new SQL candidates from these two groups.
- Self-consistency is then run again on the new candidates.
- GRPO training is optional: the paper reports rows marked "Training: none" for both the generator and revision model.
- Source: [CSC-SQL](https://arxiv.org/html/2505.13271)

**OpenSearch-SQL (arXiv 2502.14913)**
- There is no learned selector. Failed and empty-result SQL is dropped, then a majority vote runs on execution results.
- Ties go to the query with the shortest execution time.
- "Consistency alignment" agents fix individual SQL (value/column, function, style) before voting. They are not a selector.
- Generator: GPT-4o-0513, 21 candidates.
- Source: [OpenSearch-SQL](https://arxiv.org/html/2502.14913)

**MSc-SQL (arXiv 2410.12916, NAACL 2025)**
- A fine-tuned critic of about 7B sees 3 candidates together with their execution results and picks one.
- The generators are Mistral-7B, Llama-3-8B and Gemma-2-9B, all QLoRA-tuned.
- Sources: [MSc-SQL](https://arxiv.org/html/2410.12916v2); [ACL Anthology](https://aclanthology.org/2025.naacl-long.107/)

**GradeSQL ORM (arXiv 2606.30851)**
- An outcome reward model is trained to score candidates, followed by best-of-N.
- Code: sisinflab/GradeSQL.
- Source: [ORM paper](https://arxiv.org/html/2606.30851)

**DeepEye-SQL (arXiv 2510.17586), training-free**
- Confidence = the share of candidates in a result cluster.
- If the top cluster's confidence is above θ = 0.6, its SQL is returned directly.
- Otherwise the top-2 clusters go to a prompted LLM pairwise adjudication: 3 sampled judgments per pair, majority of those.
- The prompt includes the consensus confidence as a prior.
- Final score = Conf × WinRate.
- Source: [DeepEye-SQL](https://arxiv.org/html/2510.17586)

**DPC (arXiv 2604.15163), training-free**
- Candidates are clustered by result. The largest cluster ("Champion") is paired with the second largest ("Challenger").
- SLICER/TESTER agents build a small distinguishing database.
- A SOLVER writes a Python/Pandas solution, and each SQL's execution is compared against it (using BS-F1).
- Source: [DPC](https://arxiv.org/html/2604.15163)

**Query and Conquer (arXiv 2503.24364, Snowflake), training-free**
- Self-consistency is framed as Minimum Bayes Risk decoding.
- The chosen candidate maximizes average execution-result similarity to the other samples.
- Exact similarity uses frequency-matched cell overlap / max(|A|, |B|). Approximate similarity applies the same metric to EXPLAIN plans, with no execution.
- Majority vote is the special case of a 0/1 utility.
- Source: [Query and Conquer](https://arxiv.org/html/2503.24364v1)

**Test-case reranking (Li & Xie, arXiv 2401.02115, preprint only)**
- A small DB is built by randomly sampling rows from the original DB (MTS = 5, CSV format).
- An LLM predicts the expected result for the question on this DB.
- Candidates are reranked by how many tests they pass plus their generation probability.
- Only GPT-4-turbo was usable. GPT-3.5-turbo "cannot generate high-quality test cases".
- Source: [Li & Xie 2024](https://arxiv.org/html/2401.02115v1)

**SIRIUS-SQL (arXiv 2606.01246, Tencent)**
- Score = tuple-level cross-pool consensus + an LLM-judge score. The judge compares result-class representatives in both orders.
- A deterministic AST structural reranker handles near-ties, triggered by a gate.
- The judge/RM may be trained: a Table 4 caption mentions "RM training". Unverified.
- Source: [SIRIUS-SQL](https://arxiv.org/html/2606.01246)

**Verification as a standalone task (Alrashed, Sukoon, Karger, Noy, Google; PVLDB 19(11), VLDB 2026)**
- Methods: "round-trip critique" (SQL → NL back-translation) and "synthetic execution consistency" (unit-test-like synthetic DBs).
- A secondary summary says it flags 64% of generator errors and supports abstention.
- I could not read the PDF body, so the numbers are unverified.
- Sources: [PVLDB PDF](https://www.vldb.org/pvldb/vol19/p3732-alrashed.pdf); [dbscholar summary](https://rmarcus.info/dbscholar/papers/h81eac4660ca3ff39)

**Other 2026 selectors seen only in search snippets (not verified)**
- R³-SQL (arXiv 2604.25325, ACL Findings 2026 per snippet): a pairwise/listwise ranker with consistency reward and position-bias mitigation, compared with CHASE's selector.
- JudgeSQL: a reasoning judge plus a weighted consensus tournament.
- VeriPIE (arXiv 2610.17493), CAPER (arXiv 2606.03327, clause-level process supervision).
- Sources: [R³-SQL](https://arxiv.org/pdf/2604.25325); [ACL Findings 2026 PDF](https://aclanthology.org/2026.findings-acl.2146.pdf); [VeriPIE](https://arxiv.org/pdf/2610.17493); [CAPER](https://arxiv.org/pdf/2606.03327)

### Inferences
- **Same as DeepEye.** Ours's design (group by result, vote, call the selector only when there is no majority) is structurally the same as DeepEye-SQL's confidence-gated adjudication, which is the closest published training-free analogue.
- **Untested levers from DeepEye:** Ours could add three things DeepEye has:
  - multiplying the vote share into the score (Conf × WinRate);
  - 3 sampled judgments per pair;
  - restricting the comparison to the top-2 clusters.
- **Two more additions without training:**
  - MBR-style result-similarity weighting, which gives partial credit to near-identical result sets;
  - a DPC-style distinguishing-DB check between the top-2 clusters.

### Gaps
- No 2023–2026 text-to-SQL paper reporting "confidence-weighted voting" with token log-probabilities on BIRD was found, apart from DeepEye's cluster-share confidence.
- I could not extract tables from R³-SQL, JudgeSQL, VeriPIE, CAPER or the VLDB verification paper. These PDFs are not text-extractable here and have no HTML version.

## Q2. Reported numbers: self-consistency vs selector vs oracle on the same pool

### Takeaway
On the same candidate pool, fine-tuned selectors add +1.8 to +4.2 EX over SC and close roughly 15–35% of the SC-to-oracle gap. Prompted or training-free selectors add about +0.7 to +2.2 EX and close roughly 9–30%. No method comes close to the oracle: a gap of 7–10 points remains in every paper.

### Cited Findings

**Comparison table**

| System (selector type) | Generator / pool | SC / majority | Selector | Oracle | Gap closed (my calc) |
|---|---|---|---|---|---|
| CHASE-SQL (fine-tuned Gemini-1.5-Flash pairwise) | Gemini-1.5-Pro, 3 generators, 21 cands | 68.84 | 73.01 | 82.79 | ≈30% |
| CHASE-SQL ranker agent (prompted listwise) | same | 68.84 | 65.51 | 82.79 | negative |
| Agentar-Scale-SQL (RL Qwen2.5-Coder-32B pairwise) | Gemini-2.5-Pro + GPT-5 + fine-tuned OmniSQL-32B, 17 cands | 73.08 | 74.90 (+1.82) | 84.29 | ≈16% |
| XiYan-SQL (fine-tuned selector) | 3 candidates | 68.84 ("w/o selection model", SC only) | 71.58 (+2.74) | n/a | – |
| XiYan-SQL, 5 candidates | 5 candidates | n/a | 73.34 | n/a | – |
| GradeSQL ORM best-of-N (trained) | OmniSQL-7B, N = 32 | 66.95 | 68.90 (+1.95) | Pass@32 = 80.57 | ≈14% |
| GradeSQL "execution-based best-of-N" | same | 66.95 | 66.04 (below majority) | 80.57 | – |
| MSc-SQL (fine-tuned 7B multi-sample critic) | 3 small models | 62.6 | 65.6 (+3.0) | 71.4 | ≈34% |
| MSc-SQL, off-the-shelf reward model as critic | same | 62.6 | 60.2 (below SC) | 71.4 | – |
| DeepEye-SQL (prompted, gated) | Qwen3-Coder-30B-A3B | 72.7 | 73.5 (+0.8) | 81.6 (UB-EX, full pipeline) | ≈9% |
| DeepEye-SQL | Gemma3-27B | 70.1 | 71.1 (+1.0) | – | – |
| DeepEye-SQL | Qwen2.5-Coder-32B | 70.2 | 70.9 (+0.7) | – | – |
| DPC (training-free; **BIRD Mini-Dev 500, K = 5**) | DeepSeek-V3.2 | 51.2 | 53.4 (+2.2) | Pass@5 = 58.8 | ≈29% |
| DPC | GPT-5 | 49.4 | 51.2 | 56.4 | – |
| DPC | Qwen2.5-Coder-7B | 46.4 | 47.6 | 57.6 | – |
| SIRIUS-SQL (selector variants) | Gemini-3.1 Pro hybrid pool, 32 cands | 75.03 | merge + gate 75.88 (+0.85) | Oracle@32 = 82.66 | ≈11% |

Sources by row group:
- CHASE-SQL rows: [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Agentar-Scale-SQL: [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403)
- XiYan-SQL rows: [XiYan-SQL](https://arxiv.org/html/2411.08599)
- GradeSQL rows: [ORM paper](https://arxiv.org/html/2606.30851)
- MSc-SQL rows: [MSc-SQL](https://arxiv.org/html/2410.12916v2)
- DeepEye-SQL rows: [DeepEye-SQL](https://arxiv.org/html/2510.17586)
- DPC rows: [DPC](https://arxiv.org/html/2604.15163)
- SIRIUS-SQL: [SIRIUS-SQL](https://arxiv.org/html/2606.01246)

**CHASE-SQL details**
- Per-generator results (10 samples per generator at each of two temperatures), SC → selector:

  | Generator | T = 0.5 | T = 1.8 |
  |---|---|---|
  | QP | 65.78 → 71.70 | 65.51 → 71.73 |
  | DC | 66.43 → 71.31 | 64.41 → 70.53 |
  | OS | 67.34 → 70.40 | 66.88 → 71.38 |

- Per-generator upper bounds are 74.8–80.4.
- Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **Prompted vs. fine-tuned selector (CHASE-SQL Table 5).** This is pairwise binary accuracy, not end-to-end EX, on pairs whose labels differ:

  | Selector | Tuned? | Pairwise binary accuracy |
  |---|---|---|
  | Claude-3.5-Sonnet | no | 60.21 |
  | Gemini-1.5-Pro | no | 63.98 |
  | Gemma-2-9B | yes | 64.28 |
  | Gemini-1.5-Flash | yes | 71.01 |

  The prose says untuned Gemini-1.5-Pro reached "58.01%", which is inconsistent with the table. Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)

**DPC plug-in results**
- BIRD Mini-Dev, N = 5, Qwen2.5-Coder-7B as the DPC backbone. SC → DPC:
  - DAIL-SQL: 48.6 → 50.4
  - CHESS: 66.2 → 67.2
  - OmniSQL-7B: 49.2 → 50.8
  - XiYanCoder-7B: 53.0 → 55.4
- A prompted "Multiple-Choice Selection" (one call picks from the list) scored below SC with Qwen (43.6 vs 46.4) and roughly tied SC with DeepSeek (51.0 vs 51.2).
- Source: [DPC](https://arxiv.org/html/2604.15163)

**CSC-SQL (merge revision; selection plus regeneration, not pure selection)**
- Untuned rows, SC → CSC at n = 64:

  | Model | SC | CSC |
  |---|---|---|
  | Qwen2.5-Coder-7B (n = 8: 62.18 → 64.28) | 64.45 | 68.70 (+4.25) |
  | Qwen2.5-Coder-32B | 68.67 | 70.69 (+2.02) |
  | Llama-3.1-70B | 69.82 | 71.69 |
  | OmniSQL-7B | 67.54 | 69.62 |

- Using the top-2 groups is best: top-1 gives 65.44, top-2 gives 67.88, top-3 gives 65.90 (SC = 65.17).
- The paper defines "major_top2_pass@k" but gives it only in a figure.
- Source: [CSC-SQL](https://arxiv.org/html/2505.13271)

**Query and Conquer (BIRD "validation subset", temperature 0.7; MBR exact similarity)**
- GPT-4o-mini: greedy 46.9, Maj@10 49.3, Exec@10 50.5, Exec@30 51.6, Pass@10 62.1.
- Qwen2.5-Coder-7B: Maj@10 45.4, Exec@10 51.7, Pass@10 67.9.
- GPT-4o: Maj@10 51.6, Exec@10 52.4.
- Source: [Query and Conquer](https://arxiv.org/html/2503.24364v1)

**OpenSearch-SQL (GPT-4o, Mini-Dev)**
- Self-consistency and vote raise EX from 68.2 to 70.6.
- On full dev, EX goes from 67.8 without SC & vote to 69.3 with it.
- With GPT-4o-mini, EX peaked at 7–15 candidates rather than 21. The exact values are only in a figure.
- Source: [OpenSearch-SQL](https://arxiv.org/html/2502.14913)

**Test-case reranking (Spider dev only)**
- DAIL-SQL: 80.9 → SC 81.8 → test-case rerank 84.5 with GPT-4-turbo.
- RESDSQL: 81.9 → 83.9.
- Only about 60% of generated test cases were correct. GPT-4-turbo's test-result prediction accuracy was 70.1%.
- Source: [Li & Xie 2024](https://arxiv.org/html/2401.02115v1)

### Inferences
- **Realistic gain for Ours:** for a prompted gpt-4o-mini selector over a strong vote, the training-free papers with comparable backbones suggest about +0.5 to +1.5 EX on full BIRD dev. DeepEye gets +0.7 to +1.0 with 27–32B open models; Query and Conquer gets about +1.2 for GPT-4o-mini MBR vs Maj@10. Expecting to close more than 15% of the oracle gap with prompting alone is not supported by the literature.
- **Prompted gpt-4o-mini is likely weak:** CHASE's prompted Gemini-1.5-Pro and Claude-3.5-Sonnet reached only about 60–64% pairwise accuracy on discordant pairs. A prompted gpt-4o-mini pairwise judge is likely at or below that. This is not measured anywhere I found.
- **Best training-free reported gains:** these came from methods that inject new execution evidence rather than asking the LLM to judge text. Examples are DPC's distinguishing DB plus Python cross-check (+2.2 on Mini-Dev) and CSC's regeneration from the top-2 groups (+2 to +4 with untuned models, at high n).

### Gaps
- No paper reports a prompted gpt-4o-mini pairwise or listwise selector on full BIRD dev with SC and oracle on the same pool.
- CHASE does not report end-to-end EX for the untuned selector, only binary accuracy.
- Agentar's figure-only voting vs. selector bars, and CSC's top-2 pass@k values, are not available as numbers.

## Q3. Failure modes, when selection hurts, and gating

### Takeaway
Selection hurts when it overrides a correct majority. DPC loses 3.0 points on majority-correct questions. Listwise rankers, untuned reward models and plain execution-based best-of-N fall below SC. Published systems mitigate this by gating (judge only when the vote is uncertain), by multiplying in vote confidence, by evaluating both orders, and by restricting the comparison to the top-2 clusters.

### Cited Findings

**Overriding correct majorities (DPC, BIRD Mini-Dev, Qwen backbone)**
- On majority-correct questions, SC is 100% and DPC is 97.0% (−3.0).
- On majority-incorrect questions, SC is 0% and DPC is 21.4%.
- The net gain is only +1.2.
- The paper attributes LLM-as-judge failures to "symbolic blindness" and "consensus on hallucinations".
- Source: [DPC](https://arxiv.org/html/2604.15163)

**Selectors that fall below SC**
- CHASE listwise ranker: 65.51 vs SC 68.84. Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)
- MSc-SQL off-the-shelf Skywork-Reward-Llama-3.1-8B critic: 60.2 vs SC 62.6. Source: [MSc-SQL](https://arxiv.org/html/2410.12916v2)
- GradeSQL execution-based best-of-N: 66.04 vs majority 66.95. Source: [ORM paper](https://arxiv.org/html/2606.30851)
- DPC's prompted Multiple-Choice Selection: 43.6 vs SC 46.4 (Qwen-7B). Source: [DPC](https://arxiv.org/html/2604.15163)

**Small and untuned selectors**
- Even tuned Gemma-2-9B reached only 64.28 pairwise accuracy, versus 71.01 for tuned Gemini-1.5-Flash. Untuned large models were at 60–64.
- Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)

**Position or order bias**
- CHASE evaluates each pair in both orders. Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)
- SIRIUS-SQL judges result-class representatives in both positions and debiases. Source: [SIRIUS-SQL](https://arxiv.org/html/2606.01246)
- R³-SQL reportedly adds position-bias mitigation to its listwise ranker. This is from a search snippet only, unverified. Source: [R³-SQL](https://arxiv.org/pdf/2604.25325)
- No paper found quantifies the position-bias rate for SQL selection.

**Gating**
- DeepEye-SQL returns the top cluster when its share is above 0.6, and otherwise runs the LLM adjudication.
- Accuracy stays above 73.0% for θ in [0.4, 1.0], so it is robust to the threshold.
- Cluster-share confidence correlates with EX at Pearson r = 0.954 on BIRD dev.
- Source: [DeepEye-SQL](https://arxiv.org/html/2510.17586)
- SIRIUS-SQL runs an extra structural reranker only when the top-2 scores are tied and the largest class is at most T_max. This adds +0.20 EX (75.68 → 75.88). Source: [SIRIUS-SQL](https://arxiv.org/html/2606.01246)

**Candidate count interacts with vote quality**
- With GPT-4o-mini, OpenSearch-SQL's vote peaked at 7–15 candidates. More candidates are not monotonically better for weaker models. Source: [OpenSearch-SQL](https://arxiv.org/html/2502.14913)
- CHASE found that more than 20 candidates gave no significant oracle gain. Source: [CHASE-SQL](https://arxiv.org/html/2410.01943)

**Noisy tests and labels**
- LLM-predicted test cases were only about 60% correct, which caps reranking gains. Source: [Li & Xie 2024](https://arxiv.org/html/2401.02115v1)
- The VLDB verification paper reportedly finds widespread benchmark label flaws (secondary summary, unverified). Source: [dbscholar summary](https://rmarcus.info/dbscholar/papers/h81eac4660ca3ff39)

### Inferences
- **Ours's gate is supported:** calling the selector only when no group has a majority (about 10% of questions) matches DeepEye's design. The literature supports keeping majorities untouched.
- **Headroom left for Ours:** the remaining headroom is mostly majority-wrong questions. About 70–80% of these remain unrecoverable even for DPC.
- **Cheap safeguards for Ours:**
  - evaluate both orders;
  - use 3 samples per pair;
  - compare only the top-2 clusters;
  - weight by cluster share.

### Gaps
- No paper reports the fraction of questions that trigger the gate (DeepEye says only "low-confidence scenarios"). There are no per-gate-bucket accuracies to compare with Ours's 10%.

## Q4. Cost per selector

### Takeaway
Exhaustive pairwise tournaments are expensive: O(m²) calls, up to hundreds per question. Gated top-2 adjudication and execution-only MBR are near-free. DPC and listwise multiple-choice cost about 4K tokens per question. Test-case generation costs about 10 times the API calls.

### Cited Findings
- **Agentar-Scale-SQL:** 1–561 selection calls per query and 20–630 LLM calls in total. Agentar's own table lists CHASE-SQL + Gemini at 297 total calls. CHASE's paper does not state its call count; for 21 candidates there are up to 210 pairs, or 420 ordered comparisons, minus same-result shortcuts. Sources: [Agentar-Scale-SQL](https://arxiv.org/html/2509.24403); [CHASE-SQL](https://arxiv.org/html/2410.01943)
- **DeepEye-SQL:** the selection stage averages 0.19K input and 0.01K output tokens per query over all queries, because of the shortcut. When it is triggered, it uses 3 judgments per pair over the top-2. Source: [DeepEye-SQL](https://arxiv.org/html/2510.17586)
- **DPC vs. MCS:** DPC costs about 3.8K tokens and about 4.2 s per question, versus about 4.2K tokens and about 5.1 s for prompted Multiple-Choice Selection. SC takes about 0.8 s and no LLM tokens. Source: [DPC](https://arxiv.org/html/2604.15163)
- **CSC-SQL:** the merge step adds 7–11% of total time. The cost was $0.0014–0.0043 per question on an H800 (self-hosted). Source: [CSC-SQL](https://arxiv.org/html/2505.13271)
- **Query and Conquer:** MBR uses CPU-side execution comparisons only, with no extra LLM calls. The paper claims a 7B model with SC reaches o1-level accuracy at about 30 times lower cost. Source: [Query and Conquer](https://arxiv.org/html/2503.24364v1)
- **Test-case reranking:** about 10 times the OpenAI API calls, with up to 10 test cases per question. Source: [Li & Xie 2024](https://arxiv.org/html/2401.02115v1)

### Inferences
- **Cost estimate for Ours (rough arithmetic, not measured):** if the gate stays at about 10% of questions, a DeepEye-style 3-judgment, both-orders top-2 adjudication with gpt-4o-mini means about 6 calls × about 150 questions. The cost would likely stay within about $1–2 per dev run, comparable to the current $0.38.
- **DPC-style distinguishing DB:** applied only to gated questions, this adds about 4K tokens each, which is still cheap on gpt-4o-mini.

### Gaps
- No paper reports dollar cost per question for API-based prompted selectors on BIRD with gpt-4o-mini.
