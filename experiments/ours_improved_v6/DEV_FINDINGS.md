# V6 deterministic repairs — development evidence only

Implementation: `postprocess_v6.py`; unit tests: `tests/test_postprocess_v6.py`.
No API/model inference, test question, test prediction or test label was read by this development task. V5 and its frozen source files are unchanged.

## Data and exposure

- Cached canonical V5 candidates: `experiments/ours_improved_v5/runs/deepseek_flash_v5_20261029_r1/tune/records.jsonl` (300 questions) and `audit/records.jsonl` (100 questions).
- Gold inspected exclusively under `baselines/probgate_ehrsql_2024/data/gold/dev/` plus the official train question/SQL pairs.
- Both 300 tune and historical 100 audit questions were inspected during this development. The latter is now **exposed descriptive development**, not an independent validation/audit holdout. Parent selects the policy using tune only and must freeze it before accessing test results.

## Rules implemented

1. **Period-aggregate projection contract.** For a root SELECT that requests one matching aggregate and includes only redundant period GROUP BY keys as other projections, remove those presentation keys when the English question asks a daily/weekly/monthly/yearly aggregate without explicitly requesting date keys. Preserve all grouping, filters, temporal conditions and aggregate expression. Skip DISTINCT/CTE, unrelated output columns, unmatched aggregate, aliases used by ORDER/HAVING, and numeric ORDER BY expressions that could bind to output ordinals. Explicit `by month`, `per day`, `for each year` and equivalent period wording also blocks projection removal. Evidence: all **81** train questions selected by period-aggregate + grouped-SQL criteria have exactly one output column. Two tuning questions and one exposed-audit question had this observable output-shape failure.
2. **Identified first/last organism.** A positive question asking the first/last organism and selecting a single `microbiologyevents.org_name` ordered with LIMIT 1 receives `org_name IS NOT NULL` if no existing NULL predicate exists. The query's other filters/order are preserved. Negative/missing/unknown-organism wording, unrelated tables, other outputs and missing LIMIT/ORDER are excluded. Evidence: **84/84** corresponding train questions have explicit `org_name IS NOT NULL` in gold SQL. This rule deliberately follows the **EHRSQL training-label convention** of finding the first/last identified organism; it is not guaranteed by metadata uniqueness or by universal clinical semantics. One tuning query omitted it and disagreed with the two correct candidates.
3. **Unique physical-code case normalization.** For an ICD literal in a resolved diagnosis/procedure dictionary scope, accept exactly one full stored code matching the full-code spelling or bare suffix case-insensitively. Never cross dictionaries; ambiguous or absent matches remain unchanged. This extends the V5 exact metadata namespace rule for uppercase suffixes such as `Z6838` versus stored `icd10|z6838`. This does not imply the surrounding SQL semantics are correct.

Changed proposals are re-executed read-only through the frozen V4 normalizer. A failed or empty proposal keeps the original V5 prediction. Genuine model nulls, truncation and existing hard issues are not revived. An empty-guard candidate may only be revived when it already satisfies V5's valid-but-empty revival preconditions and an actual unique physical-code repair was made. Every accepted proposal retains `v6_original_record` and `v6_repair` evidence. Generation request hashes remain unchanged.

## Observed development scores, fixed strict-three policy

The numbers below are the **initial pre-review development observation**, not the final selected run. A subsequent code review added conservative guards for positional ORDER BY and explicit period-output wording. The parent marks the initial development run obsolete and reruns development under a new run/protocol hash before locking and evaluating test. Use that new run as the authoritative final score.

- Tune 300: V5 RS10 **96.3333** → enhanced strict-three **97.3333**; correct 289→292, wrong **0→0**, false abstentions 11→8.
- Exposed historical audit 100: V5 RS10 **96.0** → enhanced strict-three **97.0**; correct 96→97, wrong **0→0**, false abstentions 4→3.
- Applied tune proposal changes: **2** period projections + **1** organism NULL filter.
- Applied exposed-audit changes: **1** period projection + **2** unique casefold ICD repairs on candidates belonging to the same BMI question.
- **28 unit tests passed** before parent policy locking, covering guarded scope, unchanged source, query shape, metadata ambiguity, proposal execution failure, null/truncation rejection and actual SQLite examples where dropping an ordinal ORDER BY projection would select a different group.

The casefold repairs on the BMI question yield valid queries but still use per-month COUNT rather than the question's mean of monthly counts. Thus they remain incorrect candidates; strict-three refuses because the plan candidate returns a different result. A two-vote fallback could make this case worse. Parent's policy evaluation must account for this, rather than assuming physical validity is semantic correctness.

These are development observations, not a promise of higher test score, proof of generalization, or a new clinical benchmark. The implementation reads no evaluation labels at runtime. All rules are functions of the question, candidate AST, existing metadata and read-only execution.

## Interface

`enhance_v6(question, candidates, metadata, *, enable_projection=True, enable_organism=True, enable_casefold=True)` returns a new candidate list. `metadata` is the frozen V5 complete metadata object. Existing V5 canonical candidates should be supplied. `compile_v6(...)` is a pure proposal builder exposed for tests. The parent runner owns candidate generation, fixed policy grid, final selection, evaluation and report generation.
