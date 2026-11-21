# Diverse candidate generation vs identical-prompt sampling at fixed N (text-to-SQL, BIRD dev)

## Q1. CHASE-SQL: per-generator accuracy, upper bound from mixing generators, equal-candidate-count comparisons

### Takeaway
CHASE-SQL's mixed generators raise the oracle (upper bound) a lot, but the gain from mixing under plain self-consistency is small. Most of its benefit comes from a fine-tuned pairwise selector, not from the vote. The paper does not give an equal-N "single generator vs mix" comparison under majority vote in text form; the only candidate-count curves (Fig. 2) are figures with no numbers in the text.

### Cited Findings
- Table 1 (Gemini 1.5 Pro, BIRD dev): single query 63.01; self-consistency 68.84 (+5.84); upper bound 82.79 (+19.78). The final system used 7 candidates per generator x 3 generators = 21 candidates. — [CHASE-SQL arXiv 2410.01943](https://arxiv.org/html/2410.01943)
- Table 4 (Gemini 1.5 Pro, one candidate per generator, BIRD dev EX): baseline zero-shot CoT 57.75; Query-Plan CoT 63.62; Divide-and-Conquer CoT 63.92; Online Synthetic examples 67.09. With the query fixer: 61.58 / 65.51 / 65.77 / 68.02. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Table 6 (BIRD dev, 10 samples per generator, model not named in the text; lower bound / upper bound / self-consistency / selection agent):
  - QP T=0.5: 50.46 / 78.55 / **65.78** / 71.70
  - QP T=1.8: 48.63 / 80.44 / 65.51 / 71.73
  - DC T=0.5: 51.37 / 78.42 / **66.43** / 71.31
  - DC T=1.8: 47.39 / 79.34 / 64.41 / 70.53
  - OS T=0.5: 60.43 / 74.77 / **67.34** / 70.40
  - OS T=1.8: 50.98 / 79.66 / 66.88 / 71.38

  Self-consistency within one generator lands at about 64-67 regardless of generator. A single generator's upper bound at 10 samples is already 75-80, against 82.79 for all three generators with 21 candidates. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Table 7 ablations (full system 73.01, Gemini 1.5 Pro): self-consistency instead of the selector 68.84 (-4.17); ranker instead of the selector 65.51; w/o QP 72.36 (-0.65); w/o OS 72.16 (-0.85); w/o DC 71.77 (-1.24). Dropping any single generator costs under 1.3 points when the trained selector is kept. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Diversity knobs: "we increase the next token sampling temperature, and also shuffle the order of columns and tables in the prompt". "Increasing the sampling temperature raises the upper bound but also lowers the lower bound", and the effect is stronger for the online-synthetic generator. Growing the pool "beyond 20 did not yield significant improvements". No numeric ablation of column/table shuffling is given. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Why self-consistency is limited: it "would assume that the most consistent answer is always the best one", and it "can inadvertently exclude correct queries that are less frequent". — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- The selector needs fine-tuning. Binary selection accuracy: untuned Gemini-1.5-pro 63.98 (Sec. 3.5 says 58.01, which is inconsistent), untuned Claude-3.5-Sonnet 60.21, tuned Gemini-1.5-flash 71.01. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Error breakdown (Fig. 5): 72.9% correct; 10.4% where a correct candidate existed but was not chosen; 6.7% with no correct candidate; 10.0% with a wrong gold query. — [CHASE-SQL](https://arxiv.org/html/2410.01943)

### Inferences
- The best per-generator self-consistency at 10 samples (64.4-67.3) and self-consistency over all 21 mixed candidates (68.84) are only about 1.5-4 points apart, and the mix has more than twice the candidates. Under majority vote, mixing generators gives a small gain at best. The large gains come from a selector that can choose minority-correct answers. This matches the student's finding that 4 enriched + 4 QP = 63.6 = 8 enriched.
- The student's QP-only result (62.45) sits below their enriched-only result (63.6). In CHASE, the QP/DC/OS self-consistency numbers are within about 2 points of each other. Mixing a weaker generator into a vote tends to dilute vote concentration, consistent with the student's mean of 63.9 ± 0.35 for random 4+4 subsets.
- Temperature trades the lower bound against the upper bound. At fixed N with majority vote, a very high T (CHASE's 1.8) slightly *lowered* self-consistency for DC and QP. A moderate T is safer for voting.

### Gaps
- Fig. 2 (upper and lower bound vs number of candidates per generator) and the Fig. 3 Venn counts of correct answers unique to each generator are only available as figures. I found no text numbers for equal-N single-vs-mixed under self-consistency.
- Table 6's model is not named in the text (probably Gemini 1.5 Pro, not confirmed).
- I found no CHASE-SQL numbers with gpt-4o-mini.

## Q2. Other text-to-SQL systems (XiYan, OpenSearch-SQL, MCS-SQL, Pi-SQL, etc.): gains at equal N vs single-prompt self-consistency?

### Takeaway
Almost no text-to-SQL paper holds N fixed while varying diversity. The closest evidence:
- Pi-SQL (gpt-4o-mini, BIRD dev): mixing 3 generation strategies beats the best single strategy by about 1-2 EX.
- MCS-SQL: moving from 1 to 5 prompts (with more candidates) gives +1.3 on BIRD dev.
- OpenSearch-SQL deliberately uses one prompt with 21 samples.

XiYan's diversity depends on fine-tuned generators.

### Cited Findings
- **MCS-SQL** (GPT-4 8K via Azure, T=1.0, n=20 samples per prompt, p_q=5 SQL prompts that differ in few-shot selection strategy (question vs masked-question similarity) and example order; schema-linking prompts shuffle table/column order):
  - BIRD dev ablation (cumulative): few-shot 60.0; + MCS (p_q=1, n=20 → 20 candidates) 62.1; + MCS (p_q=5, n=20 → 100 candidates) 63.4 (+1.3).
  - Spider dev: 88.8 → 89.5 (+0.7).
  - **This is not equal N** (20 vs 100 candidates). — [MCS-SQL arXiv 2405.07467](https://arxiv.org/html/2405.07467)
- MCS-SQL selection (BIRD dev / Spider dev): majority vote 62.8 / 89.2; MCS (multiple-choice selection by the LLM) without confidence filter 62.5 / 85.4; MCS with confidence filter (drop candidates whose execution-result share is < 0.2) 63.4 / 89.5. A training-free LLM selector only beats majority vote after low-consistency candidates are filtered out. — [MCS-SQL](https://arxiv.org/html/2405.07467)
- MCS-SQL schema-linking recall (BIRD/Spider dev): 1 prompt, n=1: 61.3/91.8; 1 prompt, n=20: 77.1/96.5; 3 shuffled-order prompts, n=20: 89.8/99.2. Schema-order shuffling raises *coverage* for schema linking. There is no separate EX ablation for shuffling. — [MCS-SQL](https://arxiv.org/html/2405.07467)
- MCS-SQL few-shot selection (BIRD/Spider dev EX): random 57.0/82.0; question similarity 59.3/86.2; masked-question similarity 60.0/86.7. — [MCS-SQL](https://arxiv.org/html/2405.07467)
- **Pi-SQL** (gpt-4o-mini, T=0 for main runs, BIRD dev; Python "pivot" programs guide SQL):
  - Vanilla+SC with N=11 SQLs at T=0.5, matched to Pi-SQL's token cost: 59.71 EX. Pi-SQL: 64.54 EX.
  - Single strategy: merge-first 61.93, filter-first 61.99, direct 62.58. Mixed (all three): 64.54, +1.96 over the best single strategy.
  - Mixed + plain SC over SQL execution results: 63.62, i.e. about +1.0 over the best single strategy under a vote-like selector.
  - The number of candidates per strategy is not stated explicitly. — [Pi-SQL arXiv 2506.00912](https://arxiv.org/html/2506.00912)
- **XiYan-SQL** (preview, arXiv 2411.08599): generators are 2 fine-tuned SQL models (two-stage multi-task training; **needs fine-tuning**) + 1 ICL generator using GPT-4o.
  - Default 3 candidates: 71.58 (the text says 71.51). 5 candidates: 73.34.
  - w/o fine-tuned generator: 68.67; w/o ICL generator: 70.27; self-consistency instead of the selection model: 68.84 (about -3).
  - No per-generator EX, no upper bound, no shuffling ablation.
  - Table 2's 75.63 split is ambiguous in that version. — [XiYan-SQL](https://arxiv.org/html/2411.08599)
- **OpenSearch-SQL** (GPT-4o-0513, BIRD): "we only use a single prompt ... to generate a SQL candidate set"; 21 samples at T=0.7.
  - Dev EX 69.3 full vs 67.8 single SQL.
  - Mini-Dev: removing self-consistency & vote drops 70.6 → 68.2; the gain is concentrated on difficult questions (+7.64).
  - Candidate sweep N ∈ {1,3,7,15,21}: GPT-4o keeps improving; **GPT-4o-mini peaks at 7 and 15 candidates** (values only in Fig. 4).
  - Structured CoT widens the vote gain (EX_V − EX_G: no CoT +1.6, unstructured CoT +4.8, structured CoT +6.2). — [OpenSearch-SQL arXiv 2502.14913](https://arxiv.org/html/2502.14913)
- **CSC-SQL**: voting loses effectiveness when candidates are not diverse; lower temperature gave less diversity and lower scores, and they chose T=0.8. This is from a search-result summary; I did not verify it against the full text, and CSC-SQL uses RL fine-tuning. — [CSC-SQL arXiv 2505.13271](https://arxiv.org/pdf/2505.13271)

### Inferences
- With gpt-4o-mini (the student's model), Pi-SQL is the closest analogue: a mix of reasoning *strategies* (different decompositions such as merge-first vs filter-first) gave about +1 EX under self-consistency. Pi-SQL's strategies are structurally different "pivot program" paths, which is a stronger kind of diversity than two prompts in the same CoT style.
- MCS-SQL's prompt diversity is few-shot set/order and schema order. Its +1.3 came with 5x more candidates, so at equal N the effect is likely smaller (unverified).
- OpenSearch-SQL's GPT-4o-mini curve peaking around 7-15 candidates suggests vote gains for this model saturate close to N=8. More gains would have to come from candidate quality or selection, not quantity.

### Gaps
- I did not research Distillery, PURPLE, DAIL-SQL few-shot selection, Agentar-Scale-SQL, Alpha-SQL or DPC (arXiv 2604.15163, a training-free dual-paradigm consistency selector reporting pass@5 on BIRD) because of the tool budget. DAIL-SQL and PURPLE concern few-shot *selection*, not fixed-N diversity.
- I found no BIRD paper that varies the generator mix at equal N under majority vote.

## Q3. General LLM literature: diversity vs sampling at fixed budget; coverage vs vote concentration

### Takeaway
The cleanest fixed-budget result is DiVeRSe on GSM8K (not SQL). With 100 paths, 5 prompts x 20 samples (80.0) beat 1 prompt x 100 (76.7), and 100 prompts x 1 sample (73.0) was the worst. A few prompts each sampled several times is best. Diversity mainly raises coverage (pass@k). Majority vote can stall or even drop as calls are added (Chen et al.).

### Cited Findings
- **DiVeRSe** (Li et al., ACL 2023; code-davinci-002, GSM8K, majority voting, fixed M=100):
  - 1x100 = 76.7; 5x20 = **80.0**; 10x10 = 79.8; 100x1 = 73.0.
  - 1x100 vs 5x20 on other models and datasets: text-davinci-002 GSM8K 58.2 → 61.3, CommonsenseQA 72.9 → 77.3; code-davinci-002 CSQA 77.3 → 78.8, CLUTRR 35.6 → 43.8; davinci GSM8K 18.9 → 21.3.
  - Verbatim: "neither only using diverse prompts nor only using sampling is optimal"; "the best performance is achieved by combining diverse prompts and sampling." The prompts there differ in their few-shot exemplars. — [DiVeRSe arXiv 2206.02336](https://ar5iv.labs.arxiv.org/html/2206.02336)
- **DIV-SE** (Naik et al., "Diversity of Thought Improves Reasoning Abilities of LLMs"; GPT-3.5-Turbo / GPT-4 / LLaMA-2-70B; non-SQL). Prompts vary *approach* and *persona*; the approach/persona pairs are chosen on a validation set of fewer than 20 questions; majority vote.
  - At equal ensemble size: AQuA-RAT GPT-3.5 ZS: SC-5 63.37 vs DIV-SE 72.83; Blocksworld-3 GPT-4: SC-3 66.0 vs 94.0; Graph Coloring GPT-4: SC-3 18.0 vs 97.0 (graph coloring uses an external verifier).
  - Gains are small or absent on easier or saturated tasks: GPT-4 CommonsenseQA 81.70 vs 81.60; LLaMA-2-70B IDIV-SE 27.00 < CoT 31.32. — [DIV-SE arXiv 2310.07088](https://arxiv.org/html/2310.07088v2)
- **PlanSearch** (Claude 3.5 Sonnet, LiveCodeBench, code generation): pass@200 77.0 with diverse natural-language plans vs 60.6 for repeated sampling, against pass@1 41.4 without search. The authors predict search gains "as a direct function of the diversity of generated ideas". This is a coverage (pass@k) result, not a majority-vote result. — [PlanSearch arXiv 2409.03733](https://arxiv.org/abs/2409.03733)
- **Chen et al. 2024** ("Are More LLM Calls All You Need?", NeurIPS 2024): Vote and Filter-Vote accuracy is often *non-monotone* in the number of calls. More calls help "easy" queries and hurt "hard" ones, where the majority is wrong. A scaling model fit on a few samples can predict the call count that maximizes accuracy. — [Chen et al. arXiv 2403.02419](https://arxiv.org/html/2403.02419v2)

### Inferences
- Coverage vs concentration: diversity raises pass@k (CHASE single-generator upper bound 75-80 → 82.79 mixed; PlanSearch 60.6 → 77.0). A majority vote only captures that coverage if the correct answer is still the plurality. For queries where both prompts are mostly right, mixing does nothing. For "hard" queries, a weaker generator adds wrong mass. The student's 63.6 = 63.6 is the expected outcome when the second prompt is about 1 point weaker and highly correlated with the first.
- DiVeRSe's optimum (5-10 prompts with several samples each, not 1 prompt and not all-distinct prompts) suggests a small number of prompt variants, each sampled 2-4 times at N=8. Examples: 4x2 or 2x4 with *exemplar/schema-order* variation of the strong prompt, rather than swapping to a weaker prompt family. This is an extrapolation from GSM8K at M=100 to SQL at N=8 and is unverified.
- DIV-SE's gains came from *validated* approach choices: approaches were kept only if they scored well on a small dev set. This implies that diverse prompts should each be individually close to the best prompt's accuracy before mixing.

### Gaps
- I found no fixed-N study of "temperature mixing" (e.g., greedy + 7 sampled) or "mixture-of-prompts" in SQL.
- I did not find "Self-consistency with diverse reasoning paths" literature beyond DiVeRSe and DIV-SE.

## Q4. Practical guidance: allocating 8 samples across k prompts; voting when generators differ in accuracy

### Takeaway
Under plain majority vote, published evidence favors:
- (a) keeping most samples on the strongest prompt and diversifying it with variants of comparable accuracy (few-shot set/order, schema order, alternative decomposition strategies), not adding a weaker prompt family;
- (b) moderate temperature;
- (c) a better aggregation rule: confidence filtering plus an LLM selector, or cross-verification.

Better aggregation, not the mix itself, is where the published systems get most of their gain.

### Cited Findings
- Fixed M=100, GSM8K: 5x20 (80.0) ≥ 10x10 (79.8) > 1x100 (76.7) > 100x1 (73.0). — [DiVeRSe](https://ar5iv.labs.arxiv.org/html/2206.02336)
- MCS-SQL (GPT-4, BIRD dev): majority vote 62.8 < LLM multiple-choice selection with confidence threshold 0.2 at 63.4. Without the filter, MCS is worse than the vote (62.5). The selection lists candidates in descending confidence order and takes a majority over 20 selector samples. — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Pi-SQL (gpt-4o-mini, BIRD dev): on the same mixed candidate pool, cross-verification against the Python programs' majority execution result gave 64.54 vs 63.62 for plain SQL self-consistency. — [Pi-SQL](https://arxiv.org/html/2506.00912)
- In CHASE-SQL, self-consistency over the mixed pool (68.84) is 4.17 below the trained selector (73.01), and 10.4% of questions had a correct candidate that was not chosen. — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- In CHASE-SQL, high temperature (T=1.8) widens the upper bound but reduces self-consistency for the QP and DC generators (65.78 → 65.51; 66.43 → 64.41). — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Vote accuracy can be non-monotone in the number of calls. Fitting a small model to predict the optimum is recommended. — [Chen et al.](https://arxiv.org/html/2403.02419v2)

### Inferences
These are reasoning from the findings above and need validation on the student's data.
- With gpt-4o-mini and enriched=63.6 vs QP=62.45, a 6+2 or 7+1 split will likely be within noise of 8+0. Expect no gain unless QP's correct answers are disjoint from the enriched prompt's errors. The student can check this offline: on their existing 16 samples, count the questions where the vote is wrong but the QP samples contain the correct execution result.
- Weighted voting when generators differ in accuracy: weight each sample's vote by its generator's dev accuracy, or break ties in favor of the stronger generator. I found no SQL paper quantifying this; treat it as untested. MCS-SQL's confidence-filter-then-select scheme is the closest published training-free alternative.
- Equal-N diversity sources most likely to help, by evidence strength:
  1. Structurally different decomposition strategies of similar accuracy (Pi-SQL +1-2 with gpt-4o-mini).
  2. Few-shot exemplar set/order variation (DiVeRSe; MCS-SQL).
  3. Schema/column order shuffling (CHASE; MCS-SQL; this raises schema-linking recall but has no isolated EX number).
  4. Higher temperature (raises the oracle and can lower the vote).

### Gaps
- No published BIRD result compares 8 samples from one prompt against 4+4 or 6+2 splits under execution-result majority vote. The student's own experiment appears to be among the few such measurements.
- I found no published numbers for "greedy + 7 sampled" allocations in text-to-SQL.
