# Background theory (Cơ sở lý thuyết) for a training-free GPT-4o-mini text-to-SQL system

Scope: the concepts behind each part of the pipeline: OmniSQL-style prompt → value retrieval → BM25 few-shot → greedy + 8 samples (T=0.8) + 8 "query plan" samples → execution-guided repair → execution-result majority vote → LLM selector only when there is no majority → EX + exact McNemar test.
Verification status: identifiers, authors and abstract-level numbers marked "verified" were checked this session against the arXiv API, the arXiv HTML, ACL Anthology or official pages. Items marked "(not re-verified this session)" come from well-known canonical references. They are listed again under Gaps so the writer can check them before citing.

---

## 1. Large language models, in-context learning, temperature sampling

### Takeaway
LLMs such as GPT-3, GPT-4 and GPT-4o-mini can do a task from an instruction plus a few demonstrations placed in the prompt (in-context learning, ICL), with no gradient updates. That is what makes the system "training-free". Temperature controls how random each sampled token is, and therefore how diverse the candidate set is.

### Cited Findings
**Primary citations (verified IDs and authors)**
- Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., et al. (31 authors, last author Amodei, D.). "Language Models are Few-Shot Learners." NeurIPS 2020. arXiv:2005.14165. https://arxiv.org/abs/2005.14165
- OpenAI (Achiam, J., Adler, S., Agarwal, S., et al.). "GPT-4 Technical Report." arXiv:2303.08774, 2023. https://arxiv.org/abs/2303.08774
- OpenAI. "GPT-4o mini: advancing cost-efficient intelligence." Official blog post, 18 July 2024. https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/
- Holtzman, A., Buys, J., Du, L., Forbes, M., Choi, Y. "The Curious Case of Neural Text Degeneration." ICLR 2020. arXiv:1904.09751. https://arxiv.org/abs/1904.09751

**Key facts**
- GPT-3 is a 175-billion-parameter autoregressive language model. It does many NLP tasks "few-shot": the task and demonstrations are given purely as text, with no gradient updates or fine-tuning. This is the original definition of in-context learning (zero-shot, one-shot and few-shot settings). — [Brown et al. 2020](https://arxiv.org/abs/2005.14165)
- GPT-4 is a large multimodal model that takes image and text input. It reaches human-level performance on many professional and academic benchmarks. The report also says some of its performance was predicted from much smaller models (predictable scaling). — [OpenAI 2023](https://arxiv.org/abs/2303.08774)
- GPT-4o mini was announced on 18 July 2024. OpenAI's own reported numbers:
  - MMLU 82.0% (Gemini Flash 77.9%, Claude Haiku 73.8%)
  - HumanEval 87.2%
  - context window 128K tokens, up to 16K output tokens
  - knowledge cutoff October 2023
  - price $0.15 per 1M input tokens and $0.60 per 1M output tokens
  - text and vision through the Chat Completions, Assistants and Batch APIs

  These are vendor-reported figures. — [OpenAI 2024](https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/)
- Decoding strategies such as greedy, temperature, top-k and nucleus (top-p) sampling strongly affect the quality and diversity of generated text. Holtzman et al. is the standard reference for stochastic decoding and proposes nucleus sampling. — [Holtzman et al. 2020](https://arxiv.org/abs/1904.09751)
- **Temperature formula** (standard definition): for logits z_i, p_i = exp(z_i / T) / Σ_j exp(z_j / T).
  - T → 0 approaches greedy (argmax) decoding.
  - T = 1 is the model's own distribution.
  - T > 1 flattens the distribution and increases diversity.
  - The "temperature" name comes from the Boltzmann distribution (Ackley, Hinton & Sejnowski 1985, "A Learning Algorithm for Boltzmann Machines," Cognitive Science 9(1):147–169), and it was popularized for softmax by Hinton, Vinyals & Dean 2015, "Distilling the Knowledge in a Neural Network," arXiv:1503.02531. (not re-verified this session)
- CHASE-SQL measured the diversity/quality trade-off directly on BIRD dev. Raising temperature increases candidate diversity but "often compromise[s] the quality of the candidates". Self-consistency accuracy generally *drops* as temperature rises "since the majority cluster becomes smaller", for example:
  - divide-and-conquer generator: 66.43 at T=0.5 vs 64.41 at T=1.8
  - query-plan generator: 65.78 vs 65.51

  — [Pourreza et al. 2024, CHASE-SQL](https://arxiv.org/abs/2410.01943)

### Inferences
- The system uses T=0.8 for its 16 samples and a greedy (T=0) anchor. This sits between the "too little diversity" and "too much noise" regimes that CHASE-SQL describes. The greedy query is a high-precision anchor; the samples add coverage.
- Because GPT-4o-mini is used as-is, the theory chapter should frame the work as *inference-time* (test-time) methods: prompting, retrieval, sampling and selection, not learning.

### Gaps
- The formula and the Ackley/Hinton citations for temperature were not fetched this session. Check them before citing.
- OpenAI has not disclosed GPT-4o-mini's parameter count or training data. No peer-reviewed technical report exists, so only the blog post (and the GPT-4o System Card, arXiv:2410.21276, not checked here) can be cited.

---

## 2. Chain-of-thought prompting and zero-shot CoT

### Takeaway
Asking the model to write intermediate reasoning before the answer improves multi-step reasoning a lot. The original method uses few-shot exemplars (Wei et al.). A single trigger phrase such as "Let's think step by step" also works zero-shot (Kojima et al.). The OmniSQL prompt's step-by-step instruction is zero-shot CoT, and the "query plan" prompt is a structured CoT variant.

### Cited Findings
**Primary citations (verified)**
- Wei, J., Wang, X., Schuurmans, D., Bosma, M., Ichter, B., Xia, F., Chi, E., Le, Q., Zhou, D. "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models." NeurIPS 2022. arXiv:2201.11903. https://arxiv.org/abs/2201.11903
- Kojima, T., Gu, S. S., Reid, M., Matsuo, Y., Iwasawa, Y. "Large Language Models are Zero-Shot Reasoners." NeurIPS 2022. arXiv:2205.11916. https://arxiv.org/abs/2205.11916

**Key facts**
- CoT shows a few exemplars whose answers include intermediate natural-language reasoning steps. The authors tested it on three LLMs for arithmetic, commonsense and symbolic reasoning. PaLM 540B with eight CoT exemplars reached state of the art on GSM8K. — [Wei et al. 2022](https://arxiv.org/abs/2201.11903)
- DiVeRSe's abstract summarizes the effect: prompting methods raised the GSM8K solve rate from 17.9% to 58.1%. — [Li et al. 2023](https://arxiv.org/abs/2206.02336)
- Zero-shot CoT adds "Let's think step by step" before the answer. With InstructGPT text-davinci-002:
  - MultiArith: 17.7% → 78.7%
  - GSM8K: 10.4% → 40.7%

  PaLM 540B showed similar gains. Datasets: MultiArith, GSM8K, AQUA-RAT, SVAMP, Last Letter, Coin Flip, Date Understanding, Tracking Shuffled Objects. — [Kojima et al. 2022](https://arxiv.org/abs/2205.11916)
- CoT in text-to-SQL:
  - DIN-SQL breaks generation into sub-problems (schema linking, classification and decomposition, generation, self-correction). This raises few-shot accuracy of three LLMs by about 10%, to 85.3% EX on the Spider holdout (previous SOTA 79.9) and 55.9% on the BIRD holdout. — [Pourreza & Rafiei 2023](https://arxiv.org/abs/2304.11015)
  - CHASE-SQL's "Query Plan CoT" turns SQLite `EXPLAIN` output into readable text and reasons in three steps that mirror "the steps a database engine takes during execution": (1) find the relevant tables, (2) perform operations (counting, filtering, matching), (3) return the selected columns. As a single-candidate method with Gemini 1.5 Pro on BIRD dev it scores 63.62 vs a 57.75 baseline (+5.87), and 65.51 with the query fixer. — [CHASE-SQL](https://arxiv.org/abs/2410.01943)

### Inferences
- The system's second ("query plan") prompt is a direct descendant of CHASE-SQL's Query Plan CoT. Its value lies less in being more accurate on its own and more in producing *differently distributed* errors (see Section 7).

### Gaps
- The exact GSM8K numbers for PaLM 540B with and without CoT (commonly cited as 17.9% → 56.9%) were not re-verified from the Wei et al. tables. The abstract-level claim and the DiVeRSe summary (17.9 → 58.1) were verified, and the two figures differ slightly.

---

## 3. Self-consistency, Universal Self-Consistency, and execution-based voting

### Takeaway
Self-consistency samples several reasoning paths and returns the answer most of them agree on. For code and SQL, "agreement" is measured by *execution results* (MBR-exec), so candidates whose SQL text differs but returns the same rows count as one vote. This is the theoretical basis for the system's result-set majority vote. Universal Self-Consistency (USC) instead has the LLM itself pick the most consistent answer, which is the basis for an LLM selector.

### Cited Findings
**Primary citations (verified)**
- Wang, X., Wei, J., Schuurmans, D., Le, Q., Chi, E., Narang, S., Chowdhery, A., Zhou, D. "Self-Consistency Improves Chain of Thought Reasoning in Language Models." ICLR 2023. arXiv:2203.11171. https://arxiv.org/abs/2203.11171
- Chen, X., Aksitov, R., Alon, U., Ren, J., Xiao, K., Yin, P., Prakash, S., Sutton, C., Wang, X., Zhou, D. "Universal Self-Consistency for Large Language Model Generation." arXiv:2311.17311, 2023 (Google; ICML 2024 workshop poster). https://arxiv.org/abs/2311.17311
- Shi, F., Fried, D., Ghazvininejad, M., Zettlemoyer, L., Wang, S. I. "Natural Language to Code Translation with Execution." EMNLP 2022. arXiv:2204.11454. https://arxiv.org/abs/2204.11454
- Ni, A., Iyer, S., Radev, D., Stoyanov, V., Yih, W., Wang, S. I., Lin, X. V. "LEVER: Learning to Verify Language-to-Code Generation with Execution." ICML 2023. arXiv:2302.08468. https://arxiv.org/abs/2302.08468

**Definitions and formulas**
- **Self-consistency.** Sample m reasoning paths with answers a_1..a_m (temperature sampling), then output â = argmax_a Σ_{i=1}^{m} 𝟙[a_i = a]. Greedy decoding is replaced by "sample-and-marginalize" over reasoning paths. — [Wang et al. 2023](https://arxiv.org/abs/2203.11171)
- **Self-consistency gains over CoT greedy decoding** (abstract):

  | Benchmark | Gain |
  |---|---|
  | GSM8K | +17.9% |
  | SVAMP | +11.0% |
  | AQuA | +12.2% |
  | StrategyQA | +6.4% |
  | ARC-challenge | +3.9% |

  — [Wang et al. 2023](https://arxiv.org/abs/2203.11171)
- **MBR-exec.** Each candidate program is run on a small set of test inputs. The candidate chosen is the one with minimum Bayes risk, i.e. maximum agreement of its execution results with the other candidates: p̂ = argmax_{p∈P} Σ_{p'∈P} 𝟙[exec(p) = exec(p')]. This beats execution-unaware selection in few-shot code generation. — [Shi et al. 2022](https://arxiv.org/abs/2204.11454)
- **LEVER.** Trains a verifier that scores each sampled program using the NL input, the program and its execution result, then reranks by combining the verifier score with generation probability. It improves code-davinci-002 by 4.6–10.9% across four datasets. Note that LEVER *trains* a verifier, so it is not training-free. — [Ni et al. 2023](https://arxiv.org/abs/2302.08468)
- **USC.** Standard self-consistency needs answers in a format that can be extracted and compared exactly. USC concatenates all samples and asks the LLM to choose the most consistent one. Results:
  - math: matches standard SC without needing matching answer formats
  - code generation: matches execution-based voting *without* access to execution results
  - open-ended tasks (where SC cannot be applied): beats greedy decoding

  — [Chen et al. 2023](https://arxiv.org/abs/2311.17311)
- **Execution-based self-consistency in text-to-SQL:**
  - C3 (zero-shot ChatGPT) uses execution-based consistency voting and reaches 82.3% EX on the Spider holdout. — [Dong et al. 2023](https://arxiv.org/abs/2307.07306)
  - SQL-PaLM also uses execution-based consistency decoding (abstract has no numbers). — [Sun et al. 2023](https://arxiv.org/abs/2306.00739)
- **Self-consistency on BIRD dev** (Gemini 1.5 Pro, CHASE-SQL): single query 63.01 → self-consistency 68.84 (+5.84). The oracle upper bound over the same candidates is 82.79 (+19.78). "The most consistent answers would not always be the correct ones, with an upper-bound performance 14% higher than that achieved through self-consistency." — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- MCS-SQL groups candidate SQL by identical execution result and defines a candidate's **confidence** as the fraction of candidates that share its result. Its "majority vote" baseline picks the highest-confidence query: 62.8 EX on BIRD dev with GPT-4. — [Lee et al. 2025, MCS-SQL](https://arxiv.org/abs/2405.07467)

### Inferences
- The system's vote is MBR-exec / execution-based self-consistency applied to SQL. Grouping by result set merges semantically equivalent SQL, such as different JOIN orders or aliases.
- The "no majority" condition matches MCS-SQL's low-confidence regime. When the largest cluster is small, the vote carries little information, which is where an LLM/USC-style selector should be called.

### Gaps
- Shi et al.'s numeric gains (e.g. on MBPP) are not in the abstract and were not fetched.
- USC's exact numbers were not extracted.

---

## 4. Few-shot demonstration selection: DAIL-SQL, retrieval-based ICL, BM25

### Takeaway
Which demonstrations go into the prompt matters. Picking examples similar to the test question (kNN retrieval) beats random selection (Liu et al.). DAIL-SQL turned similarity-based selection into the standard for text-to-SQL. BM25 is the classic lexical relevance function used to retrieve those examples.

### Cited Findings
**Primary citations**
- Gao, D., Wang, H., Li, Y., Sun, X., Qian, Y., Ding, B., Zhou, J. "Text-to-SQL Empowered by Large Language Models: A Benchmark Evaluation." arXiv:2308.15363 (2023). Published in PVLDB 17(5), 2024 (not re-verified this session; commonly cited as pp. 1132–1145). https://arxiv.org/abs/2308.15363 (verified ID and authors)
- Liu, J., Shen, D., Zhang, Y., Dolan, B., Carin, L., Chen, W. "What Makes Good In-Context Examples for GPT-3?" arXiv:2101.06804 (2021). Published at DeeLIO 2022 (not re-verified). https://arxiv.org/abs/2101.06804 (verified)
- Robertson, S., Zaragoza, H. "The Probabilistic Relevance Framework: BM25 and Beyond." Foundations and Trends in Information Retrieval 3(4):333–389, 2009. DOI 10.1561/1500000019 (not re-verified this session). https://doi.org/10.1561/1500000019

**Key facts**
- Retrieving demonstrations that are semantically similar to the test input (kNN in embedding space) beats random selection. Gains reported in the abstract: +41.9% on ToTTo table-to-text and +45.5% on NQ open-domain QA. — [Liu et al. 2021](https://arxiv.org/abs/2101.06804)
- DAIL-SQL systematically compares question representation, example selection and example organization for LLM text-to-SQL. It reached 86.6% EX on the Spider leaderboard (GPT-4) and also treats token efficiency as a cost metric. — [Gao et al. 2023](https://arxiv.org/abs/2308.15363)
- DAIL-SQL method details (from the paper body, not re-verified this session):
  - selection ranks train examples by similarity of *masked* questions (domain words replaced by mask tokens), then favours those whose SQL skeleton is similar to a pre-predicted SQL above a threshold
  - organization shows question–SQL pairs without their schemas to save tokens
- MCS-SQL shows few-shot retrieval matters on BIRD. On BIRD dev with GPT-4, adding few-shot examples (k = 20, selected by question / masked-question similarity) raised EX from 55.2 to 60.0 (+4.8), the largest single gain in its ablation. — [MCS-SQL](https://arxiv.org/abs/2405.07467)
- **BM25 scoring function** (standard form, Robertson & Zaragoza 2009): score(D, Q) = Σ_{q∈Q} IDF(q) · f(q,D)·(k1+1) / ( f(q,D) + k1·(1 − b + b·|D|/avgdl) ), where:
  - f(q,D) is term frequency, |D| is document length, avgdl is the average document length
  - k1 ≈ 1.2–2.0 controls term-frequency saturation, b ≈ 0.75 controls length normalization
  - IDF(q) = log( (N − n(q) + 0.5)/(n(q) + 0.5) ) in the Robertson–Spärck Jones form
  - BM25 came out of the Okapi system at TREC-3 (Robertson et al. 1994)

  (not re-verified this session) — [Robertson & Zaragoza 2009](https://doi.org/10.1561/1500000019)

### Inferences
- Retrieving 3 BIRD-train examples with BM25 is a lexical, training-free version of DAIL-SQL / Liu et al. selection. It needs no embedding model and suits BIRD questions, which share domain keywords with train items.
- Because BIRD train and dev use *different databases*, retrieved examples teach SQL patterns and BIRD conventions (evidence usage, CAST, division) rather than schema-specific answers.

### Gaps
- DAIL-SQL's BIRD numbers and its self-consistency gain were not fetched (only the abstract page loaded).
- The PVLDB volume and pages need checking (likely PVLDB 17(5):1132–1145).
- The BM25 formula is quoted from standard knowledge. Confirm the notation against Robertson & Zaragoza (2009), §3.

---

## 5. Schema linking and value retrieval (database content in prompts)

### Takeaway
Text-to-SQL needs two things. Schema linking maps question words to tables and columns. Value linking maps question words to stored cell values (e.g. "Fremont" → `city = 'Fremont'`). Putting real database content into the prompt, as example rows or matched values, is a standard technique from BRIDGE onward. CHESS (LSH) and CodeS (BM25 + LCS) built it into scalable value retrieval. The system's inverted index of stored text values works on the same principle.

### Cited Findings
**Primary citations (verified)**
- Lin, X. V., Socher, R., Xiong, C. "Bridging Textual and Tabular Data for Cross-Domain Text-to-SQL Semantic Parsing" (BRIDGE). Findings of EMNLP 2020. arXiv:2012.12627. https://arxiv.org/abs/2012.12627
- Li, H., Zhang, J., Li, C., Chen, H. "RESDSQL: Decoupling Schema Linking and Skeleton Parsing for Text-to-SQL." AAAI 2023 (oral). arXiv:2302.05965. https://arxiv.org/abs/2302.05965
- Talaei, S., Pourreza, M., Chang, Y.-C., Mirhoseini, A., Saberi, A. "CHESS: Contextual Harnessing for Efficient SQL Synthesis." arXiv:2405.16755 (2024; ICML 2025 workshop). https://arxiv.org/abs/2405.16755
- Li, H., Zhang, J., Liu, H., Fan, J., Zhang, X., Zhu, J., Wei, R., Pan, H., Li, C., Chen, H. "CodeS: Towards Building Open-source Language Models for Text-to-SQL." SIGMOD 2024 (Proc. ACM Manag. Data). arXiv:2402.16347. https://arxiv.org/abs/2402.16347
- Rajkumar, N., Li, R., Bahdanau, D. "Evaluating the Text-to-SQL Capabilities of Large Language Models." arXiv:2204.00498 (2022). https://arxiv.org/abs/2204.00498
- Chang, S., Fosler-Lussier, E. "How to Prompt LLMs for Text-to-SQL: A Study in Zero-shot, Single-domain, and Cross-domain Settings." NeurIPS 2023 Table Representation Learning Workshop. arXiv:2305.11853. https://arxiv.org/abs/2305.11853
- Li, J., Hui, B., Qu, G., Yang, J., Li, B., Li, B., Wang, B., Qin, B., Cao, R., Geng, R., Huo, N., Zhou, X., Ma, C., Li, G., Chang, K. C. C., Huang, F., Cheng, R., Li, Y. "Can LLM Already Serve as A Database Interface? A BIg Bench for Large-Scale Database Grounded Text-to-SQLs" (BIRD). NeurIPS 2023 (Datasets & Benchmarks). arXiv:2305.03111. https://arxiv.org/abs/2305.03111
- Li, H., Wu, S., Zhang, X., Huang, X., Zhang, J., Jiang, F., Wang, S., Zhang, T., Chen, J., Shi, R., Chen, H., Li, C. "OmniSQL: Synthesizing High-quality Text-to-SQL Data at Scale." arXiv:2503.02240 (2025). https://arxiv.org/abs/2503.02240

**Key facts**
- BIRD contains:
  - 12,751 question–SQL pairs
  - 95 databases totalling 33.4 GB
  - 37 professional domains

  It stresses that database *values* matter, using dirty values, external knowledge ("evidence") and efficiency. ChatGPT reached 40.08% EX against 92.96% for humans. — [Li et al. 2023, BIRD](https://arxiv.org/abs/2305.03111)
- BRIDGE adds the cell values that match question words ("anchor texts") to the serialized schema, which is the original "database content in the input" idea. Ensemble scores: Spider 71.1% dev / 67.5% test; WikiSQL 92.6% dev / 91.9% test. — [Lin et al. 2020](https://arxiv.org/abs/2012.12627)
- RESDSQL separates schema linking from skeleton parsing. A cross-encoder ranks and keeps relevant schema items before generation, and the SQL skeleton is generated before the full SQL. — [Li et al. 2023, RESDSQL](https://arxiv.org/abs/2302.05965)
- CHESS has four agents: Information Retriever, Schema Selector, Candidate Generator, Unit Tester. Its retriever uses **locality-sensitive hashing (LSH)** to find database values similar to question keywords, plus vector search over catalog descriptions. It reports 71.10% on the BIRD test set with ~83% fewer LLM calls than the leading method. The ICML 2025 workshop page says ~93% instead, so the sources disagree. In the CHASE-SQL ablation, removing LSH value retrieval drops BIRD dev EX from 73.01 to 70.09 (−2.92). — [CHESS](https://arxiv.org/abs/2405.16755); [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- CodeS is a family of open 1B–15B models with SQL-centric pre-training, schema-linking prompts and data augmentation, evaluated on Spider, BIRD and robustness variants. It is a source for "database value retrieval" prompt construction. — [CodeS](https://arxiv.org/abs/2402.16347)
- The CodeS value retriever is coarse-to-fine: a BM25 index over all values, then LCS-based matching. (From the paper body, not re-verified this session.)
- Rajkumar et al. found Codex a strong text-to-SQL baseline on Spider via prompting alone. They studied prompt formats that include `CREATE TABLE` statements and sample rows; the "CREATE TABLE + SELECT 3 rows" format is not re-verified this session. — [Rajkumar et al. 2022](https://arxiv.org/abs/2204.00498)
- Chang & Fosler-Lussier study how to represent schema and database content in prompts in zero-shot, single-domain and cross-domain settings. — [Chang & Fosler-Lussier 2023](https://arxiv.org/abs/2305.11853)
- MCS-SQL ablation on BIRD dev (GPT-4): schema linking +2.1 (50.7 → 52.8), *sample table contents* +2.4 (→ 55.2). — [MCS-SQL](https://arxiv.org/abs/2405.07467)
- With strong reasoning models, explicit schema *pruning* can be dropped. Maamari et al. give the full schema and reach 71.83% on BIRD (ranked first at the time), arguing that pruning mainly risks losing needed columns. — [Maamari et al. 2024, "The Death of Schema Linking?"](https://arxiv.org/abs/2408.07702)
- OmniSQL synthesizes SynSQL-2.5M (2.5M samples, >16,000 synthetic databases), trains OmniSQL-7B/14B/32B and evaluates on nine datasets. Its standard inference prompt is the base prompt the system reuses. — [OmniSQL](https://arxiv.org/abs/2503.02240)

**Inverted index (supporting IR concept)**
- An inverted index maps each term to its postings, i.e. the list of values or documents that contain it. This allows lookup in roughly O(number of query terms × postings length) instead of scanning the whole database. Standard references: Zobel, J., Moffat, A. "Inverted Files for Text Search Engines." ACM Computing Surveys 38(2), Article 6, 2006, DOI 10.1145/1132956.1132959; Manning, Raghavan & Schütze, *Introduction to Information Retrieval*, CUP 2008, ch. 1–2. (not re-verified this session)

### Inferences
- The system keeps the full schema with example values (OmniSQL DDL) and adds question-matched values from an inverted index. This combines the BRIDGE/CodeS/CHESS value-linking idea with the "no pruning" finding of Maamari et al.
- Exact-token lookup in an inverted index is cheaper than LSH but less tolerant of spelling variants. That trade-off is worth stating in the thesis.

### Gaps
- The details of the CodeS value retriever and the Rajkumar prompt format need checking against the paper bodies.
- No numeric results from CodeS were extracted.
- The Zobel & Moffat details were not re-verified.

---

## 6. Execution-guided decoding, repair, and self-correction

### Takeaway
Running candidate SQL gives an external signal (errors, empty results) that can filter candidates or drive repair:
- Execution-guided decoding (Wang et al. 2018) first used this signal for text-to-SQL.
- LLM-era versions are Self-Debugging, DIN-SQL self-correction, the MAC-SQL Refiner and the CHASE-SQL query fixer.
- Without *external* feedback, LLM self-correction often fails (Huang et al. 2024). That supports repairing only when execution fails or returns empty.

### Cited Findings
**Primary citations (verified)**
- Wang, C., Tatwawadi, K., Brockschmidt, M., Huang, P.-S., Mao, Y., Polozov, O., Singh, R. "Robust Text-to-SQL Generation with Execution-Guided Decoding." arXiv:1807.03100 (2018). https://arxiv.org/abs/1807.03100
- Chen, X., Lin, M., Schärli, N., Zhou, D. "Teaching Large Language Models to Self-Debug." ICLR 2024. arXiv:2304.05128. https://arxiv.org/abs/2304.05128
- Pourreza, M., Rafiei, D. "DIN-SQL: Decomposed In-Context Learning of Text-to-SQL with Self-Correction." NeurIPS 2023. arXiv:2304.11015. https://arxiv.org/abs/2304.11015
- Wang, B., Ren, C., Yang, J., Liang, X., Bai, J., Chai, L., Yan, Z., Zhang, Q.-W., Yin, D., Sun, X., Li, Z. "MAC-SQL: A Multi-Agent Collaborative Framework for Text-to-SQL." COLING 2025 (oral). arXiv:2312.11242. https://arxiv.org/abs/2312.11242
- Huang, J., Chen, X., Mishra, S., Zheng, H. S., Yu, A. W., Song, X., Zhou, D. "Large Language Models Cannot Self-Correct Reasoning Yet." ICLR 2024. arXiv:2310.01798. https://arxiv.org/abs/2310.01798 (author list beyond the first author not re-verified)

**Key facts**
- Execution guidance runs partially generated SQL during decoding and drops candidates that fail or return empty results. It improves several semantic parsers on WikiSQL, ATIS and GeoQuery, reaching 83.8% EX on WikiSQL. — [Wang et al. 2018](https://arxiv.org/abs/1807.03100)
- In Self-Debugging the LLM explains its own code ("rubber-duck debugging") and uses execution feedback, with no human feedback:
  - Spider: +2–3% over baseline, and +9% on the hardest questions
  - TransCoder and MBPP: up to +12%
  - matches or beats baselines that generate more than 10× as many candidates

  — [Chen et al. 2024](https://arxiv.org/abs/2304.05128)
- DIN-SQL's final module is self-correction: the LLM reviews and fixes its SQL with a "generic" or "gentle" prompt. Overall: Spider holdout 85.3 and BIRD holdout 55.9. — [Pourreza & Rafiei 2023](https://arxiv.org/abs/2304.11015)
- MAC-SQL has three agents: Selector (sub-database), Decomposer (main generator) and Refiner. The Refiner fixes SQL using execution errors. MAC-SQL + GPT-4 reaches 59.59 EX on the BIRD holdout vs 46.35 for vanilla GPT-4. Their fine-tuned SQL-Llama (Code Llama 7B) gets 43.94. — [Wang et al. 2025, MAC-SQL](https://arxiv.org/abs/2312.11242)
- In CHASE-SQL (BIRD dev, Gemini 1.5 Pro) the query fixer adds +3.83 to the baseline (57.75 → 61.58) and about +1–2 to each CoT generator. Removing it from the full system costs −3.78 (73.01 → 69.23). — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- In XiYan-SQL each generator is followed by a refiner that fixes errors using execution results or error messages. — [XiYan-SQL](https://arxiv.org/abs/2411.08599)
- Intrinsic self-correction, where the LLM reviews its own answer without external feedback, does not reliably improve reasoning and sometimes makes it worse. — [Huang et al. 2024](https://arxiv.org/abs/2310.01798)

### Inferences
- Triggering repair only on an execution error or an empty result uses the *external* feedback that Huang et al. say is needed. It also avoids "fixing" a correct query, which their results suggest can happen when self-correction is applied to every query.
- Repairing the greedy query serves the same purpose as execution-guided decoding: it removes invalid outputs. It does so at the whole-query level, after generation, rather than during decoding.

### Gaps
- Huang et al.'s numbers (e.g. GSM8K drops after self-correction) were not extracted.

---

## 7. LLM-as-selector, candidate selection, and prompt diversity

### Takeaway
Multi-candidate text-to-SQL systems (MCS-SQL, CHASE-SQL, XiYan-SQL) spend inference compute in two phases:
1. Generate diverse candidates, from multiple prompts or generators.
2. Select among them: majority vote, an LLM multiple-choice pick, a pairwise selector, or a trained selector.

LLM selection beats majority voting when it is tuned or restricted to low-confidence cases. Untuned LLM judges are weak and biased: the pairwise accuracy of an untuned Claude-3.5-Sonnet is about 60%, and judges are position-biased. Prompt diversity raises the oracle upper bound.

### Cited Findings
**Primary citations (verified)**
- Pourreza, M., Li, H., Sun, R., Chung, Y., Talaei, S., Kakkar, G. T., Gan, Y., Saberi, A., Ozcan, F., Arik, S. O. "CHASE-SQL: Multi-Path Reasoning and Preference Optimized Candidate Selection in Text-to-SQL." arXiv:2410.01943 (2024); ICLR 2025 (venue not re-verified this session). https://arxiv.org/abs/2410.01943
- Lee, D., Park, C., Kim, J., Park, H. "MCS-SQL: Leveraging Multiple Prompts and Multiple-Choice Selection For Text-to-SQL Generation." COLING 2025, pp. 337–353. arXiv:2405.07467. https://aclanthology.org/2025.coling-main.24
- Gao, Y., Liu, Y., Li, X., Shi, X., Zhu, Y., Wang, Y., Li, S., Li, W., Hong, Y., Luo, Z., Gao, J., Mou, L., Li, Y. "A Preview of XiYan-SQL: A Multi-Generator Ensemble Framework for Text-to-SQL." arXiv:2411.08599 (2024; v3 Feb 2025). https://arxiv.org/abs/2411.08599
- Li, Y., Lin, Z., Zhang, S., Fu, Q., Chen, B., Lou, J.-G., Chen, W. "Making Large Language Models Better Reasoners with Step-Aware Verifier" (DiVeRSe). ACL 2023 (venue not re-verified this session). arXiv:2206.02336. https://arxiv.org/abs/2206.02336
- Wang, P., Li, L., Chen, L., Cai, Z., Zhu, D., Lin, B., Cao, Y., Liu, Q., Liu, T., Sui, Z. "Large Language Models are not Fair Evaluators." arXiv:2305.17926 (2023). https://arxiv.org/abs/2305.17926
- Zheng, L., Chiang, W.-L., Sheng, Y., Zhuang, S., Wu, Z., Zhuang, Y., Lin, Z., Li, Z., Li, D., Xing, E. P., Zhang, H., Gonzalez, J. E., Stoica, I. "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena." NeurIPS 2023 Datasets & Benchmarks. arXiv:2306.05685. https://arxiv.org/abs/2306.05685

**CHASE-SQL** (BIRD dev; generators Gemini 1.5 Pro / Claude-3.5-Sonnet)
- It has three generators:
  - **Divide-and-conquer CoT**: decompose into sub-questions written as pseudo-SQL, then assemble
  - **Query-plan CoT**: mimics the database engine's EXPLAIN plan
  - **Online synthetic examples**: few-shot examples generated per question
- The selector is a pairwise binary classifier, Gemini-1.5-Flash fine-tuned with LoRA rank 16 for 10 epochs on 3.8K samples.
  - Score: c_f = argmax_{c∈C} Σ_{pairs} θ_p(c_i, c_j | Q, H, D).
  - Each pair is compared in both orders and the winner gets +1.
  - If two candidates' execution results match, the classifier is not called and the first candidate wins.

  — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- Selection results (EX on BIRD dev):

  | Selection method | EX |
  |---|---|
  | Single query | 63.01 |
  | Self-consistency | 68.84 |
  | Ranker agent | 65.51 (worse than SC) |
  | Pairwise selector (full system) | 73.01 |
  | Oracle | 82.79 |

  The selector beats SC by "roughly 6%" when given the same candidates. — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- Per-generator comparison (10 samples each), SC vs selection agent:

  | Generator, temperature | SC | Selector |
  |---|---|---|
  | Query plan, T=0.5 | 65.78 | 71.7 |
  | Query plan, T=1.8 | 65.51 | 71.73 |
  | Divide-and-conquer, T=0.5 | 66.43 | 71.31 |
  | Divide-and-conquer, T=1.8 | 64.41 | 70.53 |
  | Online synthetic, T=0.5 | 67.34 | 70.4 |
  | Online synthetic, T=1.8 | 66.88 | 71.38 |

  — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- Pairwise binary selection accuracy (Table 5):

  | Selector model | Accuracy |
  |---|---|
  | Claude-3.5-Sonnet (untuned) | 60.21% |
  | Gemini-1.5-Pro (untuned) | 63.98% |
  | Tuned Gemma-2 9B | 64.28% |
  | Tuned Gemini-1.5-Flash | 71.01% |

  The text in §3.5 gives 58.01% for untuned Gemini-1.5-Pro, which conflicts with Table 5. — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- Diversity statements: "Low diversity limits improvement potential and reduces the difference between self-consistency and scoring-based approaches." Removing one generator from the full system costs:
  - query plan: −0.65
  - online synthetic: −0.85
  - divide-and-conquer: −1.24

  So each generator adds a modest but positive amount of complementary coverage. — [CHASE-SQL](https://arxiv.org/abs/2410.01943)

**MCS-SQL** (GPT-4, BIRD dev)
- Candidate generation:
  - 5 SQL-generation prompts × 20 samples at T=1.0, up to 100 candidates
  - prompts differ in few-shot selection (question vs masked-question similarity) and ordering
  - schema order is shuffled in the linking prompts
- Filtering: drop candidates with errors or timeouts (180 s), group by execution result, and drop those with confidence < 0.2.
- Selection: the LLM chooses from a multiple-choice list ordered by descending confidence (LLMs favour earlier options), sampled 20 times, then a majority vote over the picks.
- Results:
  - MCS with 1 prompt: 62.1; with 5 prompts: 63.4 (+1.3 from prompt diversity)
  - majority vote 62.8 vs MCS 63.4 (+0.6)
  - MCS *without* confidence filtering: 62.5, worse than majority vote
- Final scores: BIRD 65.5%, Spider 89.6%.

— [MCS-SQL](https://arxiv.org/abs/2405.07467)

**Other selectors and judge biases**
- XiYan-SQL pipeline: schema linking → multiple generators (fine-tuned plus ICL), each followed by a refiner → a selection agent. Reported scores: BIRD dev 75.63% (v2/v3; 72.23% in v1), Spider test 89.65%, SQL-Eval 69.86%, NL2GQL 41.20%. — [XiYan-SQL](https://arxiv.org/abs/2411.08599)
- DiVeRSe uses *diverse prompts* to produce varied reasoning paths, plus a verifier and step-aware voting. GSM8K: 74.4% → 83.2%; state of the art on 6 of 8 reasoning benchmarks. This is the reasoning-domain precedent for "prompt diversity + selection". — [Li et al. 2023](https://arxiv.org/abs/2206.02336)
- LLM judges are sensitive to candidate order. With ChatGPT as judge, simply reordering the candidates made Vicuna-13B beat ChatGPT on 66 of 80 queries. — [Wang et al. 2023](https://arxiv.org/abs/2305.17926)
- GPT-4 as judge agrees with human preferences over 80% of the time, the same level as human–human agreement. The paper also documents position, verbosity and self-enhancement biases (bias list not re-verified this session). — [Zheng et al. 2023](https://arxiv.org/abs/2306.05685)

### Inferences
- Calling the LLM selector *only when there is no majority* follows MCS-SQL's confidence-filtering logic and USC. When a clear majority exists, voting is already reliable, and an untuned selector (pairwise accuracy about 60% in CHASE-SQL) could override correct majorities. When no majority exists, the vote carries little information and the selector's limited accuracy is still better than an arbitrary tie-break.
- The second "query plan" prompt draws 8 samples from a different conditional distribution. This raises oracle coverage (the CHASE-SQL ablation) more cheaply than adding more samples from the same prompt.
- To reduce position bias in the selector, the thesis can cite Wang et al. 2023 and MCS-SQL (ordering by confidence) as the reason for its ordering choice.

### Gaps
- The CHASE-SQL selector is *fine-tuned*. No primary source was found that measures an *untuned* GPT-4o-mini selector on BIRD, so the thesis's own ablation would be the evidence.
- The final venue of CHASE-SQL (ICLR 2025) was not verified this session.

---

## 8. Test-time compute scaling: coverage vs selection

### Takeaway
Drawing more samples raises **coverage** (pass@k / oracle accuracy): the fraction of problems where at least one candidate is correct. Coverage grows roughly log-linearly with the number of samples, but final accuracy is limited by the **selection** method. Majority voting and reward models plateau. Allocating compute per prompt depending on difficulty (Snell et al.) is more efficient than uniform best-of-N.

### Cited Findings
**Primary citations (verified)**
- Brown, B., Juravsky, J., Ehrlich, R., Clark, R., Le, Q. V., Ré, C., Mirhoseini, A. "Large Language Monkeys: Scaling Inference Compute with Repeated Sampling." arXiv:2407.21787 (2024). https://arxiv.org/abs/2407.21787
- Snell, C., Lee, J., Xu, K., Kumar, A. "Scaling LLM Test-Time Compute Optimally can be More Effective than Scaling Model Parameters." arXiv:2408.03314 (2024); ICLR 2025 (venue not re-verified this session). https://arxiv.org/abs/2408.03314

**Key facts**
- Coverage scales with the number of samples over four orders of magnitude, often log-linearly. On SWE-bench Lite, DeepSeek-Coder-V2-Instruct solves 15.9% of issues with 1 sample and 56% with 250 samples, beating the single-sample state of the art of 43%. Gains are largest in domains with automatic verifiers (unit tests, proof checkers). — [Brown et al. 2024](https://arxiv.org/abs/2407.21787)
- The same abstract reports that common ways of picking from a sample collection, such as majority voting and reward models, plateau beyond several hundred samples and do not scale fully with the budget. This was recalled from the abstract and was not in this session's extraction. — [Brown et al. 2024](https://arxiv.org/abs/2407.21787)
- Compute-optimal allocation, which adapts by prompt difficulty and uses PRM-verifier search or iterative revisions, is more than 4× as compute-efficient as best-of-N. In a FLOPs-matched comparison, a smaller model with extra test-time compute beats a 14× larger model on problems where the smaller model already has a non-trivial success rate. — [Snell et al. 2024](https://arxiv.org/abs/2408.03314)
- The coverage/selection gap in text-to-SQL is large. On BIRD dev, CHASE-SQL's oracle is 82.79 vs 68.84 for self-consistency and 73.01 for the best selector. — [CHASE-SQL](https://arxiv.org/abs/2410.01943)
- **Unbiased pass@k estimator** (standard, from Chen et al. 2021, "Evaluating Large Language Models Trained on Code," arXiv:2107.03374): pass@k = E[1 − C(n−c, k)/C(n, k)], for n samples of which c are correct. (not re-verified this session)

### Inferences
- The system's budget is fixed (1 greedy + 16 samples + ≤1 repair + occasional selector call), and the selector is called only on hard (no-majority) cases. This is a simple form of difficulty-adaptive test-time compute in the spirit of Snell et al.
- The thesis should report both oracle coverage (any of the 17 candidates correct) and selected EX, so the coverage–selection gap can be quantified, as in CHASE-SQL.

### Gaps
- Snell et al.'s domain is math (MATH with PaLM 2). The transfer to SQL is an inference, not a finding.
- The Chen et al. 2021 pass@k formula was not re-verified.

---

## 9. Evaluation metric: execution accuracy (EX) on BIRD

### Takeaway
EX counts a prediction as correct when its execution result set equals that of the gold SQL. BIRD uses EX as its main metric, and the BIRD/OmniSQL scorer compares result sets. EX allows different SQL strings to count as correct, but it can produce false positives when two different queries happen to return the same result.

### Cited Findings
- BIRD defines EX as the proportion of examples where the predicted SQL's result set equals the gold SQL's result set, (1/N) Σ 𝟙(V_n = V̂_n). It also proposes the Valid Efficiency Score (VES). Humans achieve 92.96% and ChatGPT 40.08%. The formula comes from the paper body; the headline numbers are verified. — [BIRD](https://arxiv.org/abs/2305.03111)
- Spider (Yu et al. 2018, EMNLP, arXiv:1809.08887) introduced cross-domain text-to-SQL with exact-match and execution metrics. Test-suite accuracy (Zhong, Yu, Klein, EMNLP 2020, arXiv:2010.02840) runs queries on many distilled databases to reduce EX false positives. (not re-verified this session) — https://arxiv.org/abs/1809.08887 ; https://arxiv.org/abs/2010.02840

### Inferences
- Because the system votes over *result sets* and is scored by *result-set* comparison, the voting key and the metric are aligned. That alignment is a theoretical justification for execution-based voting over string voting.

### Gaps
- The exact BIRD EX formula and the OmniSQL evaluation script's timeout and ordering conventions were not fetched here. Project memory says the scorer equals the paper exactly at timeout 60; confirm this from the repo.

---

## 10. Statistical testing: McNemar (exact), bootstrap CIs, multiple comparisons, NLP guidance

### Takeaway
When two systems are evaluated on the *same* test items, the correct comparison is paired. McNemar's test uses only the discordant items (b = A right/B wrong, c = A wrong/B right). The exact version is a two-sided binomial test of b vs c with p = 0.5. Dietterich (1998) showed McNemar is the test with acceptable Type I error when each algorithm can be run only once, which is the situation of a fixed LLM evaluated once on BIRD dev. The paired bootstrap gives confidence intervals for the EX difference. Bonferroni or Holm correction is needed when several system pairs are tested. Dror et al. (2018) is the NLP-specific guide.

### Cited Findings
**Primary citations**
- McNemar, Q. "Note on the sampling error of the difference between correlated proportions or percentages." Psychometrika 12(2):153–157, 1947. DOI 10.1007/BF02295996. https://doi.org/10.1007/BF02295996 (not re-verified this session)
- Dietterich, T. G. "Approximate Statistical Tests for Comparing Supervised Classification Learning Algorithms." Neural Computation 10(7):1895–1923, 1998. DOI 10.1162/089976698300017197. https://web.engr.oregonstate.edu/~tgd/publications/dietterich-approximate-statistical-tests-nc1998.pdf (verified)
- Dror, R., Baumer, G., Shlomov, S., Reichart, R. "The Hitchhiker's Guide to Testing Statistical Significance in Natural Language Processing." ACL 2018 (Long Papers), pp. 1383–1392, Melbourne. DOI 10.18653/v1/P18-1128. https://aclanthology.org/P18-1128/ (verified)
- Efron, B. "Bootstrap Methods: Another Look at the Jackknife." Annals of Statistics 7(1):1–26, 1979. DOI 10.1214/aos/1176344552 (not re-verified). Efron, B., Tibshirani, R. J. *An Introduction to the Bootstrap*. Chapman & Hall, 1993 (not re-verified).
- Paired bootstrap in NLP: Koehn, P. "Statistical Significance Tests for Machine Translation Evaluation." EMNLP 2004, https://aclanthology.org/W04-3250/. Berg-Kirkpatrick, T., Burkett, D., Klein, D. "An Empirical Investigation of Statistical Significance in NLP." EMNLP-CoNLL 2012, https://aclanthology.org/D12-1091/. (not re-verified)
- Multiple comparisons: Dunn, O. J. "Multiple Comparisons Among Means." JASA 56(293):52–64, 1961 (Bonferroni correction). Holm, S. "A Simple Sequentially Rejective Multiple Test Procedure." Scandinavian Journal of Statistics 6(2):65–70, 1979. (not re-verified)

**Definitions and formulas**
- **McNemar's 2×2 table.** For paired predictions of systems A and B on the same N items, let b = #(A correct, B wrong) and c = #(A wrong, B correct). The null hypothesis is that both systems have the same accuracy, which implies P(b-type) = P(c-type).
  - Asymptotic statistic: χ² = (b − c)²/(b + c), or with continuity correction (Edwards 1948) χ² = (|b − c| − 1)²/(b + c), compared against χ²(1).
  - **Exact version:** under H0, b ~ Binomial(n = b + c, 0.5). Two-sided p = min(1, 2·Σ_{i=0}^{min(b,c)} C(n, i)·0.5^n).
  - The exact version is preferred when b + c is small (commonly < 25).

  (standard definitions; McNemar 1947 original; Edwards 1948 Psychometrika 13:185–187 not re-verified) — [McNemar 1947](https://doi.org/10.1007/BF02295996)
- **Dietterich (1998)** compared 5 approximate tests:
  - Two widely used tests, the difference-of-two-proportions test and the paired t-test over several random train/test splits (resampled t-test), have high Type I error in some situations and "should never be used".
  - For algorithms that can be executed only once, McNemar's test is the only test with acceptable Type I error.
  - For algorithms that can be run 10 times, the 5×2cv t-test is recommended: it is slightly more powerful and directly measures training-set variation.

  — [Dietterich 1998](https://web.engr.oregonstate.edu/~tgd/publications/dietterich-approximate-statistical-tests-nc1998.pdf)
- **Dror et al. (2018).** They:
  - review the main concepts of significance testing and the properties of NLP tasks, setups and metrics that determine which test fits
  - propose a simple practical protocol for choosing a test, with a short survey of the relevant tests
  - survey ACL and TACL 2017 empirical papers, finding that significance testing is often ignored or misused even though the field places great weight on empirical results

  — [Dror et al. 2018](https://aclanthology.org/P18-1128/)
- **Paired bootstrap CI** (standard): resample the N test items with replacement B times (e.g. B = 10,000), compute ΔEX = EX_A − EX_B on each resample, and report the 2.5–97.5 percentile interval. Koehn 2004 introduced this for MT. (not re-verified)
- **Bonferroni / Holm.** For m tests, Bonferroni rejects when p_i ≤ α/m, which controls the family-wise error rate. Holm's step-down procedure orders the p-values and rejects while p_(i) ≤ α/(m − i + 1); it is uniformly more powerful than Bonferroni and still controls FWER. (not re-verified)

### Inferences
- For "Ours vs majority-vote baseline" on BIRD dev (N = 1534), the exact McNemar test is appropriate. Both systems are deterministic evaluations on the same items, and the training-split variance that Dietterich's 5×2cv addresses does not apply to a frozen LLM. LLM sampling randomness is a separate source of variance and could be handled by repeated runs or seeds.
- When the thesis tests several ablations against one baseline, apply Holm or Bonferroni. Report the effect (ΔEX in points), b and c, the exact p-value and a bootstrap CI together.

### Gaps
- **Dror et al.'s specific recommendations** (which test for which metric) and **the survey numbers** (how many ACL/TACL 2017 papers used tests) could not be extracted. The ACL Anthology PDF downloaded, but no PDF text extractor was available. Read §3–§5 of the PDF before citing specific recommendations.
- The McNemar 1947, Edwards 1948, Efron 1979, Koehn 2004, Berg-Kirkpatrick 2012, Dunn 1961 and Holm 1979 bibliographic details are from canonical knowledge and were not re-fetched.

---

## 11. Data contamination in LLM evaluation on public benchmarks

### Takeaway
Public benchmarks such as Spider and BIRD may be in LLM training data, which can inflate measured accuracy. Ranaldi et al. (2024) gave direct evidence for text-to-SQL: GPT-3.5 reconstructs masked Spider column names far better than for an unseen dataset (Termite), and its accuracy drops on Termite. BIRD (May 2023) predates GPT-4o-mini's October 2023 knowledge cutoff, so contamination is a validity threat to acknowledge.

### Cited Findings
**Primary citation (verified)**
- Ranaldi, F., Ruzzetti, E. S., Onorati, D., Ranaldi, L., Giannone, C., Favalli, A., Romagnoli, R., Zanzotto, F. M. "Investigating the Impact of Data Contamination of Large Language Models in Text-to-SQL Translation." Findings of ACL 2024, pp. 13909–13920. arXiv:2402.08100. https://aclanthology.org/2024.findings-acl.827 (verified title, venue and pages; full co-author list not re-verified this session)

**Key facts**
- **Detection method.** Mask 25% of column names in each database dump, remove INSERT statements, and ask GPT-3.5 to reconstruct the masked names. DC-accuracy = correctly reconstructed names / number of masked columns. Results:
  - Spider: mean 33.42% (±33.01), range 0–100%
  - Termite (a new, unpublished dataset): mean 13.21% (±18.70), range 0–44.44%

  — [Ranaldi et al. 2024](https://arxiv.org/html/2402.08100v1)
- **Performance gap** (GPT-3.5 test-suite accuracy, Spider vs Termite):

  | Difficulty | Spider | Termite | Gap (points) |
  |---|---|---|---|
  | Easy | 90.11 | 74.00 | 16.11 |
  | Medium | 77.21 | 67.06 | 10.15 |
  | Hard | 48.83 | 28.33 | 20.50 |
  | Extra-hard | 30.94 | 31.14 | −0.20 |

  — [Ranaldi et al. 2024](https://arxiv.org/html/2402.08100v1)
- **Adversarial Table Disconnection** (removing structural cues) hurts Termite more than Spider. On Easy: Spider +0.97 vs Termite −12.00. This suggests the model relies on memorized structure for Spider. — [Ranaldi et al. 2024](https://arxiv.org/html/2402.08100v1)
- The authors conclude that "data contamination is responsible for overestimating the performance of GPT-3.5 on Text-to-SQL". Limitations they state: only GPT-3.5 was tested thoroughly (GPT-4 only in small pilots), and only Spider among public datasets. — [Ranaldi et al. 2024](https://aclanthology.org/2024.findings-acl.827)
- Timeline facts:
  - BIRD was first posted on 4 May 2023. — [BIRD](https://arxiv.org/abs/2305.03111)
  - GPT-4o mini's knowledge cutoff is October 2023. — [OpenAI 2024](https://openai.com/index/gpt-4o-mini-advancing-cost-efficient-intelligence/)
- General contamination references (not re-verified this session):
  - Sainz, O. et al. "NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark." Findings of EMNLP 2023.
  - Golchin, S., Surdeanu, M. "Time Travel in LLMs: Tracing Data Contamination in Large Language Models." ICLR 2024, arXiv:2308.08493.

### Inferences
- The BIRD dev set and its gold SQL have been public since mid-2023, before GPT-4o-mini's cutoff, so absolute EX may be inflated by memorization. *Relative* comparisons (Ours vs baselines using the same model) are less affected, because contamination affects both arms. This is why paired tests (McNemar) on the same model are the stronger evidence.
- Retrieving few-shot examples only from BIRD *train* avoids leaking dev answers through the prompt. It does not address contamination inside the model weights.

### Gaps
- No study was found that directly measures BIRD contamination for GPT-4o-mini. Ranaldi et al. cover Spider and GPT-3.5 only.
- The Sainz et al. and Golchin & Surdeanu details were not re-verified.
