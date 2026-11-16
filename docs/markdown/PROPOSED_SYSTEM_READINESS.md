# Proposed Text-to-SQL system readiness

**Offline implementation verified. Live pilot BLOCKED.** The main profile
is `clinsql_ours_v1` on English CLINSQL, MIMIC-IV v3.1 and BigQuery GoogleSQL.
It uses inference only with the pinned `gpt-5-mini-2025-08-07` configuration.

## Retrieval and data sources

1. **Clinical knowledge.** The catalog loader verifies a versioned, SHA-256
   pinned export bound to the schema. It accepts ICD diagnosis and procedure
   dictionary entries with ICD version and exact code strings, plus lab/ICU
   item metadata from `d_labitems` and `d_items`. Concepts can match dictionary
   labels, abbreviations and supplied aliases with source provenance. Lexical
   matches are candidates. Patient event rows are outside the catalog schema.
   Synthetic coverage is available. An approved real dictionary export and
   sourced aliases remain pending.
2. **Schema.** The authoritative 31-table manifest and pinned lexical index
   supply tables, ranked column hints and declared JOIN paths. The pipeline
   checks database records against the indexed DDL and schema digest. The
   linked candidate uses JOIN closure over declared relationships, and the
   other candidates have full schema context. Composite ICD JOIN validation
   remains active in the main configuration.
3. **Few-shot.** The loader verifies the pinned 145-example development
   corpus and its master manifest. Retrieval filters the current case ID,
   normalized duplicate questions, near duplicates by token overlap and
   sequence similarity with numbers masked, and examples sharing the SQL
   hash of excluded examples. Internal-check and test cases supply no
   examples. Run records label development and internal-check separately.

## Verification, correction and selection

The linker extracts obligations from verbatim question spans. The planner
maps each obligation to an operation. The verifier checks the original
question again and requires actual SQL evidence IDs and used schema references.
The CLINSQL prompts explicitly cover patient/admission/stay grain, cohort and
negation, admission age, event windows and boundaries, aggregation, grouping
and output shape. SQL filters using clinical literals and explicit joins
between base-table columns receive additional deterministic grounding checks.
Verification receives result shape and column types. Result cells stay local.

Three generation strategies feed the SQLGlot validator, then the shared
BigQuery adapter with read-only guard, dataset/table allowlist, dry run,
timeouts and bytes caps. The pipeline logs syntax, schema, SQL execution and
semantic correction reasons. It allows two technical repairs per proposal,
one semantic repair per branch and at most 24 model calls per question.
Authorization, quota, service, timeout and incomplete results terminate
without SQL repair. Complete multi-row results can be selected and saved.
Supported candidates are deduplicated by AST, then selected by grounded
evidence. Result agreement does not establish equivalence.

## Ablation configuration

`ProposedFlags` configures Ours independently. The main configuration
enables schema RAG, multi-layer RAG, SQL validation, correction and
requirement verification. Turn off `multi_layer_rag` for schema-only RAG,
or also turn off `schema_rag` for full-schema prompting without retrieval.
`self_correction` controls both technical and semantic repair.
`requirement_verification` controls verification and semantic selection.
Disabling `sql_validation` also requires disabling verification, which
depends on AST evidence. BigQuery execution safeguards apply in all modes.
`base_prompt_only` uses one generation branch and requires retrieval,
verification and correction off. Flag combinations are included in the
run configuration SHA-256.

## Regression and live pilot

**37 targeted tests passed, 8 deselected.** The selected suite covers catalog
identity, schema/index pins, JOIN and clinical grounding, leakage filtering,
temporal and output obligations through mock verification, GoogleSQL,
correction categories, result completeness, candidate deduplication, ablation
and pilot scope checks. It used synthetic cases and local pinned metadata.

`proposed_runner.run_proposed_pilot_case` requires an Ours-specific approval,
active scope, question/schema/index/catalog and configuration hashes, and
separate persistent API and SQL budgets. It uses the existing reader checks
through the shared BigQuery executor, claims each case once and stores only
the selected complete result under a verified private ACL. The run record
includes retention metadata compatible with the existing expiry helper.

Before live execution, supply the authorized MIMIC dictionary snapshot and
alias provenance, approve evidence transmission, reader scope and budgets,
verify account access to the pinned model, and provision private trace/result
paths with retention enforcement. The paid path has not been exercised.
Near-duplicate filtering is heuristic, AST checks cover supported literal
and explicit JOIN forms, and semantic verification still depends on model
judgment. These limits require validation on independent cases before
reporting effectiveness.
