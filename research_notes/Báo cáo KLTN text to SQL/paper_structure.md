# How LLM-based text-to-SQL papers (2023-2026) and Vietnamese CS theses (KLTN) are structured: a writing guide for a training-free agentic text-to-SQL thesis

Scope note: section headings below were read from the arXiv HTML / ar5iv renderings of each paper (the latest arXiv version available on 2026-11-21). Camera-ready versions at the venue may differ slightly. Where the fetch was truncated (mostly appendices), this is stated.

---

## Q1. Section headings, order, and content of the 10 reference papers

### Takeaway
Nearly all ten papers follow the same skeleton: Abstract, Introduction (with a contribution list), Related Work (placed second, or near the end in ACL-style papers like MAC-SQL), Method (an overview subsection with Figure 1/2, then one subsection per pipeline component), Experiments (Setup: datasets / metrics / baselines / implementation details, then Main Results, then Ablation, then extra analyses), Conclusion, References, and appendices holding prompts and error analysis. Only the ACL/COLING and NeurIPS-era papers (DIN-SQL, MAC-SQL) have a dedicated Limitations section. MAC-SQL is the only one with an Ethics Statement, and Alpha-SQL (ICML) has an Impact Statement.

### Verified bibliographic details (venue, year, arXiv ID)
| Paper | Authors (first … last) | Venue / year (verified) | arXiv ID | Sources |
|---|---|---|---|---|
| DIN-SQL | Mohammadreza Pourreza, Davood Rafiei | NeurIPS 2023 (37th Conf. on Neural Information Processing Systems), poster | 2304.11015 | [NeurIPS virtual](https://neurips.cc/virtual/2023/poster/70430); [NeurIPS PDF](https://papers.neurips.cc/paper_files/paper/2023/file/72223cc66f63ca1aa59edaec1b3670e6-Paper-Conference.pdf); [ar5iv](https://ar5iv.labs.arxiv.org/html/2304.11015) |
| DAIL-SQL ("Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation") | Dawei Gao, Haibin Wang, Yaliang Li, Xiuyu Sun, Yichen Qian, Bolin Ding, Jingren Zhou (Alibaba) | PVLDB 17(5): 1132-1145, 2024, doi:10.14778/3641204.3641221 | 2308.15363 | [VLDB PDF](https://www.vldb.org/pvldb/vol17/p1132-gao.pdf); [ar5iv](https://ar5iv.labs.arxiv.org/html/2308.15363) |
| MAC-SQL | Bing Wang, Changyu Ren, Jian Yang, Xinnian Liang, Jiaqi Bai, LinZheng Chai, Zhao Yan, Qian-Wen Zhang, Di Yin, Xing Sun, Zhoujun Li | COLING 2025 (Proc. 31st Int. Conf. on Computational Linguistics), pp. 540-557, Abu Dhabi; Anthology ID 2025.coling-main.36 | 2312.11242 (v6, 18 Mar 2025) | [ACL Anthology](https://aclanthology.org/2025.coling-main.36); [arXiv HTML](https://arxiv.org/html/2312.11242) |
| CHESS ("Contextual Harnessing for Efficient SQL Synthesis") | Shayan Talaei, Mohammadreza Pourreza, Yu-Chen Chang, Azalia Mirhoseini, Amin Saberi | arXiv preprint (v3 revised 25 Nov 2024); no peer-reviewed venue found | 2405.16755 | [arXiv HTML](https://arxiv.org/html/2405.16755) |
| CHASE-SQL ("Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL") | Mohammadreza Pourreza, Hailong Li, Ruoxi Sun, Yeounoh Chung, Shayan Talaei, Gaurav Tarlok Kakkar, Yu Gan, Amin Saberi, Fatma Özcan, Sercan Ö. Arık | ICLR 2025 (poster, in ICLR 2025 proceedings) | 2410.01943 | [ICLR proceedings](https://proceedings.iclr.cc/paper_files/paper/2025/hash/974ff7b5bf08dbf9400b5d599a39c77f-Abstract-Conference.html); [arXiv HTML](https://arxiv.org/html/2410.01943) |
| OmniSQL ("Synthesizing High-quality Text-to-SQL Data at Scale") | Haoyang Li, Shang Wu, Xiaokang Zhang, Xinmei Huang, Jing Zhang, Fuxin Jiang, Shuai Wang, Tieying Zhang, Jianjun Chen, Rui Shi, Hong Chen, Cuiping Li (Renmin Univ. & ByteDance) | PVLDB Vol. 18, No. 11, 2025 (per paper's PVLDB Reference Format) | 2503.02240 (v2, 13 Jul 2025) | [arXiv HTML](https://arxiv.org/html/2503.02240) |
| RSL-SQL ("Robust Schema Linking in Text-to-SQL Generation") | Zhenbiao Cao, Yuanlei Zheng, Zhihao Fan, Xiaojin Zhang, Wei Chen, Xiang Bai | arXiv preprint (v2, 26 Nov 2024); no venue found | 2411.00073 | [arXiv HTML](https://arxiv.org/html/2411.00073) |
| XiYan-SQL ("A Novel Multi-Generator Framework For Text-to-SQL") | Yifu Liu, Yin Zhu, Yingqi Gao, Zhiling Luo, Xiaoxia Li, Xiaorong Shi, Yuntao Hong, Jinyang Gao, Yu Li, Bolin Ding, Jingren Zhou (Alibaba Cloud) | arXiv preprint (v2 revised 06 Apr 2026); venue not stated | 2507.04701 (earlier 2024 preliminary version: 2411.08599, not fetched) | [arXiv HTML](https://arxiv.org/html/2507.04701) |
| Alpha-SQL ("Zero-Shot Text-to-SQL using Monte Carlo Tree Search") | Boyan Li, Jiayi Zhang, Ju Fan, Yanwei Xu, Chong Chen, Nan Tang, Yuyu Luo | ICML 2025, PMLR 267: 36810-36830 | 2502.17248 | [PMLR](https://proceedings.mlr.press/v267/li25dt.html); [arXiv HTML](https://arxiv.org/html/2502.17248) |
| MCS-SQL ("Leveraging Multiple Prompts and Multiple-Choice Selection For Text-to-SQL Generation") | Dongjun Lee, Choongwon Park, Jaehyuk Kim, Heesoo Park (Dunamu) | COLING 2025, pp. 337-353, Abu Dhabi; Anthology ID 2025.coling-main.24 | 2405.07467 | [ACL Anthology](https://aclanthology.org/2025.coling-main.24); [arXiv HTML](https://arxiv.org/html/2405.07467) |

### Cited Findings: exact section headings

**DIN-SQL** ([ar5iv](https://ar5iv.labs.arxiv.org/html/2304.11015)): Abstract, then 1 Introduction, then 2 Related Work, then **3 Few-shot Error Analysis** (a motivating error study placed *before* the method), then 4 Methodology (4.1 Schema Linking Module; 4.2 Classification & Decomposition Module; 4.3 SQL Generation Module; 4.4 Self-correction Module), then 5 Experiments (5.1 Models; 5.2 Hyperparameter; 5.3 Dataset; 5.4 Metrics; 5.5 Results with 5.5.1 Test set results, 5.5.2 Development set results, 5.5.3 Error improvements; 5.6 Ablation study), then 6 Conclusions, then **7 Limitations**, then Acknowledgement, References, and Appendix A Prompts (A.1 Zero-shot prompting … A.6 Self-correction prompts).

**DAIL-SQL** ([ar5iv](https://ar5iv.labs.arxiv.org/html/2308.15363)): 1 Introduction, then **2 Preliminary**, then 3 Methodology (3.1 Question Representation; 3.2 In-Context Learning for Text-to-SQL with 3.2.1 Example Selection and 3.2.2 Example Organization; 3.3 DAIL-SQL; 3.4 Supervised Fine-Tuning for Text-to-SQL), then 4 Experiment (4.1 Setting; 4.2 Question Representations; 4.3 In-Context Learning …; 4.4 Supervised Fine-Tuning … (4.4.1-4.4.4); **4.5 Token Efficiency**), then **5 Discussion**, then 6 Conclusions, then References. Appendices (cross-referenced only): A Details of DAIL-SQL (A.1 Pseudocode; A.2 Implementation Details) … **E Efficiency (E.1 Financial Efficiency; E.2 Time-Consuming)**.

**MAC-SQL** ([arXiv HTML](https://arxiv.org/html/2312.11242)): 1 Introduction, then 2 Preliminaries (**2.1 Problem Definition of Text-to-SQL**; 2.2 Large Language Model for Text-to-SQL), then 3 MAC-SQL Framework (3.1 Overview; 3.2 Selector; 3.3 Decomposer; 3.4 Refiner), then 4 SQL-Llama Model, then 5 Experiments (5.1 Experimental Setup: Datasets, Evaluation Metrics, Baselines; 5.2 Overall Performance; 5.3 Ablation Study; 5.4 Discussion; **5.5 Error Analysis**), then **6 Related Work** (placed late), then 7 Conclusion, then **Limitations; Ethics Statement**; Acknowledgments; References. Appendices: A Implementation Details (per agent); B Prompt Details; C Error Type Examples.

**CHESS** ([arXiv HTML](https://arxiv.org/html/2405.16755)): 1 Introduction, then 2 Related Work, then 3 Methodology (3.1 Agents: Descriptions and Tools; 3.2 Preprocessing; 3.3 Adapting Text-to-SQL Systems for Real-World Deployment), then 4 Experiments and Results (4.1 Datasets and Metrics; **4.2 Different Configurations of CHESS per Deployment Constraints**, with 4.2.1 "…for High Computational Budget" and 4.2.3 "…for Limited Computational Budget"; 4.3 Ablation Studies), then **5 Conclusion and Limitations**, then References. Appendices: A Implementation Details; B Finetuning …; C Prompt Templates; D Extended Experiments (D.1 Query Generation with the Correct Context; D.2 Models Ablation); E Schema Selection Example; **F Error Analysis** (F.1 Incorrectly Predicted SQL, subdivided into F.1.1 Column … F.1.9 SELECT; F.2 Vague Question; F.3 Incorrect Golden SQL).

**CHASE-SQL** ([arXiv HTML](https://arxiv.org/html/2410.01943)): 1 Introduction, then 2 Related Work, then 3 Methods (3.1 Overall Framework; 3.2 Value Retrieval; 3.3 Multi-path Candidate Generation; 3.4 Query Fixer; 3.5 Selection Agent), then 4 Experiments (4.1 Datasets and Models; 4.2 BIRD results; 4.3 Spider results; 4.4 Generator and selection performance; 4.5 Ablation Studies), then 5 Conclusion, then References. Appendix A: A.1 Related works; A.2 Models; **A.3 Performance Based On Database**; **A.4 Error Analysis** (A.4.1 Selection Agent Error Analysis; A.4.2 Error Analyses); A.5-A.8 prompts; A.9 Generated Synthetic Examples Analysis; A.10 prompts.

**OmniSQL** ([arXiv HTML](https://arxiv.org/html/2503.02240)): 1 Introduction, then 2 Related Work (2.1 Text-to-SQL; 2.2 Data Augmentation …), then 3 Data Synthesis Framework (3.1 Overview … 3.5), then 4 SynSQL-2.5M (4.1-4.5 including 4.5 Data Quality Evaluation), then 5 OmniSQL (5.1 Input-Output Construction; 5.2 Supervised Fine-Tuning), then 6 Experiments (**6.1 Experimental Setup: 6.1.1 Evaluation Datasets; 6.1.2 Evaluation Metrics; 6.1.3 Implementation Details; 6.1.4 Environments; 6.1.5 Baselines; 6.1.6 Inference Strategy**; 6.2 Main Results; 6.3 Ablation studies (6.3.1-6.3.4); 6.4 Comparison with Data Augmentation), then 7 Conclusion, then References. No Limitations section.

**RSL-SQL** ([arXiv HTML](https://arxiv.org/html/2411.00073)) uses IEEE-style Roman numbering: I Introduction, then II Related Work, then III Method (III-A Prompt Engineering; III-B Step 1: Bidirectional Schema Linking; III-C Step 2: Contextual Information Augmentation; III-D Step 3: Binary Selection Strategy; III-E Step 4: Multi-Turn Self-Correction), then IV Experiment (IV-A Datasets, including **IV-A3 Subsampled Development Set**; IV-B Evaluation Metrics: EX, VES, NSR, SRR; IV-C Baseline Methods), then **V Results and Analysis** (V-A Main Results; V-B Analysis including **V-B3 Token Consumption and Cost**; V-C Ablation Study), then **VI Case Study** (VI-A Maximize Positive Gain; VI-B Minimize Negative Impact), then VII Conclusion. No appendix and no limitations section.

**XiYan-SQL** ([arXiv HTML](https://arxiv.org/html/2507.04701)), IEEE-style: I Introduction, then II Related Work, then III Methodology (III-A Overall Framework; III-B Schema Filter; III-C Multiple SQL Generation; III-D SQL Selection), then IV Experiments (IV-A Experimental Setup; IV-B Main Results; IV-C Ablation Study; IV-D through IV-G "Study of" each component; IV-H Analysis of Results from Different SQL Generators; **IV-I Analysis of Cost Efficiency**; **IV-J Study of Generalization**), then V Discussion, then VI Conclusion. Appendices I-VI are referenced but were not captured. No limitations section.

**Alpha-SQL** ([arXiv HTML](https://arxiv.org/html/2502.17248)): 1 Introduction, then 2 Related Work, then 3 Alpha-SQL (**3.1 Zero-shot Text-to-SQL** [task definition]; 3.2 An Overview of Alpha-SQL), then 4 The Design Details of Alpha-SQL (4.1 LLM-as-Action-Model; 4.2 MCTS for Candidate SQL Generation; 4.3 Database Value Retrieval), then 5 Experiments (5.1 Experimental Setup; 5.2 Main Results on BIRD and Spider; **5.3 Impact of MCTS Rollouts on Performance**; 5.4 Comparison with Baseline LLMs; 5.5 Ablation Study of Action Space), then 6 Conclusion, then Acknowledgements, then **Impact Statement**, then References. Appendix A: A.1 Algorithm; A.2-A.4 prompt templates (including **A.4 Prompt Template for Baseline LLMs**).

**MCS-SQL** ([arXiv HTML](https://arxiv.org/html/2405.07467)): Introduction, then Related Work, then 3 Methodology (3.1 Schema Linking; 3.2 Multiple SQL Generation; 3.3 Selection with 3.3.1 Candidate Filtering and 3.3.2 Multiple-Choice Selection), then **4 Experimental Setup** (4.1 Datasets; 4.2 Evaluation Metrics; 4.3 Implementation Details; 4.4 Baselines), then **5 Results and Analysis** (5.1 Main Results; 5.2 Ablation Study; 5.3-5.5 "Impact of …" analyses), then Conclusion, then References, then **Appendix A: Error Analysis**, then Appendix B: Prompts. No Limitations or Ethics section in the arXiv v1. The COLING camera-ready may add one; not verified.

### Inferences
- The canonical order for an agentic, training-free pipeline paper is: Problem definition, Overview figure, one subsection per agent/module, Setup, Main results, Ablation (leave-one-out or incremental add-one), Component analyses ("Study of X" / "Impact of X"), Cost, Error analysis, Case study, Conclusion/Limitations. MCS-SQL and RSL-SQL show the cleanest "Experimental Setup" and "Results and Analysis" split into two top-level sections.
- Putting a motivating error analysis before the method (DIN-SQL §3) works well when the method is designed to fix observed failure types.

### Gaps
- Camera-ready (venue) versions of MAC-SQL, MCS-SQL, CHASE-SQL and DIN-SQL may add Limitations sections required by COLING/ICLR/NeurIPS checklists. I read only arXiv versions.
- XiYan-SQL 2411.08599 (the 2024 preliminary version) was not fetched, and the venue of 2507.04701 was not found.
- I could not find a venue for OmniSQL's PVLDB page numbers or DOI. Only "Vol. 18, No. 11, 2025" was confirmed, from the paper itself.

---

## Q2. How the papers present formulation, overview figure, components, setup, results, ablation, cost, error analysis, case studies, limitations, and ethics

### Takeaway
Formal notation is light: usually one task definition (MAC-SQL's X=(Q,S,K), Alpha-SQL's D=(T,C,R) plus search tree, DAIL-SQL's argmax P_M(s*|σ(q,D))) and a few equations for scoring or selection. Experimental setup always lists datasets with sizes, EX (plus VES/R-VES on BIRD), baselines, exact model names, temperature and candidate counts. Ablations are leave-one-out tables with Δ. Error analyses sample failed BIRD dev cases and consistently find that a large share (about 10-30% or more) are gold-SQL errors.

### Cited Findings

**Problem formulation / notation**
- MAC-SQL defines the task as a triple X = (Q, S, K) (question, schema, optional external knowledge) that generates SQL Y, with token-level factorization (Eq. 1). It also gives Algorithm 1 for the agent loop with maxTryTimes — [MAC-SQL](https://arxiv.org/html/2312.11242)
- Alpha-SQL defines D = (T, C, R). The search tree is Ψ = (V, E): nodes are partial reasoning states and edges are actions. The reward R(y,q,D) is the self-consistency fraction of N sampled queries with matching execution result. Seven actions A1-A7 come with an ordering table — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- DAIL-SQL formalizes the task as maximizing P_M(s* | σ(q, D)), and the ICL version as P_M(s* | σ(q, D, Q′)) with |Q′| = k — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- CHASE-SQL formalizes selection: candidates C={c1..cn} are compared pairwise, and the final query is the one with the highest cumulative win count (Eq. 1, Algorithm 3) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL gives a keyword extraction K = f_Ms(Q, E), a column score formula, and candidate count p_l = p_s · p_m (2 schemas × 5 generators = 10) — [XiYan-SQL](https://arxiv.org/html/2507.04701)
- RSL-SQL defines schema-linking metrics NSR = Σ|S_gt ∩ S̃| / Σ|S_gt| and SRR (the fraction of questions where S̃ ⊇ S_gt). It frames net benefit as y − x (positive gain minus negative impact) — [RSL-SQL](https://arxiv.org/html/2411.00073)
- MCS-SQL defines a confidence score as the fraction of candidates with the same execution result, with threshold T=0.2 (Eqs. 1-3) — [MCS-SQL](https://arxiv.org/html/2405.07467)
- DIN-SQL, CHESS and OmniSQL give no formal task definition — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015); [CHESS](https://arxiv.org/html/2405.16755); [OmniSQL](https://arxiv.org/html/2503.02240)

**Method overview figure**
- CHASE-SQL's Figure 1 shows value retrieval, then multi-path generation, then a fixer loop, then a selection agent — [CHASE-SQL](https://arxiv.org/html/2410.01943). MAC-SQL's Figure 2 shows the Selector, Decomposer and Refiner — [MAC-SQL](https://arxiv.org/html/2312.11242). CHESS's Figure 2 shows four agents, each with named tools (`extract_keywords`, `retrieve_entity`, `filter_column`, `revise`, `generate_unit_test` …) — [CHESS](https://arxiv.org/html/2405.16755). XiYan's Figure 1 is titled "Overview of the proposed XiYan-SQL framework" — [XiYan-SQL](https://arxiv.org/html/2507.04701)

**Experimental setup conventions (exact values reported)**
- OmniSQL lists BIRD dev as 1,534 examples, and the metrics EX and TS. Closed-source baselines are given with version dates: GPT-4o-mini-2024-07-18, GPT-4o-2024-11-20, GPT-4-Turbo-2024-04-09. Greedy decoding uses temperature 0. Majority voting uses temperature 0.8 with 8 candidates grouped by execution result. Software is vLLM 0.6.3 — [OmniSQL](https://arxiv.org/html/2503.02240)
- **The OmniSQL GPT-4o-mini baseline on BIRD dev is 58.8 (greedy) and 61.5 (majority@8).** It is listed under "Closed-source LLMs (as a reference)" and described as "a point of reference rather than a direct comparison under controlled parameter size conditions." The authors excluded multi-stage frameworks: "single-step" evaluation only — [OmniSQL](https://arxiv.org/html/2503.02240)
- DIN-SQL: GPT-4 / CodeX via the OpenAI API, "greedy decoding with temperature set to zero," and max tokens of 350 (self-correction) and 600 (other modules) — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015)
- DAIL-SQL: temperature 0 "to eliminate the influence of randomness," with context limits of 4096 (OpenAI) and 2048 (open-source) and 200 tokens reserved for the response. Shots are 0/1/3/5 — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- MCS-SQL: GPT-4 8K via Azure, temperature 1.0, n=20 responses per call, p_t=3 / p_c=3 / p_q=5 prompts, k=20 few-shot examples, a 180 s execution timeout, and T=0.2 — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Alpha-SQL: N_rollout=24, N_expansion=3 at T=0.8, N_reward=5 at T=1.0, N_revision=10, and similarity thresholds 0.3/0.6. Embeddings use text-embedding-3-large, on 8×80GB GPUs — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- CHESS: in the high-budget setting, Gemini-1.5-pro generates 20 candidates with 10 unit tests. In the low-budget setting, 1 candidate gets up to 3 revisions. Embeddings use text-embedding-3-small with ChromaDB. CHESS also introduces a 147-example **Subsampled Development Set (SDS)** (81/54/12 simple/moderate/challenging) that Alpha-SQL and RSL-SQL reuse — [CHESS](https://arxiv.org/html/2405.16755); [Alpha-SQL](https://arxiv.org/html/2502.17248); [RSL-SQL](https://arxiv.org/html/2411.00073)
- CHASE-SQL: 7 candidates per generator (21 total), temperatures 0.5 vs 1.8 compared, and a fixer with up to β=3 attempts — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- XiYan-SQL: the schema filter uses gpt-4o-0806 (exact version string). Prior results are "taken from publications or leaderboards; some are reproduced under the same configuration" — [XiYan-SQL](https://arxiv.org/html/2507.04701)
- Omissions: MAC-SQL reports no temperature or decoding settings — [MAC-SQL](https://arxiv.org/html/2312.11242). RSL-SQL reports no model version or temperature — [RSL-SQL](https://arxiv.org/html/2411.00073)

**Main results tables**
- The standard BIRD table has Method, then (often) a backbone LLM, then Dev EX, then Test EX (and VES/R-VES). MAC-SQL and Alpha-SQL also break results down by difficulty (Simple / Moderate / Challenging / All) — [MAC-SQL](https://arxiv.org/html/2312.11242); [CHESS Table 6](https://arxiv.org/html/2405.16755)
- Alpha-SQL adds a "Zero-shot ✓/✗" column to separate fine-tuning-free methods (RSL-SQL GPT-4o 67.2 ✓, DAIL-SQL 55.9 ✓) from fine-tuned ones (CHASE-SQL 73.0 ✗, XiYan 73.3 ✗) — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- CHESS splits its tables by deployment budget (high vs limited computational budget) — [CHESS](https://arxiv.org/html/2405.16755)

**Ablation tables**
- Leave-one-out with Δ:
  - CHASE-SQL Table 7: full 73.01; self-consistency instead of the selector 68.84 (−4.17); w/o query fixer 69.23 (−3.78); w/o LSH 70.09 (−2.92) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
  - CHESS Table 4 on SDS: w/o revise −6.80; w/o select_tables −6.12 — [CHESS](https://arxiv.org/html/2405.16755)
  - XiYan Table III: w/o Schema Filter −1.24; only majority voting −3.13 — [XiYan-SQL](https://arxiv.org/html/2507.04701)
  - MAC-SQL: w/o Refiner 54.76 vs 59.39, broken down by difficulty — [MAC-SQL](https://arxiv.org/html/2312.11242)
- Incremental (add-one):
  - RSL-SQL Table IV: base prompt 48.70, then +few-shot 58.67, then … +MTSC 67.21 (GPT-4o) — [RSL-SQL](https://arxiv.org/html/2411.00073)
  - MCS-SQL: zero-shot 50.7, then +schema linking 52.8, then … +MCS 63.4 (BIRD dev) — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Selection-method ablations compare majority vote vs a learned or LLM selector. MCS-SQL: majority vote 62.8, MCS without filtering 62.5, MCS with filtering 63.4 — [MCS-SQL](https://arxiv.org/html/2405.07467)

**Cost / latency / token analysis**
- RSL-SQL Table V gives total input/output tokens and dollar cost for the full BIRD dev run: GPT-4o at 21.90M input + 0.73M output costs $62.06 for 67.21 EX, vs MAC-SQL $342.44, TA-SQL $351.55, E-SQL $182.56 — [RSL-SQL](https://arxiv.org/html/2411.00073)
- XiYan Table XII: about 40.81 s per sample, about 6,700 input and 205 output tokens, latency "only 60% of that of CHASE-SQL" — [XiYan-SQL](https://arxiv.org/html/2507.04701)
- CHESS reports "approximately 83% fewer LLM calls," 6 GPT-4-turbo calls vs "around 100 LLM calls" for MCS-SQL, and token efficiency "more than ×5" — [CHESS](https://arxiv.org/html/2405.16755)
- DIN-SQL (in its Limitations section): "approximately $0.5" per question and "approximately 60 seconds" latency with GPT-4 — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015)
- MAC-SQL: about 6M tokens (Spider dev) and about 10M tokens (BIRD dev) with GPT-4, with no dollar figures — [MAC-SQL](https://arxiv.org/html/2312.11242)
- DAIL-SQL has a "Token Efficiency" section (accuracy vs tokens, Fig. 7) and Appendix E (Financial Efficiency; Time-Consuming) — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- CHASE-SQL, MCS-SQL and Alpha-SQL report no cost or latency — [CHASE-SQL](https://arxiv.org/html/2410.01943); [MCS-SQL](https://arxiv.org/html/2405.07467); [Alpha-SQL](https://arxiv.org/html/2502.17248)

**Error analysis (categories with percentages)**
- CHASE-SQL Figure 5 (BIRD dev): correct 72.9%; correct candidate present but not selected 10.4%; no correct candidate 6.7%; **wrong golden query 10.0%** — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- MCS-SQL Appendix A sampled 100 failed examples per dev set. About 62% (BIRD) and 73% (Spider) of failures were attributed to incorrect gold or EX limitations. Among the rest, schema linking was the most common error (20% BIRD, 21% Spider) — [MCS-SQL](https://arxiv.org/html/2405.07467)
- MAC-SQL Figure 5: Gold Error 30% (BIRD) / 22% (Spider); Semantic Correct 14% / 22%; Schema Linking Error 2% / 8%. Note: the text contradicts its own numbers ("more frequent in BIRD (2%) than in Spider (8%)") — [MAC-SQL](https://arxiv.org/html/2312.11242)
- CHESS Appendix F has a three-level taxonomy: Incorrectly Predicted SQL (Column, Table, Entity, Revision, Malformed Date, Evidence, NULL/DISTINCT/GROUP BY, Operation, SELECT); Vague Question; Incorrect Golden SQL (Evidence, Description, Aggregation, Column, Filtering, …). For vanilla GPT-4, 57.1% of incorrect-SQL errors are schema-linking errors — [CHESS](https://arxiv.org/html/2405.16755)
- DIN-SQL categorizes 500 Spider training failures into six classes: schema linking, JOIN, GROUP BY, nesting and set operations, invalid SQL, and miscellaneous (percentages are in Fig. 1) — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015)
- An independent study found noisy questions and incorrect gold SQL are common in BIRD. On corrected gold queries, zero-shot baselines outperformed state-of-the-art prompting methods (Wretblad et al., ACL 2024 Short, pp. 356-369, doi:10.18653/v1/2024.acl-short.34, arXiv 2402.12243) — [ACL Anthology](https://aclanthology.org/2024.acl-short.34)

**Case studies**
- RSL-SQL has a top-level "VI Case Study" section with one positive-gain and one negative-impact example — [RSL-SQL](https://arxiv.org/html/2411.00073). XiYan's Fig. 5 shows a single BIRD dev case where the CTE variant succeeds — [XiYan-SQL](https://arxiv.org/html/2507.04701). CHESS Appendix E gives a schema selection example — [CHESS](https://arxiv.org/html/2405.16755)

**Limitations / ethics**
- DIN-SQL §7 Limitations covers manually built demonstrations and cost/latency — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015)
- MAC-SQL Limitations: prompts "may benefit from further optimization," and only a 7B model was fine-tuned. Its Ethics Statement says the datasets, models and code "are not associated with any ethical concerns" — [MAC-SQL](https://arxiv.org/html/2312.11242)
- CHESS "Conclusion and Limitations": BIRD-merged large schemas are synthetic, and a benchmark reflecting large-scale databases is needed — [CHESS](https://arxiv.org/html/2405.16755)
- Alpha-SQL Impact Statement (ICML boilerplate): "many potential societal consequences of our work, none of which we feel must be specifically highlighted here" — [Alpha-SQL](https://arxiv.org/html/2502.17248)
- DAIL-SQL puts its limitations in §5 Discussion: "we only test two rule implications," and Spider databases "may be not large enough" — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- OmniSQL has no Limitations section. It acknowledges SQLite-only experiments, single-step evaluation, and "silver-standard data" — [OmniSQL](https://arxiv.org/html/2503.02240)

### Inferences
- For a gpt-4o-mini, training-free thesis, the most persuasive setup paragraph copies OmniSQL's level of specificity: dated model snapshot (gpt-4o-mini-2024-07-18), temperature per stage, number of candidates per stage, execution timeout, and software versions.
- A cost table in RSL-SQL's format (input tokens, output tokens, USD, EX for the full BIRD dev run) is the accepted way to back an equal-budget claim.
- Reporting a "gold SQL wrong" percentage from manual inspection of a failure sample (as in CHASE-SQL, MCS-SQL, MAC-SQL and CHESS) is standard and expected on BIRD.

### Gaps
- Exact percentages from DIN-SQL Fig. 1 and CHESS Fig. 18 are in figures only and could not be extracted as text.
- OmniSQL does not describe the prompt used for its GPT-4o-mini baseline in the fetched portion. The remaining ~29K characters, likely the appendix, were not read.

---

## Q3. Statistical significance tests and run-to-run variance

### Takeaway
None of the ten papers report a significance test (McNemar, bootstrap, permutation), confidence intervals, standard deviations, or multiple seeds. All report single-run point estimates, often using temperature 0 as the implicit variance control. A thesis that reports a paired McNemar test plus bootstrap CIs would exceed the field's norm.

### Cited Findings
- OmniSQL: no seeds, repeated trials, standard deviations, CIs or significance tests. The 93.98% GPT-4o-judge preference rate has no interval — [OmniSQL](https://arxiv.org/html/2503.02240)
- DAIL-SQL: single-run point estimates, with temperature 0 used "to eliminate the influence of randomness" — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- DIN-SQL, MAC-SQL, CHESS, CHASE-SQL, RSL-SQL, MCS-SQL and Alpha-SQL: none reported — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015); [MAC-SQL](https://arxiv.org/html/2312.11242); [CHESS](https://arxiv.org/html/2405.16755); [CHASE-SQL](https://arxiv.org/html/2410.01943); [RSL-SQL](https://arxiv.org/html/2411.00073); [MCS-SQL](https://arxiv.org/html/2405.07467); [Alpha-SQL](https://arxiv.org/html/2502.17248)
- XiYan-SQL: Fig. 4(b) uses "multiple random samplings" of candidates but shows no variance statistics — [XiYan-SQL](https://arxiv.org/html/2507.04701)
- Small-sample caveat: Alpha-SQL and CHESS run ablations on the 147-example SDS (only 12 challenging questions), so one question is about 0.68 pp. Several reported ablation deltas are smaller than that granularity (e.g., Alpha-SQL w/o A3 −0.4) — [Alpha-SQL](https://arxiv.org/html/2502.17248); [CHESS](https://arxiv.org/html/2405.16755)
- RSL-SQL step-wise gains include +0.26 and +0.78 points with no noise estimate — [RSL-SQL](https://arxiv.org/html/2411.00073)

### Inferences
- On BIRD dev (n=1,534), 1 question is about 0.065 pp. A paired per-question test (exact McNemar on discordant pairs vs the baseline) and a paired bootstrap CI on the EX difference are the natural choices, because every system is scored on the same questions. This is my methodological recommendation, not a field convention found in these papers.
- Because OmniSQL's GPT-4o-mini numbers are single runs, a thesis that re-runs the baseline should report both the paper's number (58.8/61.5) and its own re-run, and say that the re-run absorbs API nondeterminism.

### Gaps
- I did not find a 2023-2026 LLM text-to-SQL paper among these ten that uses McNemar or bootstrap. I did not search more broadly (e.g., for benchmark/meta-evaluation papers) within the tool budget.

---

## Q4. Phrasing of improvement claims, equal-budget comparisons, contamination/noise caveats

### Takeaway
Claims are typically "achieves a new state-of-the-art X% on BIRD … outperforming … by Y%," with absolute percentage points written as "%." Fair-comparison caveats appear as category qualifiers ("among open-source," "zero-shot," "without fine-tuning," "as a reference") or budget splits (CHESS high vs limited budget). Contamination is discussed explicitly only by OmniSQL. BIRD gold-label noise is acknowledged through error-analysis percentages.

### Cited Findings
- SOTA claims:
  - "outperforming all previous works and setting a new state-of-the-art performance"; "outperforms all of the published and undisclosed methods … by a large margin" — [CHASE-SQL](https://arxiv.org/html/2410.01943)
  - "achieves a new SOTA performance of 75.63% on the notable BIRD benchmark"; "outperforming the second-place entry by 0.84%" — [XiYan-SQL](https://arxiv.org/html/2507.04701)
  - "establishing a new state-of-the-art (SOTA) in its holdout test set" — [MAC-SQL](https://arxiv.org/html/2312.11242)
  - "refreshes the Spider leaderboard with 86.6% execution accuracy and sets a new bar" — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- Relative-gain claims:
  - "consistently improves their simple few-shot performance by roughly 10%"; "beats many heavily fine-tuned models by at least 5%" — [DIN-SQL](https://ar5iv.labs.arxiv.org/html/2304.11015)
  - "significantly outperform[s] previous ICL-based methods" — [MCS-SQL](https://arxiv.org/html/2405.07467)
- Qualified or category claims:
  - "Among the methods using open-source models … achieves state-of-the-art"; "within 2% of the leading proprietary method"; "approximately 83% fewer LLM calls" — [CHESS](https://arxiv.org/html/2405.16755)
  - "SOTA execution accuracy among open-source solutions" — [RSL-SQL](https://arxiv.org/html/2411.00073)
  - Alpha-SQL: "using a 32B open-source LLM without fine-tuning," "a fine-tuning-free, plug-and-play Text-to-SQL framework," "outperforming the best previous zero-shot approach based on GPT-4o by 2.5%" — [Alpha-SQL](https://arxiv.org/html/2502.17248); [PMLR](https://proceedings.mlr.press/v267/li25dt.html)
  - OmniSQL: "matching or surpassing leading closed-source and open-source LLMs"; closed models are "a point of reference rather than a direct comparison" — [OmniSQL](https://arxiv.org/html/2503.02240)
- Budget-aware framing:
  - CHESS organizes §4.2 by "High Computational Budget" vs "Limited Computational Budget" and states "methods solely relying on scaling sampling at inference time become less effective" — [CHESS](https://arxiv.org/html/2405.16755)
  - OmniSQL contrasts greedy decoding with majority@8 at the same temperature for every model — [OmniSQL](https://arxiv.org/html/2503.02240)
  - CHASE-SQL compares self-consistency vs its selector on the same candidate pool (−4.17) — [CHASE-SQL](https://arxiv.org/html/2410.01943)
- Contamination: OmniSQL notes some open models "incorporated the training sets of popular text-to-SQL benchmarks," and calls ScienceBenchmark/EHRSQL zero-shot because no training data from them is used — [OmniSQL](https://arxiv.org/html/2503.02240). DAIL-SQL does not discuss contamination — [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)
- Noise caveats: CHASE-SQL attributes 10.0% of BIRD dev to wrong golden queries — [CHASE-SQL](https://arxiv.org/html/2410.01943). MCS-SQL attributes about 62% of BIRD failures to incorrect gold or EX limitations — [MCS-SQL](https://arxiv.org/html/2405.07467). Wretblad et al. examine BIRD noise directly — [ACL Anthology](https://aclanthology.org/2024.acl-short.34)
- Internal inconsistencies are common and get noticed by reviewers. MCS-SQL gives two different SOTA gaps (+5.86 vs 4.74). RSL-SQL reports 87.5 in a table vs 87.7 in the text. DAIL-SQL reports 82.4 vs 83.5 — [MCS-SQL](https://arxiv.org/html/2405.07467); [RSL-SQL](https://arxiv.org/html/2411.00073); [DAIL-SQL](https://ar5iv.labs.arxiv.org/html/2308.15363)

### Inferences
- Recommended phrasing pattern for this thesis (modeled on Alpha-SQL and CHESS qualifiers): "Under the same backbone (gpt-4o-mini-2024-07-18) and without any fine-tuning, our system reaches X% EX on BIRD dev, +Δ pp over the GPT-4o-mini greedy baseline reported by OmniSQL (58.8%) and +Δ′ pp over its majority@8 (61.5%)." State the candidate count and token/$ cost next to the number, so the equal-budget question is answered in place.
- Avoid "state-of-the-art" without a category qualifier. CHASE-SQL and XiYan (73-75%) are fine-tuned or use larger models, so the fair category is "training-free with gpt-4o-mini."
- Cross-check every number between tables and text before submission, given how often the reference papers contradict themselves.

### Gaps
- No paper among the ten makes a strictly token-matched equal-budget comparison against majority voting. The closest are CHESS's budget tiers and RSL-SQL's cost table.

---

## Q5. Standard structure of a Vietnamese CS KLTN, with university examples

### Takeaway
Vietnamese faculty guidelines agree on: cover and sub-cover, Lời cam đoan (signed), Lời cảm ơn, Mục lục, abbreviation/figure/table lists, Tóm tắt, then the body (Mở đầu, then chapters, then Kết luận with hướng phát triển), then Tài liệu tham khảo, then Phụ lục. Exact ordering, page minimums (35-50+), fonts (Times New Roman 13pt) and margins differ by school. The typical 4-5 chapter body is: Tổng quan, then Cơ sở lý thuyết, then Phương pháp/Thiết kế, then Kết quả/Thực nghiệm, then Kết luận.

### Cited Findings

**ĐHQG HN - Trường ĐH Công nghệ (UET), "QUY ĐỊNH VỀ TRÌNH BÀY KHÓA LUẬN TỐT NGHIỆP (Dành cho sinh viên chương trình đào tạo chuẩn và chất lượng cao)"** — [UET PDF](https://uet.edu.vn/wp-content/uploads/2017/07/Quy-%C4%91i%CC%A3nh-v%C3%AA%CC%80-tri%CC%80nh-ba%CC%80y-kho%CC%81a-lu%C3%A2%CC%A3n-t%C3%B4%CC%81t-nghi%C3%AA%CC%A3pCLC.pdf)
- Order:
  1. Trang bìa
  2. Trang phụ bìa (Tiếng Việt), plus an English sub-cover for CLC students
  3. Trang tóm tắt nội dung (Tiếng Việt), plus an English abstract for CLC: "TÓM TẮT" in about 360 words at 12pt, with "Từ khóa" of at most 4 key phrases
  4. "Lời cam đoan" (5-10 lines, signed)
  5. Mục lục
  6. "Bảng các ký hiệu, chữ viết tắt" in Vietnamese alphabetical order
  7. Body: **Mở đầu** (must state "tính cần thiết của đề tài, ý nghĩa khoa học và thực tiễn …, đối tượng và phương pháp nghiên cứu, nội dung nghiên cứu"), then "các chương," then **Kết luận** ("những kết quả chính và đánh giá kết quả đạt được")
  8. Phụ lục
  9. Tài liệu tham khảo
- Numbering: Arabic numerals only (Chương 1, 1.1, 1.1.1). Figures and tables are numbered per chapter (Hình 1.1). Table captions go **above** the table. Figure captions go **below** the figure.
- Length: at least about 35-50 pages (the PDF text reads "3550," which is probably "35-50"). This excludes tables, figures, references and appendices.
- Formatting: 13pt Unicode font, 1.3 line spacing, margins top 2.5 / bottom 3 / left 3 / right 2 cm, 6pt between paragraphs, 1 cm first-line indent. "Latex" is explicitly allowed.
- References: grouped by language (Tiếng Việt, Tiếng Anh …), sorted **ABC by author surname** (Vietnamese authors by given name, without inverting), and numbered in square brackets. In-text citations use [n]. Article titles go in quotation marks and journal/proceedings names in italics. Page ranges use "tr." for Vietnamese sources and "pp." for English ones. Example: `[4] M.W. Allister and S.A. Long, "Resonant hemispherical dielectric antenna", Electronics Letters, Vol. 20, 2008, pp. 657-659.`

**ĐHQG TP.HCM - Trường ĐH Khoa học Tự nhiên (HCMUS), Khoa CNTT, "MỘT SỐ QUI ĐỊNH VỀ HÌNH THỨC TRÌNH BÀY KHÓA LUẬN TỐT NGHIỆP"** (PDF created 2017) — [HCMUS PDF](https://www.ctda.hcmus.edu.vn/wp-content/uploads/2015/12/CLC_Mau-quy-dinh-trinh-bay-KLTN.pdf)
- Cấu trúc: Bìa, Trang phụ bìa, Lời cám ơn, **Đề cương chi tiết có chữ kí của giáo viên hướng dẫn**, Mục lục, Bảng các hình vẽ, ký hiệu, chữ viết tắt, then Tóm tắt, then Nội dung.
- Bố cục (exact headings): **MỞ ĐẦU** (lí do chọn đề tài, mục đích, đối tượng, phạm vi), then **TỔNG QUAN** ("Phân tích đánh giá các hướng nghiên cứu đã có của các tác giả trong và ngoài nước … nêu những vấn đề còn tồn tại"), then **NGHIÊN CỨU THỰC NGHIỆM HOẶC LÍ THUYẾT** (cơ sở lí thuyết, giả thiết khoa học, phương pháp nghiên cứu), then **TRÌNH BÀY, ĐÁNH GIÁ BÀN LUẬN VỀ CÁC KẾT QUẢ**, then **KẾT LUẬN** ("ngắn gọn, không có lời bàn và bình luận thêm"), then **HƯỚNG PHÁT TRIỂN**, then **DANH MỤC TÀI LIỆU THAM KHẢO**, then **PHỤ LỤC**.
- Length: at least 50 and at most about 100 A4 pages, excluding the front matter and references.
- Formatting: Times New Roman 13 or 14pt, 1.5 line spacing, margins top 3 / bottom 3.5 / left 3.5 / right 2 cm.
- References (custom, not strictly IEEE): "Tên tác giả, tên bài báo, tên tạp chí, tập, số, năm và các trang." Conference entries: authors, title, conference name, proceedings, place and date.

**Trường ĐH Kinh tế Quốc dân (NEU), Khoa CNTT, "MỘT SỐ QUY ĐỊNH LÀM BÁO CÁO KHÓA LUẬN TỐT NGHIỆP"** — [NEU FIT](https://fit.neu.edu.vn/post/mot-so-quy-dinh-viet-bao-cao-khoa-luan)
- Front matter: Trang bìa, Mục lục, "Lời cam đoan," Lời cảm ơn (optional), "Danh mục từ viết tắt," and Danh mục bảng/biểu đồ/hình/công thức.
- Body (at least 50 pages): "Mở đầu" (1-2 pages), then "Chương 1. Tổng quan về đề tài" (5-10), then "Chương 2. Cơ sở lý thuyết" (10-15), then "Chương 3: Phương pháp nghiên cứu/Phân tích thiết kế hệ thống" (15-20), then "Chương 4: Kết quả và thảo luận" (10-15), then "Kết luận" (1-2).
- Back matter: "Tài liệu tham khảo," "Phụ lục" (must not be longer than the main body), and a **Turnitin result**.
- Formatting: Times New Roman 13, 1.3 spacing, left margin 3.5 cm, chapter titles 18pt bold uppercase, at most 4 levels of numbering, table captions above and figure captions below, equations numbered (3.2) and right-aligned, and every figure and table must be referenced in the text.
- **Citation standard: IEEE** for both in-text citations and the reference list.

**ĐHQG TP.HCM - Trường ĐH Công nghệ Thông tin (UIT)**: community LaTeX template "hcmuit-thesistemplate" on Overleaf (not an official regulation) — [Overleaf PDF](https://www.overleaf.com/latex/templates/hcmuit-thesistemplate/ghqpckjqdxfz.pdf)
- Front matter (Roman page numbers): Thông tin hội đồng chấm khóa luận tốt nghiệp, Lời cảm ơn, Mục lục, Danh sách hình vẽ, Danh sách bảng, Danh sách đoạn mã, Danh sách các từ viết tắt. Then "Tóm tắt khóa luận" (Arabic page 1, ending with a "Phần còn lại … có cấu trúc như sau" chapter roadmap). Then the chapters ("Chương 1 Giới thiệu" …), then Phụ lục A, then "Tài liệu tham khảo" (numbered [1]). The cover is bilingual (Vietnamese and English title).

**Other examples found:** [HCMUTE "Final Huong dan trinh bay khoa luan tot nghiep 2019"](https://fas.hcmute.edu.vn/Resources/Docs/SubDomain/fas/Thong%20bao/Final_Huong%20dan%20trinh%20bay%20khoa%20luan%20tot%20nghiep%202019.pdf) lists danh mục biểu đồ/hình ảnh and nhiệm vụ khóa luận as required appendices. I saw this only as a search snippet and did not read the PDF.

### Inferences
- Proposed KLTN skeleton that satisfies the UET, HCMUS and NEU rules and mirrors the papers above:
  - **Front matter:** Bìa, Phụ bìa, Lời cam đoan, Lời cảm ơn, Tóm tắt (+ Abstract), Mục lục, Danh mục hình, Danh mục bảng, Danh mục từ viết tắt.
  - **Chương 1 Giới thiệu/Tổng quan:** bối cảnh text-to-SQL, BIRD, động lực; mục tiêu, phạm vi (training-free, gpt-4o-mini, BIRD dev); câu hỏi nghiên cứu; đóng góp; bố cục. This corresponds to a paper's Introduction.
  - **Chương 2 Cơ sở lý thuyết và các nghiên cứu liên quan:** định nghĩa bài toán and notation (as in MAC-SQL §2.1 and Alpha-SQL §3.1), LLM/ICL/CoT/self-consistency, agent; the BIRD/Spider datasets and EX/VES metrics; prior methods grouped as in Q1 (DIN, DAIL, MAC, CHESS, CHASE, MCS, RSL, XiYan, Alpha, OmniSQL).
  - **Chương 3 Phương pháp đề xuất:** tổng quan (Hình 3.1 pipeline), then one subsection per module, then the algorithm/pseudocode, then a complexity/cost discussion.
  - **Chương 4 Thực nghiệm và đánh giá:**
    - 4.1 Thiết lập (dữ liệu, độ đo, baseline OmniSQL GPT-4o-mini 58.8/61.5, cài đặt: model snapshot, temperature, số mẫu, timeout)
    - 4.2 Kết quả chính
    - 4.3 Kiểm định thống kê
    - 4.4 Ablation
    - 4.5 Chi phí/độ trễ/token
    - 4.6 Phân tích lỗi (gold sai %, schema linking % …)
    - 4.7 Case study
    - 4.8 Thảo luận và hạn chế
  - **Chương 5 Kết luận và hướng phát triển.**
  - **Back matter:** Tài liệu tham khảo, Phụ lục (prompts, extra tables) — prompts go in the appendix as all ten papers do.
- Put a dedicated "Hạn chế" subsection in Chương 4 or 5. Vietnamese guidelines do not require one, but ACL-style papers do, and it is where BIRD gold-noise and single-model caveats belong.

### Gaps
- I did not find an official HUST (ĐHBK HN, SoICT) KLTN/ĐATN guideline within budget, nor an official UIT regulation (only the community template).
- The UET page-count string "3550" is ambiguous from text extraction. Reading it as 35-50 is my interpretation.
- The UET and HCMUS documents date from about 2017. Faculties may have newer versions.

---

## Q6. Citation styles in text-to-SQL venues, with correctly formatted examples

### Takeaway
ACL/COLING (MAC-SQL, MCS-SQL, Wretblad) use ACL Anthology author-year style. PVLDB (DAIL-SQL, OmniSQL) uses the ACM numeric reference format. NeurIPS/ICLR/ICML use author-year natbib styles. RSL-SQL and XiYan use IEEE-style templates (Roman-numeral sections). For a Vietnamese KLTN, IEEE numeric is the safest default: NEU mandates it, and UET's numbered [n] system is IEEE-like but sorted alphabetically and grouped by language.

### Cited Findings
- The ACL Anthology record for MAC-SQL gives citekey wang-etal-2025-mac, Proceedings of COLING 2025, pp. 540-557, Abu Dhabi — [ACL Anthology](https://aclanthology.org/2025.coling-main.36). MCS-SQL: Proceedings of the 31st International Conference on Computational Linguistics, pp. 337-353 — [ACL Anthology](https://aclanthology.org/2025.coling-main.24); [BibTeX](https://aclanthology.org/2025.coling-main.24.bib)
- DAIL-SQL: PVLDB 17(5): 1132-1145, 2024, doi:10.14778/3641204.3641221 — [VLDB](https://www.vldb.org/pvldb/vol17/p1132-gao.pdf). OmniSQL carries a "PVLDB Reference Format" header for Vol. 18, No. 11 — [OmniSQL](https://arxiv.org/html/2503.02240)
- Alpha-SQL: PMLR 267: 36810-36830 — [PMLR](https://proceedings.mlr.press/v267/li25dt.html). CHASE-SQL: ICLR 2025 proceedings — [ICLR](https://proceedings.iclr.cc/paper_files/paper/2025/hash/974ff7b5bf08dbf9400b5d599a39c77f-Abstract-Conference.html). DIN-SQL: NeurIPS 2023 — [NeurIPS](https://papers.neurips.cc/paper_files/paper/2023/file/72223cc66f63ca1aa59edaec1b3670e6-Paper-Conference.pdf)
- RSL-SQL and XiYan-SQL use I/II/III and III-A section numbering, which is characteristic of IEEE templates — [RSL-SQL](https://arxiv.org/html/2411.00073); [XiYan-SQL](https://arxiv.org/html/2507.04701)
- NEU requires IEEE — [NEU FIT](https://fit.neu.edu.vn/post/mot-so-quy-dinh-viet-bao-cao-khoa-luan). UET requires [n] numbering, alphabetical order, and grouping by language — [UET PDF](https://uet.edu.vn/wp-content/uploads/2017/07/Quy-%C4%91i%CC%A3nh-v%C3%AA%CC%80-tri%CC%80nh-ba%CC%80y-kho%CC%81a-lu%C3%A2%CC%A3n-t%C3%B4%CC%81t-nghi%C3%AA%CC%A3pCLC.pdf)

### Example entries (built only from metadata verified above)

**ACL style (author-year):**
- Bing Wang, Changyu Ren, Jian Yang, Xinnian Liang, Jiaqi Bai, LinZheng Chai, Zhao Yan, Qian-Wen Zhang, Di Yin, Xing Sun, and Zhoujun Li. 2025. MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL. In *Proceedings of the 31st International Conference on Computational Linguistics*, pages 540–557, Abu Dhabi, UAE. Association for Computational Linguistics.
- Dongjun Lee, Choongwon Park, Jaehyuk Kim, and Heesoo Park. 2025. MCS-SQL: Leveraging Multiple Prompts and Multiple-Choice Selection For Text-to-SQL Generation. In *Proceedings of the 31st International Conference on Computational Linguistics*, pages 337–353, Abu Dhabi, UAE. Association for Computational Linguistics.

**ACM / PVLDB style:**
- Dawei Gao, Haibin Wang, Yaliang Li, Xiuyu Sun, Yichen Qian, Bolin Ding, and Jingren Zhou. 2024. Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation. *PVLDB* 17, 5 (2024), 1132–1145. https://doi.org/10.14778/3641204.3641221

**IEEE style (recommended for the KLTN):**
- [1] M. Pourreza and D. Rafiei, "DIN-SQL: Decomposed in-context learning of text-to-SQL with self-correction," in *Advances in Neural Information Processing Systems 36 (NeurIPS 2023)*, 2023. [Online]. Available: arXiv:2304.11015
- [2] D. Gao, H. Wang, Y. Li, X. Sun, Y. Qian, B. Ding, and J. Zhou, "Text-to-SQL empowered by large language models: A benchmark evaluation," *Proc. VLDB Endow.*, vol. 17, no. 5, pp. 1132–1145, 2024, doi: 10.14778/3641204.3641221.
- [3] B. Li, J. Zhang, J. Fan, Y. Xu, C. Chen, N. Tang, and Y. Luo, "Alpha-SQL: Zero-shot text-to-SQL using Monte Carlo tree search," in *Proc. 42nd Int. Conf. Mach. Learn. (ICML)*, PMLR, vol. 267, 2025, pp. 36810–36830.
- [4] M. Pourreza, H. Li, R. Sun, Y. Chung, S. Talaei, G. T. Kakkar, Y. Gan, A. Saberi, F. Özcan, and S. Ö. Arık, "CHASE-SQL: Multi-path reasoning and preference optimized candidate selection in text-to-SQL," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2025.
- [5] H. Li, S. Wu, X. Zhang, X. Huang, J. Zhang, F. Jiang, S. Wang, T. Zhang, J. Chen, R. Shi, H. Chen, and C. Li, "OmniSQL: Synthesizing high-quality text-to-SQL data at scale," *Proc. VLDB Endow.*, vol. 18, no. 11, 2025, arXiv:2503.02240.
- [6] S. Talaei, M. Pourreza, Y.-C. Chang, A. Mirhoseini, and A. Saberi, "CHESS: Contextual harnessing for efficient SQL synthesis," arXiv preprint arXiv:2405.16755, 2024.
- [7] Z. Cao, Y. Zheng, Z. Fan, X. Zhang, W. Chen, and X. Bai, "RSL-SQL: Robust schema linking in text-to-SQL generation," arXiv preprint arXiv:2411.00073, 2024.
- [8] Y. Liu, Y. Zhu, Y. Gao, Z. Luo, X. Li, X. Shi, Y. Hong, J. Gao, Y. Li, B. Ding, and J. Zhou, "XiYan-SQL: A novel multi-generator framework for text-to-SQL," arXiv preprint arXiv:2507.04701, 2025.
- [9] N. Wretblad *et al.*, "Understanding the effects of noise in text-to-SQL: An examination of the BIRD-Bench benchmark," in *Proc. 62nd Annu. Meeting Assoc. Comput. Linguistics (Vol. 2: Short Papers)*, 2024, pp. 356–369, doi: 10.18653/v1/2024.acl-short.34.

### Inferences
- Use BibTeX from the ACL Anthology, PMLR, and the DBLP/VLDB pages, and render it with an IEEE .bst (`IEEEtran`) to satisfy NEU-style rules. If the faculty follows the UET rules, switch to alphabetical ordering and Vietnamese/English grouping.
- Cite the peer-reviewed version (venue) when one exists, and the arXiv ID otherwise. CHESS, RSL-SQL and XiYan-SQL 2507.04701 should be cited as arXiv preprints, because no venue was confirmed.

### Gaps
- Page numbers and DOI for OmniSQL (PVLDB 18(11)) and DIN-SQL (NeurIPS 36) were not verified, so they are omitted from the examples.
- The full author list for Wretblad et al. was not retrieved, hence the "et al." in [9].
- The ICML 2025 proceedings numbering ("42nd") follows the standard ICML sequence but was not read directly from the PMLR page.
