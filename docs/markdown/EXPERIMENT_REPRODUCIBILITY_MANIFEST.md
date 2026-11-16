# CLINSQL experiment reproducibility — pre-freeze record 14/11/2026

**Status: PRE_FREEZE; not an official test configuration.** Pinned evidence:

Phase C.2 checkpoint: `results/restricted/phase_c2_state.sqlite` imports the
five verified Phase C.1 case/artifact SHA pairs exactly once; rerunning the
checkpoint command was idempotent. `results/phase_c2_status.json` records
`OFFICIAL_SCORING=BLOCKED_RESULT_TRANSFER_NOT_APPROVED` after the user's
explicit no-transfer decision, while `TEST_443=SEALED_NOT_STARTED`.
Selected offline regression: **100/100 PASS**. These facts do not freeze the
remaining method configurations.

- CLINSQL source commit `1d819960eb3ce3ac0e9beb4e801810a05735fd58`;
  MAC-SQL `31a9df5e0d520be4769be57a4b9022e5e34a14f4`;
  SDE-SQL `e425408fcb13d69b0bd15f917b819591805a8973`.
  `PAPER_SOURCE_LOCK.json` includes key-file SHA-256 hashes; source files were
  not edited. `paper_sources.py` verifies them.
- BigQuery MIMIC-IV v3.1: project `kltn-text-to-sql`, HOSP
  `mimiciv_3_1_hosp`, ICU `mimiciv_3_1_icu`, location US, 31-table schema
  SHA-256 `46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`.
  Schema RAG index SHA-256
  `89ff2c2f8169c8b65c58821174545231854b374904ebaedd579977973710b318`.
- Model snapshot `gpt-5-mini-2025-08-07`, medium reasoning for completed
  CLINSQL pilot. Their runtime-code SHA-256 is
  `52f98b21a7dd86beea243f7bfa5dfb85a94fe5f81bd6a4a2a0607e7a63042818`.
  Two pilot SQL budget hashes/approvals are disclosed in
  `results/phase_c1_pilot_audit.json`; no result was silently overwritten.
- Master question-only validation split manifest:
  `data/clinsql/master_experiment_pre_freeze_v1.json`, SHA-256
  `fd28d344e6fe0c118a75554abcdb6d631f33b6ebb4e06262c59b6cf71e718173`.
  It has 152 development/38 internal-check and five pinned pilot IDs; test
  remains sealed. Frozen Ours development few-shot corpus SHA-256
  `5533495dbc6547409aaa4138c96d532f6377c5f98447e6c766a3aab51262c93a`,
  145 examples after five pilot and two unsupported-derived exclusions.

Not yet frozen: MAC/SDE/Ours live runner code, ICD index, all method prompt
hashes, SDE transport live behavior, official Azure judge/model configuration,
BigQuery full-experiment budgets, failure accounting and test question hash.
No full validation or official test is authorized by this manifest.
