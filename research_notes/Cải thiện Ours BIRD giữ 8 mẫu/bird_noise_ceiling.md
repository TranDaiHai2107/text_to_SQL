# BIRD dev annotation noise, evaluation artifacts, and the realistic EX ceiling

Scope note: the user evaluates gpt-4o-mini on BIRD dev (dev_20240627, 1534 Q) with OmniSQL's set-equality EX. Audits below differ in which split and version they used. Each finding says which one.

## Q1. Wretblad et al. 2024: how noisy is BIRD dev, and do rankings change on corrected data?

### Takeaway
Wretblad et al. (ACL 2024 Short) audited only parts of BIRD **dev** (pre-2024-06 version; the paper predates dev_20240627). They found noise in 49% of financial-domain items (52/106), with gold SQL wrong in 20.7%. On a 20-question sample per domain, noise ranged from 15% (superhero) to 45% (california_schools). On corrected SQL, the ranking flipped: zero-shot GPT-3.5 beat DIN-SQL and MAC-SQL.

### Cited Findings
- Published at ACL 2024 (Short Papers), arXiv 2402.12243; authors are Wretblad, Gordh Riseby, Biswas, Ahmadi and Holmström. Code and annotations are at github.com/niklaswretblad/the-effects-of-noise-in-text-to-SQL. — [ACL Anthology](https://preview.aclanthology.org/autopr/2024.acl-short.34); [arXiv](https://arxiv.org/abs/2402.12243v4)
- Split: dev only, not train. The primary domain is financial, with 106 question/SQL pairs (about 7.5% of dev). Four validation domains had 20 random questions each. — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4)
- Noise by domain (data points with any noise / noisy question / erroneous gold SQL) — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4):
  - Financial (n=106): 52 (49%) / 44 (41.5%) / 22 (20.7%)
  - California Schools (n=20): 9 (45%) / 5 (25%) / 8 (40%)
  - Superhero (n=20): 3 (15%) / 2 (10%) / 1 (5%)
  - Toxicology (n=20): 7 (35%) / 6 (30%) / 2 (10%)
  - Thrombosis Prediction (n=20): 8 (40%) / 3 (15%) / 6 (30%)
- Noise-type counts in financial (72 errors in total): 23 spelling/syntax, 17 vague/ambiguous question, 22 incorrect SQL, 2 synonyms, 7 string capitalization, 1 question that does not map to the DB. California Schools had 8 incorrect-SQL errors and 4 "does not map to DB". — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4)
- Ranking effect (single run, bar chart only, no exact EX values in the text) — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4); [arXiv abs](https://arxiv.org/abs/2402.12243v4):
  - On the original data, MAC-SQL is slightly ahead.
  - With corrected SQL, MAC-SQL and DIN-SQL tie for last and zero-shot GPT-3.5 beats both.
  - With corrected SQL and questions, all models improve and zero-shot GPT-4 is best.
  - DIN-SQL and MAC-SQL were run only with GPT-3.5.
- Concrete gold errors the paper gives — [arXiv HTML v4](https://arxiv.org/html/2402.12243v4):
  - Q132 joins client and account on district_id, which wrongly links accounts to users in the same district.
  - A one-to-many client–disposition relationship is ignored.
  - Region values ("East", "North") are capitalized in the question but stored lowercase in the DB.
  - "sum" is read as the SQL aggregate instead of a transaction amount (Q177).

### Inferences
- The financial and california_schools domains are the noisiest. If the user's unanimous-wrong items cluster there, that is circumstantial evidence of gold or evidence error.
- The audit used the pre-2024 dev. Some of these items may have been fixed in later dev releases, so the per-domain rates are upper-bound-ish for dev_20240627, not exact.

### Gaps
- No exact EX numbers are available in text form; they are only in Figure 2.
- No item-level mapping to dev_20240627 IDs was verified. The released annotations would need to be cross-checked against the user's split.

## Q2. Other audits, metric studies, and maintainer updates; estimated EX ceiling on BIRD dev

### Takeaway
The strongest evidence is Jin et al. (PVLDB 19(5), 2026, UIUC Kang lab):
- 52.8% of BIRD Mini-Dev items have annotation errors.
- On a 100-question hand-corrected sample of BIRD **Dev**, 48% needed correction.
- On that sample, agent EX changed by −7% to +31% relative, and the ranking correlation with the original set dropped to 0.32.

Arcwise's earlier pass corrected 32.3% of Mini-Dev. FLEX found that EX disagrees with human experts on about 19% of BIRD pairs (21% false positives, 17% false negatives). On corrected data, top systems reach 81–93%, against about 60–75% on the original. So **the noise-imposed ceiling of original BIRD dev EX is plausibly around 75–85%, not 100%**. This is an inference; nobody publishes a single official ceiling.

### Cited Findings
**Jin, Choi, Zhu, Kang, "Pervasive Annotation Errors Break Text-to-SQL Benchmarks and Leaderboards" (arXiv 2601.08778, PVLDB 19(5))**
- Error rates: BIRD Mini-Dev is 52.8% (263 of 498 unique examples; first Mini-Dev release, 500 items with 2 duplicates). Spider 2.0-Snow is 62.8% (76 of 121 items with public gold). — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3); [PVLDB PDF](https://www.vldb.org/pvldb/vol19/p931-jin.pdf)
- The paper does not name a BIRD Dev release such as dev_20240627. It says only that it used the Dev databases. — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3)
- Error taxonomy on erroneous Mini-Dev items (one item can have several patterns) — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3):
  - E1, gold SQL does not match the question's logic: 77 (29.3%)
  - E2, gold SQL mismatches the data or schema: 152 (57.8%)
  - E3, wrong or inconsistent domain knowledge or evidence: 28 (10.7%)
  - E4, ambiguous question or underspecified output format: 78 (29.7%)
- SAR-Agent (their AI reviewer) had 83% precision on Mini-Dev under manual verification. — [ddkang substack](https://ddkang.substack.com/p/pervasive-annotation-errors-break)
- 100-question random BIRD **Dev** sample (62 easy / 28 moderate / 10 challenging) — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3):
  - 48 items needed correction: 19 question, 17 external knowledge (evidence), 41 SQL, 1 schema. Categories overlap.
  - 6 items also needed DB modifications.
- Effect on 16 open agents (original → corrected EX) — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3):
  - CHESS went from 62% to 81% (+30.6% relative). SFT CodeS-15B went from 56% to 52% (−7.1%).
  - Twelve agents improved and four declined.
  - Per agent, an average of 16.4 False→True and 8.0 True→False flips.
- Rank changes reached ±9 places:
  - Rises: MAC-SQL 14→5; CHESS and GenaSQL rose to tie for 1st.
  - Falls: OpenSearch-SQL 2→11, GSR 4→13, Contextual-SQL 1→7.
  - Spearman correlation of the original subset vs full Dev is 0.85; original subset vs corrected subset is 0.32 (p=0.23).
  — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3)
- Frequent concrete error patterns — [arXiv HTML v3](https://arxiv.org/html/2601.08778v3):
  - Missing DISTINCT inside COUNT after a join (5 of 12 CHESS flips: IDs 310, 416, 605, 1286, 1302).
  - Omitted `rtype='S'` filter in california_schools.
  - Owner vs editor confusion in codebase_community.
  - Missing aggregation over multiple budget rows in student_club.
  - Text-typed lap times ordered lexicographically (ID 985).
  - Wrong evidence: "K-12" evidence that excludes kindergarten; an age formula computed as current year minus birth year.
  - Q416 join inflation: gold gives 12.97% vs 47.96% computed per distinct card.

**Arcwise (GitHub issue on BIRD Mini-Dev, Aug 21 2024)**
- Findings — [DAMO-ConvAI issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39):
  - 91 gold-SQL errors (about 18.27%) and 70 more questions (about 14%) that needed fixes for ambiguity or question/SQL inconsistency.
  - In total, 161 of 498 questions changed (32.33%), using minimal edits.
  - Duplicate IDs 137 and 138.
- Top categories: missing COUNT DISTINCT after one-to-many joins (about 5.62%), and output columns that do not match the question (about 8% combined). The second matters because EX compares exact columns. — [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39)
- Arcwise's agent scored about 65% on the original Mini-Dev and about 87% on the corrected one. They released a corrections JSON and a spreadsheet. — [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39)
- The corrected set was later released as Arcwise-Plat-SQL. A second pass by the UIUC/Thinking Machines group raised the detected error rate to 52.8%. — [Thinking Machines post](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/)

**BIRD maintainers**
- Sep 25 2023 cleaned dev (from maintainer accpatrick in issue #39) — [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39):
  - What changed: gold SQL errors fixed, questions with null results revised, DB description columns corrected, two empty tables filled.
  - EX moved from 37.22 to 42.24 for gpt-3.5-turbo and from 46.35 to 49.15 for GPT-4.
- Oct and Nov 2024: maintainers thanked Arcwise and others and said the fixes would be "considered for the next-generation benchmark". They did not commit to patching dev. — [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39)
- No official changelog for dev_20240627 was found. FLEX notes that the 20240627 dev "yields different EX scores than prior studies due to modified ground truth". — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4)
- The mini_dev README still lists "Release cleaner dev.json" and "Release cleaner train.json" as unchecked to-dos. — [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev)
- The BIRD README says the authors spent about 700 hours refining the data but "errors and ambiguities may remain". — [DAMO-ConvAI/bird](https://github.com/AlibabaResearch/DAMO-ConvAI/tree/main/bird)

**FLEX (Kim et al., NAACL 2025, arXiv 2409.19014; used BIRD dev 20240627)**
- Human-labelled sample of 200 BIRD pairs: EX false positives were 21 of 100 non-equivalent pairs (21%), and false negatives were 17 of 100 equivalent pairs (17%). — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4)
- Agreement with human consensus — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4):
  - EX: Cohen's κ 62.0, accuracy 81.0%
  - FLEX (GPT-4o): κ 87.04, accuracy 93.5%
  - Inter-annotator Fleiss κ: 79.32
- Among false negatives of the top-10 BIRD models, 58.13% were "different output structure" and 54.54% "incorrect ground truth" (categories overlap). — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4)
- Example: "who has the highest score" answered as name plus score gets EX=0. Yes/no vs true/false and percent vs fraction formatting are also penalized. — [FLEX ar5iv](https://ar5iv.labs.arxiv.org/html/2409.19014)
- Scores move by +2.6 points on average on BIRD (max rank change 5). Examples (FLEX / EX) — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4):
  - SuperSQL: 64.08 / 57.37
  - CHESS-GPT-4o-mini: 62.71 / 59.13
  - TA-ACL: 59.97 / 55.67

**GBV-SQL (Chen et al., ACL 2026 long, arXiv 2509.12612)**
- Results: 63.23% EX on original BIRD dev, and 90.42% on a "repaired" BIRD dev under manually audited corrections (framed as diagnostic). — [ACL Anthology](https://preview.aclanthology.org/ingest-acl/2026.acl-long.837/); [arXiv](https://arxiv.org/abs/2509.12612)
- Gold-error typology: Type A SQL-side, Type B question-side (ambiguous or unanswerable), Type C database (dirty data). — [arXiv HTML v1](https://arxiv.org/html/2509.12612v1)
- Spider dev: 183 gold-error instances among failed samples and 62 among passed ones. Only 37 failures were genuine model errors. — [arXiv HTML v1](https://arxiv.org/html/2509.12612v1)
- BIRD dev: a 10% stratified sample found gold errors in "over 30%" of items. — [arXiv HTML v1](https://arxiv.org/html/2509.12612v1)

**Train split (for contrast; not dev)**
- A 2.5k-instance BIRD **train** audit found errors in 61.1% of items. Gold SQL was wrong in 52.1%, the question was flawed in 26.2%, evidence was wrong in 18.2%, and 1.5% were unanswerable. An o3 auditor had 90.6% precision but caught only 24.5% of the errors humans flagged. — [Thinking Machines post](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/)
- The BIRD team released bird23-train-filtered (6,601 of 9,428 train examples) on 2025-09-19. — [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev)

**Corrected-data accuracy levels (ceiling evidence)**
- ReViSQL-K2.6 scored 88.55% pass@1, 91.37% greedy with reward changes, and 92.97% SC-16 on Arcwise-Plat-SQL (corrected Mini-Dev). The BIRD human proxy is 92.96%. — [Thinking Machines post](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/)

### Inferences
- **Size of the noise.** Several independent estimates put erroneous or ambiguous items in BIRD dev at about 30–50%:
  - Wretblad: 15–49% per domain
  - GBV: over 30% of a 10% sample
  - Arcwise: 32% of Mini-Dev
  - Jin: 48% of a 100-item Dev sample and 52.8% of Mini-Dev
- **Not all noise costs EX.** Many noisy items still get EX=1, because the model makes the same "mistake" as the gold or the error has no effect on the result. In Jin's sample, the best agent went from 62% to 81% (+19 points) after correction. A rough estimate is that noise caps original-dev EX at around 80% for an otherwise strong system.
- **The user's unanimous-wrong 9%.** When all 8 samples agree on one answer that differs from gold, the item is a prime candidate for gold/evidence error or a convention mismatch. Jin's 41% SQL-correction rate and FLEX's 54.5% "incorrect ground truth" share among top-model false negatives both make it plausible that roughly half or more of these items are not model error.
  - This is an estimate, not measured on gpt-4o-mini.
  - To verify it, hand-label the ~27 tuning items with Jin's E1–E4 categories.
- **Fixed 8-sample budget.** Majority vote or selection cannot recover a unanimous-wrong item unless something changes the generator's convention (for example, the output-column convention). Items where the gold is genuinely wrong are unrecoverable without overfitting.

### Gaps
- No official dev_20240627 changelog was found: neither which IDs changed nor how many.
- Jin et al. do not state the Dev version of their 100-item sample, and they publish no ceiling number.
- GBV-SQL's BIRD repair procedure and size were not visible in the text I accessed (the PDF could not be parsed). The 90.42% figure is therefore not tied to a stated number of repaired items.
- No audit run on gpt-4o-mini itself was found.

## Q3. Frequent gold conventions models "disagree" with, and which a prompt convention can absorb

### Takeaway
The best-documented systematic conventions are output-projection mismatch and DISTINCT handling.
- **Output projection:** the gold returns exactly the asked columns, sometimes extra or fewer. Arcwise puts this at about 8% of Mini-Dev, and FLEX finds it in 58% of top-model false negatives.
- **DISTINCT handling:** COUNT without DISTINCT after one-to-many joins (about 5.6% per Arcwise).
- Also documented: evidence formulas that contradict the question, string-case mismatches, and text-typed numerics.

LIMIT-1 tie-breaking and integer division were **not** quantified by any source I found.

### Cited Findings
- Output columns that differ from the question's request make up about 8% of Mini-Dev questions. EX does exact column matching. — [issue #39 (Arcwise)](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39)
- "Different output structure" accounts for 58.13% of false negatives for top-10 BIRD models, including extra columns such as returning the score alongside the name. — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4); [FLEX ar5iv](https://ar5iv.labs.arxiv.org/html/2409.19014)
- Missing COUNT DISTINCT after a one-to-many join covers about 5.62% of Mini-Dev questions per Arcwise, and 5 of 12 CHESS flips per Jin. — [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39); [Jin et al.](https://arxiv.org/html/2601.08778v3)
- Evidence or domain-knowledge errors: 17 of 100 Dev items needed evidence fixes, and E3 covers 10.7% of erroneous Mini-Dev items. Examples include the K-12 definition and the age formula. — [Jin et al.](https://arxiv.org/html/2601.08778v3)
- String capitalization mismatches between question and DB values: 7 of 72 financial-domain errors. — [Wretblad et al.](https://arxiv.org/html/2402.12243v4)
- Value representation (percent vs fraction, yes/no vs 1/0) is a separate FLEX false-negative category; rounding falls under it. Ties are discussed only in FLEX case studies (Table 18), with no count. — [FLEX arXiv v4](https://arxiv.org/html/2409.19014v4); [FLEX ar5iv](https://ar5iv.labs.arxiv.org/html/2409.19014)
- An ACL 2026 evaluation paper cites a structural audit reporting EX false negatives of up to 28.9% from non-canonical but correct queries, including projection order and value formatting. — [ACL 2026 long.257](https://aclanthology.org/2026.acl-long.257.pdf)
- About 41% of sampled Dev items needed SQL correction (Jin). Prompt conventions cannot fix those. — [Jin et al.](https://arxiv.org/html/2601.08778v3)

### Inferences
Which conventions a prompt can plausibly absorb without overfitting:

- **Plausibly absorbable, low overfitting risk:** these are generic rules, not ID-specific.
  - (a) "Return only the columns the question asks for, in the order mentioned; do not add helper or ordering columns." This targets the largest false-negative class.
  - (b) "Follow the evidence formula literally even if it seems odd." BIRD gold usually follows the evidence. Jin shows the evidence itself is sometimes wrong, but the gold usually agrees with the wrong evidence, so EX rewards following it.
  - (c) Match string literals to the DB's stored casing via value retrieval or sampling.
  - (d) CAST to REAL for ratios and percentages. This mirrors common BIRD gold style; it is an inference, since no count of integer-division mismatches was found.
- **Not safely absorbable:**
  - COUNT vs COUNT DISTINCT. The gold is inconsistent: sometimes it is missing DISTINCT where it is needed (an error), so a blanket rule helps on some items and hurts on others.
  - LIMIT 1 vs ties: no data on which way the gold leans.
  - Genuinely wrong gold joins or logic (E1/E2). Fitting these is overfitting to noise.
- **Evaluator detail to check.** The OmniSQL/BIRD-style set equality ignores row order and duplicates but is sensitive to the number and order of columns within rows. This is from knowledge of the standard BIRD evaluator, not from the sources above. So projection conventions matter more than ORDER BY conventions.

### Gaps
- No source quantifies LIMIT-1-with-ties or integer-division mismatches on BIRD dev.
- No study measured how much EX a projection-convention prompt alone recovers on BIRD dev.

## Q4. 2025–2026 corrected BIRD dev versions or re-annotations

### Takeaway
As of late 2026, no official fully corrected BIRD dev.json exists; "Release cleaner dev.json" is still an open to-do. What exists:
- Corrected **Mini-Dev** subsets: Arcwise-Plat-SQL, and the 2026-10-28 official Mini-Dev annotation fix.
- Jin et al.'s 100-item corrected Dev sample.
- GBV-SQL's "repaired" BIRD dev, used diagnostically.
- On the train side, the filtered BIRD train subset and BIRD-Platinum.

### Cited Findings
- Official Mini-Dev updates — [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev):
  - 2025-07-04: data moved to Hugging Face, now the canonical version.
  - 2025-07-22: Mini-Dev V2 with 780 instances (500 SELECT-only from BIRD-Dev plus 270 new across 18 new DBs).
  - 2026-10-28: annotations corrected and selected instances replaced across SQLite, MySQL and PostgreSQL, based on community feedback and human review.
  - The README still lists "Release cleaner dev.json" as unchecked.
- Arcwise-Plat-SQL: corrected Mini-Dev (498 unique items) as the evaluation set. Corrections JSON in issue #39. — [Thinking Machines](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/); [issue #39](https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39)
- Jin et al. corrected a 100-item Dev sample and Mini-Dev (code and data at github.com/uiuc-kang-lab/text_to_sql_benchmarks). — [arXiv abs](https://arxiv.org/abs/2601.08778); [ddkang substack](https://ddkang.substack.com/p/pervasive-annotation-errors-break)
- GBV-SQL's repaired BIRD dev: 90.42% EX vs 63.23% on the original. — [ACL Anthology](https://preview.aclanthology.org/ingest-acl/2026.acl-long.837/)
- Train-side cleanups:
  - bird23-train-filtered: 6,601 of 9,428 examples, 2025-09-19. — [bird-bench/mini_dev](https://github.com/bird-bench/mini_dev)
  - BIRD-Platinum: 2.5k audited train items. — [Thinking Machines](https://thinkingmachines.ai/news/putting-task-expertise-into-rl/)

### Inferences
- A thesis can cite Jin et al.'s 100-item Dev numbers (48% needed correction; best-agent EX 62→81) as the most direct dev-set evidence. dev_20240627 is still the de facto evaluation file, with known residual noise.
- If dev_20240627 IDs overlap with Mini-Dev, the Arcwise and Jin corrections can be mapped onto the user's tuning split. Mini-Dev was drawn from BIRD-Dev, so the overlap is likely, but the IDs need checking. That would let the user label unanimous-wrong items as gold error vs model error with external evidence instead of their own judgment.

### Gaps
- No official dev_20240627 diff or count of changed items was found.
- How many of the 1534 dev_20240627 items are covered by Mini-Dev corrections was not verified.
- The repair size and procedure for GBV-SQL's repaired dev were not accessible.
