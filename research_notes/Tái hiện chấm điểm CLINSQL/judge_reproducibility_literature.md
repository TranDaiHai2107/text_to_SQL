# Reproducibility of LLM-as-a-Judge Rubric Scoring (judge swap, decoding, prompt), with application to text-to-SQL / code evaluation, 2023-2026

Scope note: the notes back up a thesis claim that an adapted judge (gpt-5-mini, reasoning) gives scores that differ from a benchmark's official judge (gpt-5-chat, temperature 0.2), and say how big that gap might be. No source found evaluates gpt-5-mini or gpt-5-chat as judges, so every number below is an analogue from other judge pairs. Items marked [memory, verify] come from my prior knowledge of well-known papers and were not re-fetched in this session. Several 2026 preprints were seen only at abstract level; they are marked [abstract only].

## Q1. Judge-swap effects: absolute score shifts vs. ranking preservation

### Takeaway
Across studies the result is the same: changing the judge model can move absolute scores by several points (5 to 10+ points on a 100-point scale, and leniency by up to 56 pp on a binary task). System rankings, however, are usually much more stable: Spearman about 0.93-0.99 even for weak judges. "Model identity" is consistently the largest single source of variance among judge design choices.

### Cited Findings
- **Judging the Judges (Thakur et al., 2024; 13 judges, 9 exam-taker models, TriviaQA).**
  - The best judges (Llama-3 70B, Llama-3.1 70B, GPT-4 Turbo) reach Scott's π of about 87-88 against humans. Human-human π is 96.2 ± 1.07, so the best judge is "8 points behind human judgment".
  - Judges with π above 80 still give scores that differ from human-assigned scores by "up to 5 points".
  - Judges with percent agreement above 90% can differ by more than 10 points. — [arXiv 2406.12624 (HTML v6)](https://arxiv.org/html/2406.12624v6)
- **Judging the Judges: rankings.** Spearman ρ between each judge's ranking of the 9 exam-takers and the human ranking:
  - "Contains" lexical metric 0.99, Mistral-7B 0.98, GPT-4 Turbo 0.98, Llama-3.1 70B 0.94, Llama-3 70B 0.93, exact match 0.67.
  - Rankings are therefore preserved even by judges whose absolute scores are off. Kendall τ is not reported. — [arXiv 2406.12624](https://arxiv.org/html/2406.12624v6)
- **Judging the Judges: metric choice.**
  - The paper switched from Cohen's κ (earlier version) to Scott's π because of "well-documented theoretical issues" with κ.
  - It recommends "computing both percent agreement and Scott's π, paired with qualitative analysis". — [arXiv 2406.12624](https://arxiv.org/html/2406.12624v6)
- **Judging the Judges: leniency.** Most judges have P(mark "correct" when unsure) well above 0.5: GPT-4 Turbo 0.69, Mistral-7B 0.87, Llama2-70B 0.99. JudgeLM-7B is the exception at 0.19. Systematic leniency is therefore judge-specific. — [arXiv 2406.12624](https://arxiv.org/html/2406.12624v6)
- **JudgeBench (Tan et al., 2024/ICLR 2025; pairwise judging on knowledge, reasoning, math and coding pairs).** Accuracy varies widely by judge. Overall / coding accuracy:

  | Judge | Overall | Coding |
  |---|---|---|
  | GPT-4o (vanilla) | 50.86 | 61.90 |
  | Claude-3.5-Sonnet | 64.29 | 64.29 |
  | o1-mini | 65.71 | 78.57 |
  | o1-preview | 75.43 | 85.71 |
  | DeepSeek-R1 | 73.14 | 92.86 |
  | o3-mini (high) | 80.86 | 100.0 |
  | Llama-3.1-405B | 56.86 | 50.00 |
  | Prometheus2-7b | 34.86 | 42.86 |
  | JudgeLM-33B | 35.71 | 19.05 |

  — [arXiv 2410.12784 (HTML v2)](https://arxiv.org/html/2410.12784v2)
- **"How Much Do LLM-as-a-Judge Design Choices Matter?" (Vaugrante & Hagendorff, 2026) [abstract only].**
  - Switching models changed leniency by up to 56.1 pp on binary QA-accuracy classification (n=600). Detailed prompts lowered leniency by 28.9 pp.
  - Changing the rating scale alone shifted measured bias by up to 0.93 points on a 1-7 scale.
  - Average binary accuracy was 96.5% and was "rarely affected" by design choices.
  - "Model identity was the dominant source of variance." — [arXiv 2610.05094](https://arxiv.org/abs/2610.05094)
- **"Same Input, Different Scores" (Lau, 2026; GPT-4o, GPT-4o-mini, Gemini-2.5-Flash, Claude Haiku 4.5, Claude Sonnet 4.5 on enterprise RAG QA) [abstract only].** "Cross-model differences in strictness and interpretive style led to divergent ratings for the same answers." Completeness scoring fluctuated most. — [arXiv 2603.04417](https://arxiv.org/abs/2603.04417)
- **HealthBench (Arora et al., OpenAI 2025; rubric grading, physician-written criteria).** The meta-evaluation macro-F1 of different grader models against physicians:
  - GPT-4.1 0.709 (adopted as default), o4-mini 0.692, o3 0.681, GPT-4.1-mini 0.661, GPT-4.1-nano 0.580.
  - Physician-vs-physician MF1 ranges 0.569-0.730 by theme; the random baseline is 0.50.
  - The authors note GPT-4.1 was used during grader-prompt tuning, which may partly explain its lead.
  - The paper does not report how overall HealthBench scores change when the grader is swapped. — [HealthBench full paper (HF mirror)](https://huggingface.co/datasets/OnDeviceMedNotes/healthbench/blob/main/healthbench-fullpaper.md); [OpenAI PDF](https://cdn.openai.com/pdf/bd7a39d5-9e9f-47b3-903c-8b847ca650c7/healthbench_paper.pdf)
- **HealthBench re-run with a different grader (secondary).** A later paper reran the official grader code with DeepSeek-V4-Pro and got MF1 0.62, against 0.71 for GPT-4.1, on 29,511 response-criterion pairs. This shows a swap effect of about 0.09 MF1 on the same rubric. Seen via search snippet only. — [arXiv 2609.38847](https://arxiv.org/pdf/2609.38847) (unverified)
- **"Decomposing Physician Disagreement in HealthBench".** It argues that about 22.5% case-level disagreement among physicians mechanically caps achievable F1, so 0.709 reflects the human ceiling. — [arXiv 2602.22758](https://arxiv.org/pdf/2602.22758)
- **PaperBench (OpenAI 2025; hierarchical rubric, binary leaves).**
  - The judge "SimpleJudge" defaults to o3-mini-high and reaches F1 0.83 on the JudgeEval human-graded set; the random baseline is 0.49.
  - o1-high was only marginally better on some requirement types, and the authors attribute that to possible noise, at much higher cost.
  - This is a template for validating a cheaper substitute judge on a human-graded set. — [arXiv 2504.01848](https://arxiv.org/pdf/2504.01848)
- **PRBench (2025; expert rubrics).** o4-mini and GPT-4.1 show similar agreement with experts, κ about 0.60 each. Seen via search snippet. — [arXiv 2511.11562](https://arxiv.org/pdf/2511.11562)
- **Large Language Models are not Fair Evaluators (Wang et al., 2023).**
  - With ChatGPT as evaluator, Vicuna-13B "beats" ChatGPT on 66 of 80 queries just by changing the order of the responses.
  - Proposed fixes: Multiple Evidence Calibration, Balanced Position Calibration, and Human-in-the-Loop Calibration. — [arXiv 2305.17926](https://arxiv.org/abs/2305.17926)
- **MT-Bench / Chatbot Arena (Zheng et al., 2023).** GPT-4 judge agreement with humans is about 85% on non-tie votes, above the human-human agreement of about 81% [memory, verify]. — [arXiv 2306.05685](https://arxiv.org/abs/2306.05685)

### Inferences
- The reliable pattern is that absolute levels shift while rankings are mostly stable. A substitute judge should be presented as preserving relative comparisons; its absolute numbers should not be treated as interchangeable with the official ones.
- From Thakur (≤5 to >10 points) and Vaugrante (up to 56 pp leniency), a gap of several percentage points between gpt-5-mini and gpt-5-chat is within the range seen in the literature. The thesis still has to measure its own gap; no paper gives it.
- Ranking stability is weakest when systems are close together. If the compared methods differ by less than the judge-swap gap, the ranking itself may flip.

### Gaps
- No study found compares gpt-5-mini vs gpt-5-chat (or any GPT-5 variants) as judges.
- HealthBench and PaperBench validate graders against humans but do not publish "system score under grader A vs grader B" tables.
- Kendall τ across judges is rarely reported.

## Q2. Text-to-SQL / code-specific LLM judges

### Takeaway
LLM judges for SQL and code report good agreement with experts only in the authors' own setups. Results depend heavily on the judge and the protocol. Independent replications are scarce.

### Cited Findings
- **FLEX (2024/2025; LLM-based text-to-SQL metric).** Cohen's κ with human experts is 87.04 (v4), against 62 for execution accuracy (EX). An earlier version reported κ 78.17. The κ changed across versions of the same method. — [arXiv 2409.19014 v4](https://arxiv.org/html/2409.19014v4)
- **LLM-SQL-Solver (2023).** Tests whether LLMs can judge SQL equivalence. FLEX's related-work section says it is "insufficient to fully replace EX". — [arXiv 2312.10321](https://arxiv.org/html/2312.10321v4)
- **ROSE (2026; Prover-Refuter text-to-SQL metric).** Claims a lead of about 24% in Cohen's κ over the next-best metric on an expert-aligned set. — [arXiv 2604.12988](https://arxiv.org/html/2604.12988)
- **Synthetic column descriptions paper (2024).** Cohen's κ between human annotators and a GPT-4o judge was only 0.16-0.25. This was a different task (description quality), but it is a caution about low judge-human agreement. — [arXiv 2408.04691](https://arxiv.org/pdf/2408.04691)
- **AgentNLQ (2026).** Reports ≥97% human-LLM judge alignment, but on only 106 + 129 samples. — [arXiv 2605.19010](https://arxiv.org/pdf/2605.19010)
- **CodeJudge (Tong & Zhang, EMNLP 2024).**
  - Reports 12.1%-41.8% higher correlations than existing methods, with ICE-Score as the main baseline.
  - Llama-3-8B-Instruct with the CodeJudge protocol beats ICE-Score with GPT-3.5-Turbo, so protocol and prompt can matter as much as the judge model.
  - Without reference code: Kendall τ 0.502 and 73.13% accuracy. — [arXiv 2410.02184](https://arxiv.org/html/2410.02184v1)
- **ICE-Score (Zhuo, EACL Findings 2024).** A 0-4 LLM score for code usefulness and functional correctness, run at temperature 0. — [arXiv 2304.14317](https://arxiv.org/abs/2304.14317); [ACL Anthology](https://preview.aclanthology.org/setup/2024.findings-eacl.148)
- **Bias in the Loop (2026).** Audits LLM-as-a-judge for software engineering. Seen in search results only. — [arXiv 2604.16790](https://arxiv.org/pdf/2604.16790)

### Inferences
- In SQL and code judging, the protocol matters about as much as the model: decomposition, step-by-step analysis, and taxonomy of errors. Changing both the model and the reasoning mode (chat to reasoning) at the same time therefore confounds two effects.

### Gaps
- No study found swaps judges on a fixed text-to-SQL rubric benchmark and reports the change in system scores.
- No CLINSQL-specific judge-replication literature was found.

## Q3. Reasoning vs non-reasoning judges

### Takeaway
On tasks with an objectively correct answer (math, code, pairwise correctness), reasoning judges are markedly more accurate, and they gain more with higher reasoning effort. On rubric or subjective grading the evidence is mixed: reasoning judges are not clearly better and may be less reliable. I found no direct published test showing reasoning judges are systematically "stricter", so that hypothesis should be argued from the thesis's own data.

### Cited Findings
- **JudgeBench.**
  - Reasoning models top the leaderboard: o3-mini-high 80.86%, o1-preview 75.43%, DeepSeek-R1 73.14%, against GPT-4o 50.86% and Claude-3.5-Sonnet 64.29%.
  - o3-mini accuracy falls as reasoning effort is lowered.
  - On coding pairs: o3-mini-high 100%, R1 92.86%, GPT-4o 61.90%. — [arXiv 2410.12784](https://arxiv.org/html/2410.12784v2)
- **HealthBench (rubric grading).** Non-reasoning GPT-4.1 (MF1 0.709) slightly beat reasoning graders o4-mini (0.692) and o3 (0.681). It was chosen partly to avoid "the cost and latency of reasoning models". — [HealthBench paper](https://huggingface.co/datasets/OnDeviceMedNotes/healthbench/blob/main/healthbench-fullpaper.md)
- **PRBench.** o4-mini is about equal to GPT-4.1 (κ about 0.60) on expert rubrics. — [arXiv 2511.11562](https://arxiv.org/pdf/2511.11562)
- **"DeepSeek-R1 vs. o3-mini" as evaluators (2025).**
  - o3-mini evaluators improve with more reasoning on machine-translation evaluation.
  - DeepSeek-R1 generally underperforms its non-reasoning counterparts.
  - The link between reasoning tokens and evaluation quality holds only for some models. — [arXiv 2504.08120](https://arxiv.org/html/2504.08120v3)
- **ACL/EMNLP 2025 Findings paper (via search snippet).** Validity of o3-mini and o4-mini was significantly lower than GPT-4o-mini, and reasoning models' reliability was ICC about 0.7 vs 0.95 for GPT-4o-mini. Not fully verified. — [2025.findings-emnlp.445](https://preview.aclanthology.org/author-page-yu-wang-polytechnic/2025.findings-emnlp.445.pdf)
- **Vaugrante & Hagendorff (2026) [abstract only].** "Lower reasoning effort had no effect on accuracy or leniency" in their tasks. — [arXiv 2610.05094](https://arxiv.org/abs/2610.05094)
- **Arize industry blog (non-peer-reviewed).** o3 as judge showed tighter score distributions, at several times the cost. — [Arize blog](https://arize.com/blog/testing-binary-vs-score-llm-evals-on-the-latest-models/)

### Inferences
- A reasoning judge on SQL correctness would plausibly catch more real errors, such as wrong filters or joins, that a chat judge lets pass. On binary leaves this would look like strictness: lower scores, but not necessarily less valid.
- This is consistent with the thesis observation, but it is an inference, not a published finding.

### Gaps
- There is no published leniency/strictness comparison of the same model family in reasoning vs chat mode on rubric grading. gpt-5-mini vs gpt-5-chat specifically is untested.

## Q4. Temperature, sampling and nondeterminism; repeated-run variance

### Takeaway
Repeated-run variance of aggregated benchmark scores is small: about 0.002 SD on HealthBench over 16 runs. Item-level verdicts near the decision boundary do flip, even at temperature 0, because of serving nondeterminism. Temperature 0.2 vs a reasoning model's fixed default sampling is therefore a minor source of aggregate gap compared with the judge model itself, but it matters per item.

### Cited Findings
- **HealthBench Table 7 (16 runs).** SD about 0.002 for overall scores ranging 0.16-0.60. For example, o3 0.5990 ± 0.0016 and GPT-4.1 0.4778 ± 0.0022. — [HealthBench paper](https://huggingface.co/datasets/OnDeviceMedNotes/healthbench/blob/main/healthbench-fullpaper.md)
- **Lau (2026) [abstract only].**
  - Even at temperature 0 there is "substantial variability".
  - Lower temperature improves stability for GPT-4o and Gemini; the effect is limited or inconsistent for Anthropic models. — [arXiv 2603.04417](https://arxiv.org/abs/2603.04417)
- **"Necessary but Not Sufficient: Temperature Control and Reproducibility in LLM-as-Judge Safety Evaluations" (Tamba, 2026; via search snippet).**
  - When temperature is unset, the provider default (1.0) applies silently, and borderline items flip pass/fail.
  - Even at temperature 0, 1-2 of 7 borderline items stayed non-reproducible.
  - Causes: batch-dependent floating-point reductions, MoE routing, and load balancing. — [arXiv 2606.26185](https://arxiv.org/abs/2606.26185)
- **"Pinned and Still Unstable" (Ayyagari, 2026; via search snippet).** Pinning the judge and setting T=0 does not guarantee reproducible verdicts on cloud serving, which creates a noise floor for leaderboards. One platform only. — [arXiv 2609.33044](https://arxiv.org/pdf/2609.33044)
- **Klishevich et al. (2025; LLM code review).** Responses varied even with minimized temperature. — [arXiv 2502.20747](https://arxiv.org/abs/2502.20747v1)

### Inferences
- The thesis should estimate its own run-to-run noise floor, for example by re-judging a subset 3-5 times, and show that the judge-swap gap is well above it.
- OpenAI reasoning models generally do not accept a custom temperature, so "matching T=0.2" is not possible. This should be stated as an unavoidable protocol difference. [This is from API behavior, not from a cited paper; verify against current API documentation.]

### Gaps
- No source quantifies T=0.2 vs T=0 vs T=1 effects specifically on rubric-aggregated scores.

## Q5. Rubric aggregation sensitivity (binary leaves, critical-first / gating)

### Takeaway
Binary per-criterion leaves combined by point-weighting or gating turn small per-criterion disagreement into larger item-level swings. Grader-level agreement on individual criteria is only moderate (MF1 about 0.6-0.7, κ about 0.6) even for the best graders, so rubric totals carry real judge-dependent noise. I found no paper that isolates "critical-first gating" amplification directly.

### Cited Findings
- **HealthBench scoring.**
  - Each criterion is worth −10 to +10 points and is judged met or not met.
  - An example's score is the sum of points for met criteria divided by the sum of positive points; the overall score is clipped to [0, 1].
  - Per-criterion grader-physician agreement is only 55-75%, similar to physician-physician agreement. — [HealthBench paper](https://huggingface.co/datasets/OnDeviceMedNotes/healthbench/blob/main/healthbench-fullpaper.md)
- **Judging the Judges.** High percent agreement (>90%) still allows score gaps above 10 points, because disagreements are not symmetric (leniency bias). — [arXiv 2406.12624](https://arxiv.org/html/2406.12624v6)
- **Vaugrante & Hagendorff (2026) [abstract only].** Rating-scale choice alone moves bias up to 0.93 points, and detailed prompts change leniency by 28.9 pp. — [arXiv 2610.05094](https://arxiv.org/abs/2610.05094)
- **CodeJudge.** Binary verdict and severity-weighted taxonomy score are two aggregation modes with different correlations to ground truth. — [arXiv 2410.02184](https://arxiv.org/html/2410.02184v1)

### Inferences
- With a "critical-first" rubric, one flipped critical leaf can zero or cap an item. If a reasoning judge is even slightly more literal on critical leaves, the item-level score difference grows larger than the leaf-level disagreement rate.
- Worked example: 5% leaf disagreement on critical leaves, with about 3 critical leaves per item, could change around 14% of items (1 − 0.95³ ≈ 0.14). This is an illustration only.
- The thesis can report leaf-level agreement (κ or percent agreement per criterion type) separately from item-level and aggregate gaps to show this amplification.

### Gaps
- No empirical study found on gating/critical-first aggregation sensitivity to judge swaps.

## Q6. Accepted practice for reporting a substituted judge and calibrating it

### Takeaway
Accepted practice has four parts:
1. Validate the judge against a reference set (humans or the official judge), using chance-corrected agreement (Scott's π or Cohen's κ, or macro-F1) plus percent agreement.
2. Report results under one fixed judge, with rank correlations.
3. Estimate and correct systematic bias with a small labeled calibration set (prediction-powered inference, PPI, or Rogan-Gladen correction).
4. Disclose judge identity and settings, report repeated-run variance, and spot-check qualitatively.

### Cited Findings
- **Judging the Judges.** Report both percent agreement and Scott's π, plus qualitative analysis. Rank-level and score-level alignment should be reported separately because they diverge. — [arXiv 2406.12624](https://arxiv.org/html/2406.12624v6)
- **HealthBench and PaperBench.** Both validate the chosen grader on a human-labeled meta-evaluation set (MF1 0.709; F1 0.83) and justify cheaper graders by cost-accuracy trade-off before scoring all systems with that one fixed grader. HealthBench also reports a 16-run SD. — [HealthBench](https://huggingface.co/datasets/OnDeviceMedNotes/healthbench/blob/main/healthbench-fullpaper.md); [PaperBench](https://arxiv.org/pdf/2504.01848)
- **Lee et al., "How to Correctly Report LLM-as-a-Judge Evaluations" (2025).**
  - Gives a bias-corrected estimator of the true accuracy from the judge's estimated sensitivity and specificity on a calibration set, with confidence intervals.
  - Shows regimes where LLM-based evaluation is more reliable than human-only evaluation. — [arXiv 2511.21140](https://arxiv.org/html/2511.21140v3)
- **Measurement-error correction framing (2026).** Rogan-Gladen-style misclassification correction and surrogate-outcome or PPI approaches are the two main correction families. — [arXiv 2601.05420 (ICML 2026 poster)](https://arxiv.org/html/2601.05420v1)
- **PRECISE (AAAI).** Applies PPI to ranking metrics. Uncorrected LLM-judge estimates showed a uniform upward bias that hid real differences between variants; correction restored the ability to tell them apart. — [AAAI PRECISE](https://ojs.aaai.org/index.php/AAAI/article/view/41427)
- **PPI for ranking evaluation (2026).** — [arXiv 2606.05308](https://arxiv.org/pdf/2606.05308)
- **Wang et al. (2023).** Balanced-position calibration and human-in-the-loop review of high-entropy cases. — [arXiv 2305.17926](https://arxiv.org/abs/2305.17926)
- **JudgeBench.** Judges each pair twice with the order swapped and counts a verdict only if consistent. Position inconsistency of fine-tuned judges was up to 59.71% (JudgeLM-7B). — [arXiv 2410.12784](https://arxiv.org/html/2410.12784v2)

### Inferences
Proposed protocol for the thesis. It is a synthesis of these practices, not a single published standard:
1. Re-judge the benchmark's officially released predictions and baseline outputs with gpt-5-mini.
2. Report the following against the official judge's scores on the same items:
   - mean paired delta with a bootstrap CI;
   - item-level percent agreement and Cohen's κ / Scott's π;
   - leaf-level agreement per criterion type;
   - Spearman / Kendall τ of system rankings.
3. Fit a simple offset or linear mapping (official ≈ a + b·adapted), or a Rogan-Gladen correction for binary leaves, and report it as an approximation. Do not overwrite raw scores with it.
4. Label all thesis numbers as "adapted-judge" scores. Make the main claims as paired deltas between the thesis method and baselines, all under the same adapted judge.
5. Report the repeated-run SD on a subset, and show that the judge gap is larger than the noise floor while the method deltas are larger than both.
6. Human spot-check the items where the judges disagree, stratified by critical vs non-critical leaves. This shows whether the reasoning judge is stricter-but-correct or simply literal.

### Gaps
- There is no community standard for "adapted judge" labeling in text-to-SQL benchmarks.
- Offset or regression mapping between two LLM judges, as opposed to a judge-to-human correction, is not formalized in the sources found. It is a reasonable extension of PPI and Rogan-Gladen but should be presented as the thesis's own method.
- The surveys suggested in the brief were not fetched in this session: "A Survey on LLM-as-a-Judge", arXiv 2411.15594 (Gu et al., 2024), and G-Eval / Prometheus correlation tables (arXiv 2303.16634, 2310.08491). The report-writer should not cite their specific numbers from these notes.
