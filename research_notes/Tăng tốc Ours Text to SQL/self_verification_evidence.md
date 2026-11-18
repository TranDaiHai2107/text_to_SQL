# LLM Self-Verification and Self-Correction in Text-to-SQL (2023-2026)

Note on verification level: items marked [verified] were confirmed against a fetched page or search result in this session. Items marked [recall] come from prior knowledge of the papers and were not re-checked; confirm them against the linked tables before quoting.

## Q1. Intrinsic self-correction without external feedback (Huang et al. and follow-ups)

### Takeaway
Without an external signal, LLM self-critique flips correct answers to wrong ones about as often as it fixes wrong ones, so net accuracy stays flat or falls. Gains show up only when an oracle or external feedback is present.

### Cited Findings
- [verified] On GSM8K, intrinsic self-correction lowered GPT-3.5 accuracy from 75.9% to 74.7% after 2 rounds. One summary gives the baseline as 77.4% instead, so check Table 3. Llama-2 fell from 62.0% to 36.5%, and GPT-4-Turbo went from 91.5% to 88.0% (round 1) and 90.0% (round 2). — [Huang et al., ICLR 2024](https://arxiv.org/abs/2310.01798)
- [verified] The cause is answer flipping. GPT-3.5 turned correct into incorrect 8.8% of the time and fixed incorrect answers 7.6% of the time. With oracle correctness labels, accuracy rose from 75.9% to 84.3%, so the reported gains come from the oracle stopping rule. — [Huang et al.](https://arxiv.org/html/2310.01798v2)
- [recall] Kamoi et al. (TACL 2024), a critical survey, find that self-correction works with reliable external feedback (code execution, tools) or with fine-tuning on large data. They found no prior work showing successful intrinsic self-correction with prompted LLMs on general tasks. — [Kamoi et al. 2024](https://arxiv.org/abs/2406.01297)
- [recall] Stechly et al. and Valmeekam et al. (2023-2024) report that GPT-4 self-critique on planning and graph coloring hurts because the verifier has many false negatives (it rejects correct solutions) and false positives. External sound verifiers help. — [Stechly et al. 2023](https://arxiv.org/abs/2310.12397)

### Inferences
- The target verifier rules on requirement satisfaction from SQL text alone, with no result rows. That is the intrinsic setting Huang et al. describe. Its 6/6 "contradicted" verdicts with no "supported" fit the strong false-negative bias reported for self-critique.

### Gaps
- No exact replication of Huang et al. on text-to-SQL with gpt-5-class reasoning models was found.

## Q2. How SOTA text-to-SQL systems use verification, correction and selection, and their ablation gains

### Takeaway
Leading systems spend compute on generating diverse candidates and then selecting among them by execution result (self-consistency, a fine-tuned selector, or pairwise comparison). Correction is mostly triggered by execution errors or empty results. Free-form LLM critique of SQL that executed cleanly is rare and gives small gains.

### Cited Findings
- [verified] CHASE-SQL (ICLR 2025), BIRD dev, Gemini 1.5 Pro: a single query scored 63.01%, self-consistency 68.84%, and the candidate upper bound 82.79%. The full system reached 73.01% on dev and 73.0% on test. The selector is a **fine-tuned** pairwise agent. Reviews note fine-tuning is crucial for it to tell similar correct and incorrect queries apart. — [CHASE-SQL](https://arxiv.org/html/2410.01943v1), [ICLR PDF](https://proceedings.iclr.cc/paper_files/paper/2025/file/974ff7b5bf08dbf9400b5d599a39c77f-Paper-Conference.pdf)
- [recall] CHASE-SQL's query fixer is execution-feedback based: it is triggered by syntax errors or empty results and runs for up to about 3 iterations. — [CHASE-SQL](https://arxiv.org/html/2410.01943v1)
- [recall] In DIN-SQL (NeurIPS 2023), removing the self-correction module cost about 1-2 points of execution accuracy on Spider dev. The paper uses a "generic" prompt for Codex and a "gentle" prompt for GPT-4, because aggressive "find the bug" prompts caused GPT-4 to break correct queries. — [DIN-SQL](https://arxiv.org/abs/2304.11015)
- [recall] MAGIC (2024) learns correction *guidelines* from DIN-SQL's failures through a manager, feedback and correction agent loop. It reports gains over DIN-SQL's self-correction on Spider and BIRD. Its premise is that DIN-SQL's hand-written self-correction prompts are weak. — [MAGIC](https://arxiv.org/abs/2406.12692)
- [recall] CHESS (2024) uses a Unit Tester agent that generates natural-language unit tests and evaluates candidates against them. It uses execution-based revision for errors and empty results. Reported BIRD test accuracy is about 66-71% depending on version. — [CHESS](https://arxiv.org/abs/2405.16755)
- [recall] MCS-SQL uses multiple prompts and multiple-choice selection over candidates that have been grouped by execution result. — [MCS-SQL](https://arxiv.org/abs/2405.07467)
- [recall] XiYan-SQL uses fine-tuned generators plus a fine-tuned selection model. ReFoRCE (Spider 2.0) uses self-refinement driven by execution feedback and majority-vote consistency. Alpha-SQL uses MCTS with a self-supervised execution-consistency reward. OmniSQL relies on fine-tuning plus self-consistency. RSL-SQL uses bidirectional schema linking with "SQL refinement" based on execution feedback. — [XiYan](https://arxiv.org/abs/2411.08599), [ReFoRCE](https://arxiv.org/abs/2502.00675), [Alpha-SQL](https://arxiv.org/abs/2502.17248), [OmniSQL](https://arxiv.org/abs/2503.02240), [RSL-SQL](https://arxiv.org/abs/2411.00073)
- [verified] In SLM-SQL, removing corrective self-consistency cost about 5 points. That is an *execution-grounded* consistency method, not an intrinsic critique. — [SLM-SQL](https://arxiv.org/pdf/2507.22478)

### Inferences
- In this literature, verification steps that pay off tend to be (a) execution-grounded, (b) comparisons between candidates rather than an absolute verdict, or (c) learned. A prompted, non-fine-tuned verifier that gives an absolute "supported or contradicted" verdict without result rows is the weakest-evidence design.

### Gaps
- Exact per-component ablation numbers for CHESS, Alpha-SQL and XiYan were not re-verified in this session.

## Q3. Execution-feedback correction compared with intrinsic critique

### Takeaway
Grounded signals do much better than self-evaluation. Signals that worked include errors, empty or NULL results, execution-result clustering, and detectors that compare an original query against its revision.

### Cited Findings
- [verified] SQLens beat the best LLM self-evaluation method by 25.78% F1 for error detection. It improved execution accuracy of out-of-the-box text-to-SQL systems by up to 20%. — [SQLens](https://arxiv.org/abs/2506.04494)
- [verified] One self-correction round raised execution accuracy only from 0.451 to 0.468. Self-reported model confidence was poorly calibrated, while an independent verifier on top of self-consistency added more. — [Selective-prediction study](https://arxiv.org/pdf/2607.06799)
- [verified] In CLINSQL, self-refinement is defined as up to 2 rounds on *failed* SQL only, with the BigQuery error message as feedback. That is execution-error feedback, not intrinsic critique. — [CLINSQL](https://arxiv.org/abs/2601.09876)

### Inferences
- Repairs triggered by errors or empty results are cheap and well supported. An always-on intrinsic verifier on SQL that executed cleanly is not.

### Gaps
- No head-to-head cost comparison in seconds per query was found.

## Q4. Failure modes: over-rejection, verifier bias, correction degrading correct SQL

### Takeaway
The documented failure modes are flipping correct answers to wrong, false-negative-heavy verifiers, and regressions caused by unconditional repair. The common mitigations are an auditor that accepts a fix only if it is safe, and accepting a change only when the signal is grounded.

### Cited Findings
- [verified] SQLens reports that LLM self-reflection breaks correct queries. Its SQL Auditor compares the original and revised queries before accepting a fix, which reduces regressions. — [SQLens](https://arxiv.org/pdf/2506.04494)
- [verified] In Huang et al., correct-to-incorrect flips (8.8%) outnumbered incorrect-to-correct fixes (7.6%). — [Huang et al.](https://arxiv.org/html/2310.01798v2)
- [recall] DIN-SQL found that GPT-4 with a "generic" (assume buggy) correction prompt broke correct SQL, so it switched to a "gentle" prompt. — [DIN-SQL](https://arxiv.org/abs/2304.11015)
- [recall] Verifiers in LLM-as-judge setups show position, self-preference and harshness biases. Stechly et al. report many false negatives from GPT-4 as a verifier. — [Stechly et al.](https://arxiv.org/abs/2310.12397)

### Inferences
- A verifier that returned "contradicted" for 6/6 candidates, including after repair, carries no discriminative signal. If it never says "supported", it cannot rank candidates and only adds latency: about 49% of runtime in the target system. This matches the over-rejection pattern above.

### Gaps
- No published calibration study was found for requirement verifiers on clinical SQL specifically.

## Q5. Clinical/EHR text-to-SQL results

### Takeaway
CLINSQL's own baseline uses only error-triggered refinement. gpt-5-mini reaches 74.7% with it, and the paper reports no intrinsic-verifier gains. The dominant errors are cohort specification and output schema, which a SQL-only verifier with no result rows struggles to judge.

### Cited Findings
- [verified] CLINSQL (EACL 2026) has 633 expert tasks on MIMIC-IV v3.1 BigQuery. GPT-5-mini scores 74.7% on test, DeepSeek-R1 69.2%, and Gemini-2.5-Pro falls from 85.5% on Easy to 67.2% on Hard. Error shares are Cohort Specification and Coding 54%, Output Schema and Formatting 24%, and Aggregation and Clinical Statistics 14%. Refinement is up to 2 rounds using BigQuery errors. — [CLINSQL arXiv](https://arxiv.org/abs/2601.09876)
- [recall] EHRSQL (NeurIPS 2022 D&B, with a 2024 shared task) emphasizes *abstention* and reliability scoring, which penalizes wrong answers. Shared-task entries used execution-based filtering and abstention rather than self-critique. — [EHRSQL](https://arxiv.org/abs/2301.07695)

### Inferences
- The strongest published baseline on this benchmark, with this same model, uses no intrinsic verifier. Removing the verifier, or gating it to error/empty/suspicious-result cases, is supported by the evidence.

### Gaps
- The CLINSQL paper's numeric breakdown for gains from self-refinement rounds was not retrieved. No MIMICSQL study of self-verification was found.
