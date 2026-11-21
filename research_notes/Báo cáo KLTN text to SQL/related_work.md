# Related work / Các nghiên cứu liên quan: text-to-SQL taxonomy, BIRD dev EX and positioning of a training-free gpt-4o-mini pipeline

Conventions used in these notes:
- "Dev" = BIRD dev (1,534 questions, with oracle evidence unless stated), "Test" = BIRD hidden test. Every number is execution accuracy (EX, %) with its backbone.
- "LB" = number taken from the official BIRD leaderboard (bird-bench.github.io), fetched 2026-11-21. "Paper" = number from the paper's own abstract/table.
- Items marked **[unverified]** are from prior knowledge and were NOT confirmed against a primary source in this session; the report writer should either verify or drop them.

## 1. Surveys to cite (verified venues)

### Takeaway
Four surveys cover the field: Hong et al. (IEEE TKDE 2025), Liu et al. (IEEE TKDE 2025), Shi et al. (ACM Computing Surveys), and Katsogiannis-Meimarakis & Koutrika (VLDB Journal 2023, pre-LLM deep learning). All venues were confirmed from arXiv comment fields / the publisher page.

### Cited Findings
- Zijin Hong, Zheng Yuan, Qinggang Zhang, Hao Chen, et al. "Next-Generation Database Interfaces: A Survey of LLM-based Text-to-SQL." arXiv:2406.08426 (v1 2024-06-12); arXiv comment: "Accepted to IEEE TKDE2025". — [arXiv 2406.08426](https://arxiv.org/abs/2406.08426)
- Xinyu Liu, Shuyu Shen, Boyan Li, Peixian Ma, et al. "A Survey of Text-to-SQL in the Era of LLMs: Where are we, and where are we going?" arXiv:2408.05109 (v1 2024-08-09); journal_ref: "TKDE July 2025". Note the current title says "Text-to-SQL in the Era of LLMs" (the user's working title "A Survey of NL2SQL with Large Language Models" was the v1 title **[unverified]**; cite the current title). — [arXiv 2408.05109](https://arxiv.org/abs/2408.05109)
- Liang Shi, Zhengju Tang, Nan Zhang, Xiaotong Zhang, Zhi Yang. "A Survey on Employing Large Language Models for Text-to-SQL Tasks." arXiv:2407.15186 (v1 2024-07-21); comment: "Accepted by ACM Computing Surveys (CSUR)". — [arXiv 2407.15186](https://arxiv.org/abs/2407.15186)
- George Katsogiannis-Meimarakis, Georgia Koutrika. "A survey on deep learning approaches for text-to-SQL." The VLDB Journal 32, 905–936 (2023). DOI 10.1007/s00778-022-00776-8. Focuses on deep-learning (pre-LLM) systems; proposes a fine-grained taxonomy and reviews benchmarks/evaluation. — [Springer](https://link.springer.com/article/10.1007/s00778-022-00776-8)
- Additional (optional) older surveys surfaced: "A Survey on Text-to-SQL Parsing: Concepts, Methods, and Future Directions" (arXiv:2208.13629) and "Recent Advances in Text-to-SQL: A Survey of What We Have and What We Expect" (arXiv:2208.10099, COLING 2022 **[unverified venue]**). — [arXiv 2208.13629](https://arxiv.org/pdf/2208.13629); [arXiv 2208.10099](https://arxiv.org/pdf/2208.10099)
- Benchmarks to cite with the surveys: BIRD — Jinyang Li, Binyuan Hui, Ge Qu, Jiaxi Yang, et al. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs." arXiv:2305.03111, NeurIPS 2023 (arXiv comment "NeurIPS 2023"); human performance 92.96 test EX. — [arXiv 2305.03111](https://arxiv.org/abs/2305.03111); [BIRD LB](https://bird-bench.github.io/). Spider (Yu et al., EMNLP 2018, arXiv:1809.08887) **[unverified this session]**.

### Inferences
- The two TKDE 2025 surveys (Hong; Liu) are the best primary "LLM era" citations; Katsogiannis-Meimarakis & Koutrika covers the PLM/seq2seq era; Shi et al. (CSUR) covers prompting vs fine-tuning taxonomy.

### Gaps
- Volume/issue/page numbers for the two TKDE surveys and the Shi CSUR paper were not retrieved (only "accepted" comments). Check IEEE Xplore / ACM DL before final bibliography.

## 2. Taxonomy and representative work with BIRD dev EX and backbone

### Takeaway
BIRD dev EX rose from ~23% (T5-3B, 2023) to ~46% (GPT-4 zero-shot), ~55–60% (DIN/DAIL/MAC/TA-SQL prompting with GPT-4), ~63–69% (multi-candidate + selection with GPT-4/4o: MCS-SQL, CHESS, OpenSearch-SQL, RSL-SQL, Distillery), ~73–75% (CHASE-SQL+Gemini, XiYan-SQL ensembles), and ~66–72% for fine-tuned/RL open 7–32B models (OmniSQL, SQL-R1, Reasoning-SQL, Arctic-Text2SQL-R1). With gpt-4o-mini specifically, the published reference points are 58.8/61.5 (OmniSQL baseline Gre/Maj@8), 61.60 (E-SQL) and 63.15 (MCTS-SQL).

### Cited Findings

#### (a) Pre-LLM seq2seq / PLM era (mostly evaluated on Spider; few BIRD numbers)
- IRNet — Jiaqi Guo, Zecheng Zhan, Yan Gao, Yan Xiao, et al. "Towards Complex Text-to-SQL in Cross-Domain Database with Intermediate Representation." arXiv:1905.08205, ACL 2019 ("To appear in ACL 2019"). No BIRD number. — [arXiv 1905.08205](https://arxiv.org/abs/1905.08205)
- RAT-SQL — Bailin Wang, Richard Shin, Xiaodong Liu, Oleksandr Polozov, Matthew Richardson. "RAT-SQL: Relation-Aware Schema Encoding and Linking for Text-to-SQL Parsers." arXiv:1911.04942, ACL 2020. No BIRD number. — [arXiv 1911.04942](https://arxiv.org/abs/1911.04942)
- PICARD — Torsten Scholak, Nathan Schucher, Dzmitry Bahdanau. "PICARD: Parsing Incrementally for Constrained Auto-Regressive Decoding from Language Models." arXiv:2109.05093, EMNLP 2021. No BIRD number. — [arXiv 2109.05093](https://arxiv.org/abs/2109.05093)
- RESDSQL — Haoyang Li, Jing Zhang, Cuiping Li, Hong Chen. "RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL." arXiv:2302.05965, AAAI 2023 (oral). Not listed on the BIRD overall LB. — [arXiv 2302.05965](https://arxiv.org/abs/2302.05965)
- Graphix-T5 — Jinyang Li, Binyuan Hui, Reynold Cheng, Bowen Qin, et al. "Graphix-T5: Mixing Pre-Trained Transformers with Graph-Aware Layers for Text-to-SQL Parsing." arXiv:2301.07507, AAAI 2023 (oral). Not listed on the BIRD overall LB. — [arXiv 2301.07507](https://arxiv.org/abs/2301.07507)
- PLM baselines on BIRD (LB, oracle knowledge): T5-Base 11.54 dev / 12.89 test; T5-Large 19.75 / 20.94; T5-3B 23.34 / 24.05. Without oracle knowledge T5-3B: 10.37 / 11.17. — [BIRD LB](https://bird-bench.github.io/)
- Early LLM baselines (LB, oracle knowledge): Codex 34.35 dev / 36.47 test; ChatGPT 37.22 / 39.30; ChatGPT+CoT 36.64 / 40.08; PaLM-2 27.38 / 33.04; Claude-2 42.70 / 49.02; GPT-4 46.35 / 54.89. — [BIRD LB](https://bird-bench.github.io/)

#### (b) Prompting / in-context learning with closed models
- DIN-SQL — Mohammadreza Pourreza, Davood Rafiei. "DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction." arXiv:2304.11015, NeurIPS 2023. LB: DIN-SQL + GPT-4 50.72 dev / 55.90 test. — [arXiv 2304.11015](https://arxiv.org/abs/2304.11015); [BIRD LB](https://bird-bench.github.io/)
- DAIL-SQL — Dawei Gao, Haibin Wang, Yaliang Li, Xiuyu Sun, et al. "Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation." arXiv:2308.15363; PVLDB 17(5), 2024 **[venue unverified this session]**. LB: DAIL-SQL + GPT-4 54.76 dev / 57.41 test. OmniSQL notes DAIL-SQL+GPT-4+self-consistency reaches 86.6 on Spider test. — [arXiv 2308.15363](https://arxiv.org/abs/2308.15363); [BIRD LB](https://bird-bench.github.io/); [OmniSQL](https://arxiv.org/html/2503.02240)
- C3 — Xuemei Dong, Chao Zhang, Yuhang Ge, Yuren Mao, et al. "C3: Zero-shot Text-to-SQL with ChatGPT." arXiv:2307.07306 (2023; no venue in arXiv metadata). Spider-only; no BIRD number on LB. — [arXiv 2307.07306](https://arxiv.org/abs/2307.07306)
- ACT-SQL — Hanchong Zhang, Ruisheng Cao, Lu Chen, Hongshen Xu, Kai Yu. "ACT-SQL: In-Context Learning for Text-to-SQL with Automatically-Generated Chain-of-Thought." arXiv:2310.17342; Findings of EMNLP 2023 **[venue unverified]**. No BIRD number on LB. — [arXiv 2310.17342](https://arxiv.org/abs/2310.17342)
- MAC-SQL — Bing Wang, Changyu Ren, Jian Yang, Xinnian Liang, et al. "MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL." arXiv:2312.11242, COLING 2025 (Oral). LB: MAC-SQL + GPT-4 57.56 dev / 59.59 test. — [arXiv 2312.11242](https://arxiv.org/abs/2312.11242); [BIRD LB](https://bird-bench.github.io/)
- TA-SQL — Ge Qu, Jinyang Li, Bowen Li, Bowen Qin, et al. "Before Generation, Align it! A Novel and Effective Strategy for Mitigating Hallucinations in Text-to-SQL Generation." arXiv:2405.15307, Findings of ACL 2024. Abstract: 21.23% relative gain over GPT-4 baseline on BIRD dev. LB: TA-SQL + GPT-4 56.19 dev / 59.14 test. — [arXiv 2405.15307](https://arxiv.org/abs/2405.15307); [BIRD LB](https://bird-bench.github.io/)
- PURPLE — Tonghui Ren, Yuankai Fan, Zhenying He, Ren Huang, et al. "PURPLE: Making a Large Language Model a Better SQL Writer." arXiv:2403.20014, ICDE 2024. LB: PURPLE + GPT-4o 62.97 dev / 64.51 test; PURPLE + RED + GPT-4o 68.12 / 70.21. — [arXiv 2403.20014](https://arxiv.org/abs/2403.20014); [BIRD LB](https://bird-bench.github.io/)
- SuperSQL — Boyan Li, Yuyu Luo, Chengliang Chai, Guoliang Li, Nan Tang. "The Dawn of Natural Language to SQL: Are We Fully Ready?" arXiv:2406.01265, PVLDB (VLDB 2024), DOI 10.14778/3681954.3682003. LB: SuperSQL 58.50 dev / 62.66 test (backbone GPT-4 family **[unverified]**). — [arXiv 2406.01265](https://arxiv.org/abs/2406.01265); [BIRD LB](https://bird-bench.github.io/)

#### (c) Multi-candidate generation + selection / agentic pipelines
- MCS-SQL — Dongjun Lee, Choongwon Park, Jaehyuk Kim, Heesoo Park. "MCS-SQL: Leveraging Multiple Prompts and Multiple-Choice Selection For Text-to-SQL Generation." arXiv:2405.07467; COLING 2025 **[venue unverified]**. Abstract: 65.5% on BIRD (test). LB: MCS-SQL + GPT-4 63.36 dev / 65.45 test. — [arXiv 2405.07467](https://arxiv.org/abs/2405.07467); [BIRD LB](https://bird-bench.github.io/)
- CHESS — Shayan Talaei, Mohammadreza Pourreza, Yu-Chen Chang, Azalia Mirhoseini, Amin Saberi. "CHESS: Contextual Harnessing for Efficient SQL Synthesis." arXiv:2405.16755 (2024). Components: entity/value retrieval (IR), schema selection (SS), candidate generation (CG), unit tests (UT). LB: CHESS(IR+CG+UT) 68.31 dev / 71.10 test; CHESS(IR+SS+CG) 65.00 / 66.69 (backbones a mix of proprietary + fine-tuned models **[unverified detail]**). — [arXiv 2405.16755](https://arxiv.org/abs/2405.16755); [BIRD LB](https://bird-bench.github.io/)
- CHASE-SQL — Mohammadreza Pourreza, Hailong Li, Ruoxi Sun, Yeounoh Chung, et al. "CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL." arXiv:2410.01943. Generators: divide-and-conquer, query-plan CoT, instance-aware synthetic few-shot; fine-tuned pairwise selector. Abstract: 73.0% test / 73.01% dev. LB (Apr 2025 update): CHASE-SQL + Gemini 74.90 dev / 76.02 test. Venue ICLR 2025 and backbone Gemini-1.5-Pro **[unverified — not on the arXiv page]**. — [arXiv 2410.01943](https://arxiv.org/abs/2410.01943); [BIRD LB](https://bird-bench.github.io/)
- XiYan-SQL — Yingqi Gao, Yifu Liu, Xiaoxia Li, Xiaorong Shi, et al. "A Preview of XiYan-SQL: A Multi-Generator Ensemble Framework for Text-to-SQL." arXiv:2411.08599 (2024). Abstract: 75.63% BIRD test. LB: XiYan-SQL 73.34 dev / 75.63 test; single model XiYanSQL-QwenCoder-32B 67.01 / 69.03. — [arXiv 2411.08599](https://arxiv.org/abs/2411.08599); [BIRD LB](https://bird-bench.github.io/)
- OpenSearch-SQL — Xiangjin Xie, Guangwei Xu, Lingyan Zhao, Ruijie Guo. "OpenSearch-SQL: Enhancing Text-to-SQL with Dynamic Few-shot and Consistency Alignment." arXiv:2502.14913 (2025; SIGMOD 2025 **[unverified]**). Abstract: 69.3% dev, 72.28% test. LB: v2 + GPT-4o 69.30 / 72.28; v1 + GPT-4 61.34 / 64.95. — [arXiv 2502.14913](https://arxiv.org/abs/2502.14913); [BIRD LB](https://bird-bench.github.io/)
- RSL-SQL — Zhenbiao Cao, Yuanlei Zheng, Zhihao Fan, Xiaojin Zhang, Wei Chen, Xiang Bai. "RSL-SQL: Robust Schema Linking in Text-to-SQL Generation." arXiv:2411.00073 (2024). Abstract: 67.2% BIRD (GPT-4o). LB: + GPT-4o 67.21 dev / 68.70 test; + DeepSeek-v2 63.56 / 65.51. — [arXiv 2411.00073](https://arxiv.org/abs/2411.00073); [BIRD LB](https://bird-bench.github.io/)
- E-SQL — Hasan Alp Caferoğlu, Özgür Ulusoy. "E-SQL: Direct Schema Linking via Question Enrichment in Text-to-SQL." arXiv:2409.16751 (2024). LB: E-SQL + GPT-4o 65.58 dev / 66.29 test; **E-SQL + GPT-4o mini 61.60 dev / 59.81 test**. — [arXiv 2409.16751](https://arxiv.org/abs/2409.16751); [BIRD LB](https://bird-bench.github.io/)
- Distillery — Karime Maamari, Fadhil Abubaker, Daniel Jaroslawicz, Amine Mhedhbi. "The Death of Schema Linking? Text-to-SQL in the Age of Well-Reasoned Language Models." arXiv:2408.07702 (2024). Abstract: 71.83% (split not stated in abstract; matches LB test). LB: Distillery + GPT-4o 67.21 dev / 71.83 test. OmniSQL notes it fine-tunes GPT-4o on BIRD train (so not training-free). — [arXiv 2408.07702](https://arxiv.org/abs/2408.07702); [BIRD LB](https://bird-bench.github.io/); [OmniSQL](https://arxiv.org/html/2503.02240)
- ReFoRCE — Minghang Deng, Ashwin Ramachandran, Canwen Xu, Lanxiang Hu, et al. "ReFoRCE: A Text-to-SQL Agent with Self-Refinement, Consensus Enforcement, and Column Exploration." arXiv:2502.00675 (2025). Evaluated on Spider 2.0 (Spider 2.0-Snow 35.83, Spider 2.0-Lite 36.56), not BIRD. — [arXiv 2502.00675](https://arxiv.org/abs/2502.00675)
- Alpha-SQL — Boyan Li, Jiayi Zhang, Ju Fan, Yanwei Xu, et al. "Alpha-SQL: Zero-Shot Text-to-SQL using Monte Carlo Tree Search." arXiv:2502.17248, ICML 2025. Zero-shot/training-free MCTS; 69.7% BIRD dev with a 32B open model (LB: + Qwen2.5-Coder-32B-Instruct 69.70 dev / 70.26 test). — [arXiv 2502.17248](https://arxiv.org/abs/2502.17248); [BIRD LB](https://bird-bench.github.io/)
- MCTS-SQL — Shuozhi Yuan, Limin Chen, Miaomiao Yuan, Zhao Jin. "MCTS-SQL: Light-Weight LLMs can Master the Text-to-SQL through Monte Carlo Tree Search." arXiv:2501.16607; comment "Accepted AAAI 2026". BIRD dev (Table 1): Qwen-1.5B 40.69, Qwen-3B 46.71, Qwen-7B 53.61, **GPT-4o-mini 63.15**, GPT-4o 69.40, Gemini 2.5 Pro 72.91. Spider dev: GPT-4o-mini 86.16, GPT-4o 88.71. No baseline other than MCTS-SQL itself uses GPT-4o-mini in its tables. — [arXiv 2501.16607](https://arxiv.org/html/2501.16607)
- Agentar-Scale-SQL — Pengfei Wang, Baolin Sun, Xuemei Dong, Yaxun Dai, et al. "Agentar-Scale-SQL: Advancing Text-to-SQL through Orchestrated Test-Time Scaling." arXiv:2509.24403 (2025). 81.67% BIRD test; LB 74.90 dev / 81.67 test (Ant Group). — [arXiv 2509.24403](https://arxiv.org/abs/2509.24403); [BIRD LB](https://bird-bench.github.io/)
- Generic technique: Self-consistency — Xuezhi Wang, Jason Wei, Dale Schuurmans, Quoc Le, et al. "Self-Consistency Improves Chain of Thought Reasoning in Language Models." arXiv:2203.11171, ICLR 2023. — [arXiv 2203.11171](https://arxiv.org/abs/2203.11171)

#### (d) Fine-tuned open models and RL (2024–2025)
- CodeS — Haoyang Li, Jing Zhang, Hanbing Liu, Ju Fan, et al. "CodeS: Towards Building Open-source Language Models for Text-to-SQL." arXiv:2402.16347, SIGMOD 2024 (Proc. ACM Manag. Data **[issue unverified]**). LB: SFT CodeS-15B 58.47 dev / 60.37 test; SFT CodeS-7B 57.17 / 59.25. — [arXiv 2402.16347](https://arxiv.org/abs/2402.16347); [BIRD LB](https://bird-bench.github.io/)
- DTS-SQL — Mohammadreza Pourreza, Davood Rafiei. "DTS-SQL: Decomposed Text-to-SQL with Small Large Language Models." arXiv:2402.01117; Findings of EMNLP 2024 **[venue unverified]**. LB: DTS-SQL + DeepSeek 7B 55.8 dev / 60.31 test. — [arXiv 2402.01117](https://arxiv.org/abs/2402.01117); [BIRD LB](https://bird-bench.github.io/)
- SENSE — Jiaxi Yang, Binyuan Hui, Min Yang, Jian Yang, Junyang Lin, Chang Zhou. "Synthesizing Text-to-SQL Data from Weak and Strong LLMs." arXiv:2408.03256, ACL 2024. LB: SENSE (13B) 55.48 dev / 63.39 test. — [arXiv 2408.03256](https://arxiv.org/abs/2408.03256); [BIRD LB](https://bird-bench.github.io/)
- Qwen2.5-Coder — Binyuan Hui, Jian Yang, Zeyu Cui, Jiaxi Yang, et al. "Qwen2.5-Coder Technical Report." arXiv:2409.12186 (2024). BIRD dev as measured by OmniSQL (Gre/Maj@8): 7B-Instruct 50.9/61.3; 14B 61.5/66.1; 32B 64.5/67.0. — [arXiv 2409.12186](https://arxiv.org/abs/2409.12186); [OmniSQL](https://arxiv.org/html/2503.02240)
- OmniSQL — see Section 3 (64.5/67.0 dev for 32B in paper).
- SQL-R1 — Peixian Ma, Xialie Zhuang, Chengjin Xu, Xuhui Jiang, Ran Chen, Jian Guo. "SQL-R1: Training Natural Language to SQL Reasoning Model By Reinforcement Learning." arXiv:2504.08600; comment "Accepted by NeurIPS 2025". RL on 5K SynSQL-Complex pairs (optional 200K SFT cold start), self-consistency over 8 candidates. BIRD dev (Table 1): 3B 54.6, 7B 66.6, 14B 67.1 (Qwen2.5-Coder bases). Internal inconsistency: 7B also reported as 63.1 elsewhere in the paper, and Table 4 attributes the same numbers to an OmniSQL-7B initialisation. — [arXiv 2504.08600](https://arxiv.org/html/2504.08600)
- Reasoning-SQL — Mohammadreza Pourreza, Shayan Talaei, Ruoxi Sun, Xingchen Wan, et al. "Reasoning-SQL: Reinforcement Learning with SQL Tailored Partial Rewards for Reasoning-Enhanced Text-to-SQL." arXiv:2503.23157 (2025; venue not in arXiv metadata). GRPO with partial rewards. LB: Reasoning-SQL 14B 72.29 dev / 72.78 test (within a CHASE-style pipeline **[unverified detail]**). — [arXiv 2503.23157](https://arxiv.org/abs/2503.23157); [BIRD LB](https://bird-bench.github.io/)
- Arctic-Text2SQL-R1 — Zhewei Yao, Guoheng Sun, Lukasz Borchmann, Gaurav Nuti, et al. "Arctic-Text2SQL-R1: Simple Rewards, Strong Reasoning in Text-to-SQL." arXiv:2505.20315 (2025). LB single-model track (self-consistency "Few"): 32B 72.20 dev / 73.84 test; 14B 71.40 / 72.22; 7B 70.70 / – . — [arXiv 2505.20315](https://arxiv.org/abs/2505.20315); [BIRD LB](https://bird-bench.github.io/)
- Other small-model entries on LB: CSC-SQL + Qwen2.5-Coder-7B 69.19 / 71.72; SLM-SQL + Qwen2.5-Coder-1.5B 67.08 / 70.49. — [BIRD LB](https://bird-bench.github.io/)

#### (e) Clinical / EHR text-to-SQL
- TREQS / MIMICSQL — Ping Wang, Tian Shi, Chandan K. Reddy. "Text-to-SQL Generation for Question Answering on Electronic Medical Records." arXiv:1908.01839 (2019); WWW 2020 and MIMICSQL size (10,000 pairs from MIMIC-III) **[unverified]**. — [arXiv 1908.01839](https://arxiv.org/abs/1908.01839)
- EHRSQL — Gyubok Lee, Hyeonji Hwang, Seongsu Bae, Yeonsu Kwon, et al. "EHRSQL: A Practical Text-to-SQL Benchmark for Electronic Health Records." arXiv:2301.07695, NeurIPS 2022 Datasets and Benchmarks Track. Utterances collected from 222 hospital staff (physicians, nurses, insurance review, health records teams); linked to MIMIC-III and eICU; includes time expressions and unanswerable (held-out) questions. — [arXiv 2301.07695](https://arxiv.org/abs/2301.07695)
- EHRSQL 2024 shared task — Gyubok Lee, Sunjun Kweon, Seongsu Bae, Edward Choi. "Overview of the EHRSQL 2024 Shared Task on Reliable Text-to-SQL Modeling on Electronic Health Records." Proceedings of the 6th Clinical Natural Language Processing Workshop (ClinicalNLP @ NAACL 2024), Mexico City, pp. 644–654, ACL. DOI 10.18653/v1/2024.clinicalnlp-1.62; arXiv:2405.06673. >100 teams applied, 8 completed. — [ACL Anthology](https://aclanthology.org/2024.clinicalnlp-1.62/); [arXiv 2405.06673](https://arxiv.org/abs/2405.06673)

### Inferences
- Paradigm shift summary for the chapter: (a) schema-encoding PLMs (RAT-SQL, Graphix-T5, RESDSQL, PICARD) dominated Spider but score ≤ ~25% on BIRD in the T5 baselines; (b) ICL/decomposition with GPT-4 lifted BIRD dev to ~51–58%; (c) the 2024–2025 SOTA is driven by test-time compute — multiple generators + value retrieval + selector (CHESS, CHASE-SQL, XiYan, OpenSearch-SQL, Agentar-Scale-SQL); (d) a parallel line closes the gap with open 7–32B models via synthetic data (SENSE, OmniSQL) and RL (SQL-R1, Reasoning-SQL, Arctic-R1).
- Many SOTA pipelines use stronger backbones (GPT-4o, Gemini) and/or fine-tuned components (CHASE-SQL selector, Distillery fine-tunes GPT-4o, CHESS fine-tuned parts) — so they are not directly comparable to a training-free gpt-4o-mini system.
- The EHR line evaluates reliability/abstention (unanswerable questions), which matters for a medical QA thesis even though the user's main benchmark is BIRD.

### Gaps
- No BIRD dev numbers found for IRNet, RAT-SQL, PICARD, RESDSQL, Graphix-T5, C3, ACT-SQL (they are Spider-era / not on LB).
- Exact backbones for CHESS, SuperSQL, Reasoning-SQL leaderboard entries and the CHASE-SQL venue were not verified in this session.
- EHRSQL 2024 metric (Reliability Score RS(0/5/10/N)), dataset size and top team results were not on the pages fetched; read the PDF.
- MIMICSQL size and TREQS venue not verified.

## 3. OmniSQL details (contributions, SynSQL-2.5M, evaluation table)

### Takeaway
OmniSQL (PVLDB 18(11), 2025) contributes a scalable synthesis pipeline and SynSQL-2.5M (2,544,390 samples over 16,583 databases); its main table reports GPT-4o-mini at 58.8 (greedy) / 61.5 (majority of 8) on BIRD dev and OmniSQL-7B/14B/32B at 63.9/66.1, 64.2/65.9, 64.5/67.0.

### Cited Findings
- Bibliography: Haoyang Li, Shang Wu, Xiaokang Zhang, Xinmei Huang, Jing Zhang, Fuxin Jiang, Shuai Wang, Tieying Zhang, Jianjun Chen, Rui Shi, Hong Chen, Cuiping Li. "OmniSQL: Synthesizing High-quality Text-to-SQL Data at Scale." PVLDB 18(11), 2025. arXiv:2503.02240 (v2 13 Jul 2025). Renmin University of China & ByteDance. — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
- Contributions: (1) automatic, scalable synthesis framework (databases → complexity-aware SQL → stylized questions → CoT solutions); (2) SynSQL-2.5M dataset and OmniSQL-7B/14B/32B models; (3) claimed SOTA among models with fewer parameters. — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
- SynSQL-2.5M: 2,544,390 <database, question, SQL, CoT> quadruples (2,412,915 unique SQL); 16,583 synthetic SQLite databases, avg 10.15 tables and 74.07 columns; four SQL complexity levels (simple, moderate, complex, highly complex); avg 1.75 joins and 4.00 tables per query; >2M unique SQL skeletons, 83 distinct functions, ~40% use CTEs; nine question language styles; CoT chosen by majority vote over 8 samples at temperature 0.8; human eval on 1,000 samples: 96% DBs realistic, 97% questions meaningful, 89% SQL appropriate, 86% fully correct. No domain count given. — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
- Decoding protocol: Gre = greedy (temperature 0); Maj = 8 sampled responses, SQL grouped by execution result, largest group chosen. BIRD dev = EX; Spider = test-suite accuracy. — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
- Main table (BIRD dev Gre / Maj; Spider dev Gre / Maj; Spider test Gre / Maj): — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
  - GPT-4o-mini: 58.8 / 61.5; 70.4 / 71.0; 82.4 / 83.7
  - GPT-4-Turbo: 62.0 / 63.6; 72.4 / 72.2; 83.4 / 84.2
  - GPT-4o: 61.9 / 64.0; 70.9 / 70.7; 83.2 / 84.9
  - DeepSeek-V3 (671B MoE): 63.2 / 63.8; 73.1 / 73.5; 85.5 / 85.8
  - Qwen2.5-Coder-7B-Instruct: 50.9 / 61.3; 73.4 / 77.1; 82.2 / 85.6
  - Qwen2.5-Coder-14B-Instruct: 61.5 / 66.1; 78.1 / 80.6; 86.6 / 88.0
  - Qwen2.5-Coder-32B-Instruct: 64.5 / 67.0; 77.7 / 77.9; 87.5 / 88.0
  - OmniSQL-7B: 63.9 / 66.1; 81.2 / 81.6; 87.9 / 88.9
  - OmniSQL-14B: 64.2 / 65.9; 81.4 / 82.0; 88.3 / 88.3
  - OmniSQL-32B: 64.5 / 67.0; 80.9 / 80.9; 87.6 / 89.8
- OmniSQL compares OmniSQL-32B Maj 67.0 with Distillery + GPT-4o 67.2 on BIRD dev (Distillery fine-tunes GPT-4o on BIRD train); names CHASE-SQL and Alpha-SQL as multi-stage frameworks without numbers. — [arXiv 2503.02240](https://arxiv.org/html/2503.02240)
- BIRD LB entries for OmniSQL (Mar 04, 2025): OmniSQL-32B 69.23 dev / 72.05 test; OmniSQL-7B listed as 69.04 dev / 67.97 test. These differ from the paper's 67.0 Maj — the leaderboard submission evidently used a different inference setup. — [BIRD LB](https://bird-bench.github.io/); contradicts paper table in [arXiv 2503.02240](https://arxiv.org/html/2503.02240)

### Inferences
- The user's quoted baseline "58.8 greedy / 61.5 majority-of-8" matches the paper exactly. With the same backbone and the same sample budget (8), the user's 63.6% is +2.1 points over OmniSQL's Maj@8 gpt-4o-mini and roughly matches GPT-4-Turbo Maj (63.6) and is close to GPT-4o Maj (64.0). The full-budget 65.1% exceeds GPT-4o Maj (64.0) and DeepSeek-V3 Maj (63.8), but is below OmniSQL-7B Maj (66.1) and OmniSQL-32B Maj (67.0).
- When comparing to OmniSQL, cite the paper table (not the leaderboard) since the leaderboard numbers come from an undocumented setup.

### Gaps
- The last ~29K characters of the OmniSQL HTML (appendix, possibly per-difficulty breakdown, BIRD with/without evidence, other benchmarks like Spider2.0-SQLite, EHRSQL, ScienceBenchmark) were not read. OmniSQL is known to evaluate on EHRSQL too **[unverified]** — worth checking for the medical thesis angle.
- The reason for the LB vs paper difference for OmniSQL was not found.

## 4. Current BIRD leaderboard top scores (2025–2026)

### Takeaway
As of the leaderboard fetched on 2026-11-21, the top overall test EX is 83.40 (AskData, AT&T, Oct 2026; dev 78.49); the best published, citable 2025 system is Agentar-Scale-SQL (81.67 test / 74.90 dev). Human performance is 92.96 test. Most top entries are closed/no-code industrial systems.

### Cited Findings
- Top of overall LB (dev / test): 1 AskData (AT&T CDO-DSAIR, Oct 22 2026) 78.49 / 83.40; 2 GrainSQL (Purdue, Sep 26 2026) 77.77 / 82.95; 3 DataGallery-Text2SQL (Huawei, Sep 7 2026) 78.10 / 82.39; 4 SiriusAI-SQL (Tencent, Aug 22 2026) 77.77 / 82.28; 5 Agentar-Scale-SQL (Ant Group, Sep 25 2025, code available) 74.90 / 81.67; 6 Sber Text2SQL (Jun 2026) 75.74 / 81.33; 7 Xiaomi Text2SQL (May 2026) 73.66 / 80.83; 9 DeepEye (HKUST-GZ) 74.49 / 79.09; 24 CHASE-SQL + Gemini 74.90 / 76.02. — [BIRD LB](https://bird-bench.github.io/)
- Single-trained-model track (with self-consistency category): Gemini-SQL2 (Google, Jun 2026, "Many" 8–32 samples) 74.12 / 80.04; ReToolSQL-31B (JPMorganChase) 74.77 / 78.14; Q-SQL 30B-A3B MoE 72.99 / 76.47; Databricks RLVR 32B – / 75.68; Arctic-Text2SQL-R1-32B 72.20 / 73.84. — [BIRD LB](https://bird-bench.github.io/)
- 2026 frontier-model baselines (on a "New Dev" split): Claude Opus 4.6 68.77 / 70.15; Claude 4.5 Sonnet 67.34 / 66.85; Qwen3-Coder-480B-A35B 66.17 / 68.14; DeepSeek-R1 61.67 / 60.93. — [BIRD LB](https://bird-bench.github.io/)
- Leaderboard notes: 2026 entries marked "New Dev" use a new/cleaner dev split (bird-sql-dev-1106), so their dev numbers are not directly comparable to the original dev; efficiency moved to R-VES (Aug); a separate single-model leaderboard exists; a Mini-Dev 2026 update was posted Oct 28, 2026. — [BIRD LB](https://bird-bench.github.io/)

### Inferences
- The gap between the user's 65.1% (original dev, gpt-4o-mini, training-free) and LB SOTA (~78% dev) is large; the defensible framing is "small proprietary backbone, equal-budget comparison" rather than SOTA.
- Because 2026 entries use a new dev split, the user should state they evaluate on the original BIRD dev (1,534) like OmniSQL, to keep comparisons valid.

### Gaps
- Leaderboard page shows conflicting update dates ("Updated October 9, 2026" header vs entries dated Nov 6, 2026). Methods/backbones of most top-10 entries are undisclosed (no papers).

## 5. Most similar works and the user's distinguishing contribution

### Takeaway
The closest published comparators are MCTS-SQL with GPT-4o-mini (63.15 dev), E-SQL with GPT-4o mini (61.60 dev), and the OmniSQL gpt-4o-mini Maj@8 baseline (61.5); architecturally, CHESS (value retrieval + candidates + selection), OpenSearch-SQL (dynamic few-shot + consistency), MCS-SQL (multiple prompts + selection) and Alpha-SQL (training-free/zero-shot) are the nearest designs. None of these report equal-budget comparisons with paired significance tests and pre-registered tuning/held-out splits, which is the user's methodological contribution.

### Cited Findings
- Same backbone, training-free: MCTS-SQL + GPT-4o-mini 63.15 BIRD dev (paper Table 1); E-SQL + GPT-4o mini 61.60 dev / 59.81 test (LB); OmniSQL GPT-4o-mini 58.8 Gre / 61.5 Maj@8 (paper). — [MCTS-SQL](https://arxiv.org/html/2501.16607); [BIRD LB](https://bird-bench.github.io/); [OmniSQL](https://arxiv.org/html/2503.02240)
- Value/entity retrieval + candidate generation + selection: CHESS (IR + CG + UT) 68.31 dev. — [arXiv 2405.16755](https://arxiv.org/abs/2405.16755); [BIRD LB](https://bird-bench.github.io/)
- Dynamic few-shot + consistency alignment / self-consistency: OpenSearch-SQL v2 + GPT-4o 69.3 dev. — [arXiv 2502.14913](https://arxiv.org/abs/2502.14913)
- Multiple prompts + multiple-choice selection: MCS-SQL + GPT-4 63.36 dev. — [arXiv 2405.07467](https://arxiv.org/abs/2405.07467); [BIRD LB](https://bird-bench.github.io/)
- Multi-path generation + trained pairwise selector: CHASE-SQL 73.01 dev. — [arXiv 2410.01943](https://arxiv.org/abs/2410.01943)
- Training-free tree search with open model: Alpha-SQL + Qwen2.5-Coder-32B 69.7 dev. — [arXiv 2502.17248](https://arxiv.org/abs/2502.17248)
- Majority voting over execution results is the standard Maj@8 protocol in OmniSQL and SQL-R1 (8 candidates). — [OmniSQL](https://arxiv.org/html/2503.02240); [SQL-R1](https://arxiv.org/html/2504.08600)
- Self-consistency origin: Wang et al., ICLR 2023. — [arXiv 2203.11171](https://arxiv.org/abs/2203.11171)

### Inferences
- Positioning (numbers from user's brief + sources above): at an 8-sample budget the user's 63.6% beats every published gpt-4o-mini BIRD dev number found (OmniSQL Maj@8 61.5, E-SQL 61.60) and is +0.45 over MCTS-SQL+GPT-4o-mini (63.15) — within noise; at full budget 65.1% is ~+2 over MCTS-SQL/gpt-4o-mini and comparable to E-SQL+GPT-4o (65.58) and GPT-4o Maj@8 (64.0). Note that MCTS-SQL and E-SQL do not report their sampling budget in an equal-budget way, so only the OmniSQL comparison is strictly equal-budget.
- Distinguishing contributions to emphasise: (1) equal-budget comparison against the same-backbone majority-vote baseline (most papers compare against greedy or weaker-backbone baselines); (2) pre-registered tuning/held-out split of BIRD dev (most systems tune on the full dev, risking overfitting — none of the papers fetched describe a held-out dev split); (3) paired significance tests (e.g., McNemar/bootstrap) — none of the fetched papers report significance; (4) reporting negative results (ablations that did not help). These claims about "none report" are inferences from the abstracts/tables read, not an exhaustive audit.
- A "conditional selector" (invoke selection only when candidates disagree) resembles CHASE-SQL's selector and MCS-SQL's multiple-choice selection but without fine-tuning, which keeps the pipeline training-free.

### Gaps
- Did not verify whether CHESS/OpenSearch-SQL/MCS-SQL report gpt-4o-mini ablations or significance tests (full papers not read).
- Sampling budgets (number of LLM calls per question) for MCTS-SQL and E-SQL with GPT-4o-mini were not extracted; needed for a fair cost comparison.
- No paper was found that combines EHR/clinical text-to-SQL with BIRD-style agentic pipelines on gpt-4o-mini; a targeted search would be needed.
