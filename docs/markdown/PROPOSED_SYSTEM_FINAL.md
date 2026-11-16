# Proposed System (Ours) — Phase C.2 status, 14/11/2026

**Status: NOT_FINAL / LIVE_PILOT_BLOCKED.** The English CLINSQL mock pipeline
connects Schema RAG, optional ICD dictionary and few-shot retrieval, SQL
generation, SQLGlot/BigQuery validation and agentic correction. It retains
the existing Vietnamese application code without migrating that app now.
No Ours GPT-5-mini or MIMIC BigQuery SQL has run.

Schema retrieval uses the 31-table authoritative BigQuery manifest SHA-256
`46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`
and Schema RAG index SHA-256
`89ff2c2f8169c8b65c58821174545231854b374904ebaedd579977973710b318`.
The development-only few-shot corpus is frozen at
`data/clinsql/retrieval/fewshot_development_v1.json`, SHA-256
`5533495dbc6547409aaa4138c96d532f6377c5f98447e6c766a3aab51262c93a`.
The runtime loader now rejects a self-consistent corpus with a different
SHA-256; the pinned version must be updated explicitly to change examples.
It contains 145 public validation-development question/SQL examples, with
pilot 5 and internal-check 38 excluded. Only the two HOSP/ICU project literals
in example SQL are rebound to the verified BigQuery project. Two further
development examples were excluded because their official SQL references
`mimiciv_3_1_derived`, absent from the verified 31-table backend:
`Disease_Diagnosis_and_Outcomes/medium_level_queries/029` and `/043`.
No test SQL/result/rubric was read to build this corpus. Retrieval excludes
exact normalized question text and source ID; near-duplicate/answer-equivalent
leakage analysis remains to be completed before internal-check/test.

The real MIMIC ICD dictionary has **not** been loaded. Existing
`ApprovedICDCatalog` accepts only dictionary tables, and no patient rows are
permitted in model prompts, but there is no approved read or frozen ICD index
yet. `PipelineDatabase.catalog_search` returns no values by design. The
proposed method therefore has a working mock architecture, not the intended
full RAG configuration. A real runner still needs the same approval-aware
BigQuery executor, persistent budget/checkpoint, restricted result artifact
and GPT-5-mini transport used in CLINSQL CoT. It must not reuse Phase C.1
approval or MIMIC Mini/PostgreSQL.

**Next gate:** validate allowed dictionary source and handling, build/lock ICD
index, complete development-only retrieval overlap audit, connect live runner
with the shared BigQuery controls, and run the same five validation cases
under a method-scoped budget. No superiority claim is possible yet.
