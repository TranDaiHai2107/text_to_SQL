# Task 8 combined approval decision

The [final user attestation](../attestations/1adf22675348932e8022047cfd42352e20eb4d431ace6f4e9bee4e1c8d750492.json)
supersedes the earlier choices below. It records
`USER_ATTESTATION` and `USER_CONFIRMED_NOT_INDEPENDENTLY_VERIFIED`, selects
MAC-SQL `column_samples`, accepts scoped inherited IAM risk, and sets the
pilot approval deadline to 22 November 2026 at 23:59:59 UTC+7.

On 15 November, the research lead confirmed the credit balance and SKU
price were unchanged and requested an extension. Both evidence deadlines
are now **16 November 2026 at 09:00 UTC+7**. The refreshed evidence SHA-256
is `eca28faef400f5233fa2064c35f3db968006a47fc39887b164831b7bb225fd97`.
The MAC-SQL, SDE-SQL and Ours records pin this revision. The shared
ledger retains the four prior catalog jobs and their 41,943,040 billed
bytes, along with the previous and new credit pins. Ours pins the verified
catalog digest documented in the [catalog report](CLINICAL_CATALOG_EXPORT_FINAL.md).

## Earlier decision package

- **A. Local catalog.** Permit reader-only export of `d_icd_diagnoses`,
  `d_icd_procedures`, `d_labitems` and `d_items` metadata into restricted
  storage. The export step sends nothing to GPT-5-mini.
- **B. Ours dictionary transmission.** Permit retrieved catalog labels,
  exact ICD codes and versions, itemids, source table, units, and other
  approved dictionary fields to GPT-5-mini. This is separate from A.
- **C. MAC-SQL.** Selected `metadata_only`, labeled
  `MAC_SQL_RESTRICTED_ADAPTATION`. Its Refiner requires row-presence and
  NULL feedback to be covered by the referenced policy, alongside English
  questions, schema, generated SQL and sanitized errors. Patient-derived
  `column_samples` are outside this approval.
- **D. SDE-SQL.** Permit English questions, schema, generated SQL,
  sanitized errors, probe labels and result column names. Approve
  `grouped_3x3` with label `SDE_GROUPED_3X3_REQUEST_ADAPTATION`.
- **E. Ours.** Permit English questions, schema, dictionary evidence per B,
  sanitized SQL errors, result column names/types, shape and row counts.
  The frozen development demonstrations remain subject to their pinned
  retrieval scope. The runner also uses its own generated SQL in repair
  prompts. Confirm the policy reference covers that use.
- **F. Execution.** Approve the following maximum limits and the five
  cases below. Use restricted local storage for patient result cells,
  result artifacts and diagnostic traces. Retain artifacts for seven days
  after each case, with deletion through the retention command. Azure
  judge and raw patient result cells are outside the API scope.

| Scope | SQL jobs/case | Probes/case | Per SQL / case / method (GiB) | API requests, five cases |
|---|---:|---:|---|---:|
| Catalog, once | 4 | 0 | 16 / 64 / 64 | 0 |
| MAC metadata-only | 4 | 0 | 64 / 256 / 1,024 | 25 |
| SDE grouped | 141 | 128 | 64 / 1,024 / 4,096 | 130 |
| Ours | 18 | 0 | 64 / 768 / 3,072 | 120 |

All queries retain the 120-second timeout, dynamic dry-run caps and the
shared credit ceiling. SDE probe count depends on generated groups and
native diagnosis. If it exceeds the proposed capacity, record a resource
block without clipping probes. The JSON defines exact token, row and
result-byte limits. The November API policy has no USD hard cap within
these request/token limits. At configured rates the gross BigQuery job-cap
sum is approximately 1.30M VND before free tier.

The approved package defines a window ending **15/11/2026 00:00
Asia/Bangkok (14/11 17:00 UTC)**, or earlier revocation, insufficient credit
or expiry of price evidence. Continued execution requires refreshed credit
and pricing evidence if that window closes.

The five locked cases are:

- `Diagnostic_Procedures/easy_level_queries/058`
- `Vital_Signs_Monitoring/easy_level_queries/044`
- `Laboratory_Results_Analysis/medium_level_queries/079`
- `Medication_Management/medium_level_queries/012`
- `Patient_Demographics_and_Admissions/hard_level_queries/058`

Scope pins are reader `kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com`,
project/billing project `kltn-text-to-sql`, US, datasets
`mimiciv_3_1_hosp` and `mimiciv_3_1_icu`, and model
`gpt-5-mini-2025-08-07`. Budget, schema, pilot and implementation hashes
will be recorded on the approved method records. Ours' configuration hash
will bind the actual catalog digest after export.

Offline plans verified `catalog_export/local_dictionary`,
`mac_sql/metadata_only` and `sde_sql/grouped_3x3`. The saved SDE synthetic
transport evidence still matches the code pin. The credit envelope was active
during the offline check, and the restricted storage and pilot directory ACLs
both passed. The final Ours configuration
hash depends on the verified catalog digest. Once the actual reference is
available, bind the four method-scoped records to that reference, the
agreed scope, the live window and the relevant hashes.
