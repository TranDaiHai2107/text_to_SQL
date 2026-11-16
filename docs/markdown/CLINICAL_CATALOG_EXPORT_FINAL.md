# Clinical catalog export status

**PASS · 15 November 2026 (UTC+7).** All four reader jobs finished. Their
results were recovered by job ID after fixing the loader to preserve NULL
and blank labels. Recovery verified SQL, status, billed bytes, and row
completeness without submitting a new query.

- `d_icd_diagnoses` · 112,107 rows.
- `d_icd_procedures` · 86,423 rows.
- `d_labitems` · 1,650 rows, including five without searchable labels.
- `d_items` · 4,095 rows.

Total 204,275 rows. SHA-256
`3fabb16dfc04a09e58fbbb752eaa17e5d1c8a4b8eff96cda98f6a6ac7016b5fc`.
The restricted receipt records 41,943,040 billed bytes and retention through
22 November 2026 at 00:11:47 UTC+7. Rows without searchable labels or aliases
stay in the export and are skipped by lexical retrieval. Ours pins the digest.

## Prior status

Scope A is approved conditionally in the [combined decision](TASK8_COMBINED_APPROVAL.md).
The production catalog still has no export receipt, row counts or digest.

Task 7 approved the shared financial envelope. The operator approved
dictionary-only reader execution and restricted storage within policy.
The Task 8 policy reference is still a placeholder, so no export approval
was activated. The real export has zero jobs and no catalog SHA-256.

**BLOCKED before real export.** The four SELECT projections and loader
were verified offline. The open prerequisite is the actual policy reference
covering export and local storage under `results/restricted`. Scope B for
Ours also requires coverage for the approved dictionary fields sent to GPT-5-mini.

| Table | Production row count |
|---|---|
| d_icd_diagnoses | Pending export |
| d_icd_procedures | Pending export |
| d_labitems | Pending export |
| d_items | Pending export |

Schema manifest SHA-256
`46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`.
Planned provenance is the reader-accessible MIMIC-IV v3.1 BigQuery dictionaries
in `kltn-text-to-sql`. Real catalog SHA-256 and completeness are pending.
The exporter checks field order, types and dictionary identity, preserves
leading zeroes, checks full result delivery and writes a receipt with counts,
job IDs, billed bytes and SHA-256. The Ours approval will pin this digest.
