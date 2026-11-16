# CLINSQL GPT-5-mini live validation pilot — 14/11/2026

**Technical execution: PASS, 5/5 pinned validation-development cases.** Five
generated SQL predictions were executed on BigQuery MIMIC-IV v3.1 and their
complete results were stored as restricted artifacts. This is an infrastructure
pilot of **CLINSQL CoT + Self-Refinement only**. The official CLINSQL SQL Score,
Execution Score and LLM judge are **NOT RUN**. Execution success does not imply
answer correctness or superiority over any baseline.

The audit in `results/phase_c1_pilot_audit.json` verifies the five saved logs,
artifact hashes, row counts, complete flags, job IDs, private Windows ACL,
identical model/schema/index/runtime-code/API-budget fingerprints, and absence
of raw result rows in application logs. The executed cases span approved v4
and v5 run directories. The SQL budget hash differs: v4 used the original
256 MiB per SQL cap for two small queries; v5 used the separately approved
16 GiB per SQL, 160 GiB aggregate cap for the other three. The persistent SQL
ledger spans versions and shows five reconciled jobs, zero pending reservations.
The v4 Medication `BUDGET_EXCEEDED` calibration log is explicitly excluded from
the five complete predictions.

## Five complete predictions

- `Diagnostic_Procedures/easy_level_queries/058`: one API call; one result row;
  BigQuery job `0e124c1a-4552-442a-bcc0-d3b9eb1efcac`; 44,040,192 billed
  bytes; estimated API USD 0.00621525; end-to-end 27.734 seconds.
- `Vital_Signs_Monitoring/easy_level_queries/044`: one API call; one result
  row; job `e50c9005-7901-4aed-b3de-be8e7b4871d8`; 11,761,876,992 billed
  bytes; estimated API USD 0.00522925; 32.625 seconds.
- `Laboratory_Results_Analysis/medium_level_queries/079`: one API call; one
  result row; job `e5d8b375-cfb5-43e2-a919-b4fd7143a7b3`; 5,212,471,296
  billed bytes; estimated API USD 0.008163; 49.688 seconds.
- `Medication_Management/medium_level_queries/012`: two API calls, including
  native self-refinement after an SQL error; one result row; job
  `f2793279-ab7e-44aa-8da1-5c060d47f966`; 2,854,223,872 billed bytes;
  estimated API USD 0.02185525; 115.719 seconds.
- `Patient_Demographics_and_Admissions/hard_level_queries/058`: one API call;
  two result rows; job `d278ae1b-0862-48f6-b0be-f5d6549c2033`;
  208,666,624 billed bytes; estimated API USD 0.00706625; 35.953 seconds.

Across these **five complete predictions**, there were six API calls, 24,660
input tokens, 21,182 output tokens (11,648 reasoning tokens), and estimated
inference API cost **USD 0.048529**. The five BigQuery jobs billed
**20,081,278,976 bytes (18.702 GiB)**, approximately **USD 0.114149** using the
budget's USD 6.25/TiB on-demand assumption. Combined estimated inference and
SQL cost is about **USD 0.162678**; evaluation cost is zero because no judge
ran. This is a price-based estimate, not an invoice; free tier, billing plan,
cache and tax can change actual charges. Summed end-to-end latency is 261.719
seconds, mean 52.344 seconds per complete case. Each case's measured latency
includes model generation, validation/dry run, BigQuery execution and storage;
it does not include earlier calibration attempts.

## Calibration and exclusions

Earlier versioned attempts remain in their original logs and are **not**
scored as five additional predictions:

- v1 Diagnostic: Responses returned `incomplete` at the source's 2048 output
  token cap. One known request cost estimate: USD 0.00502825; no patient SQL.
- v2 Diagnostic: transport outcome unknown. Its full 11,016 input / 8192
  output token reservation remains pending, conservatively USD 0.019138;
  this is **not a claim of actual API billing**. No automatic retry or SQL.
- v2 Vital: SQL Guard rejected an unapproved `physionet-data` catalog before
  BigQuery execution. One known API request: USD 0.00562225.
- v3 Diagnostic and Vital: three and two known API calls, respectively,
  estimated USD 0.021507 and USD 0.01319075. Catalog/refinement and the
  256 MiB SQL cap prevented patient execution.
- v4 Medication: one known API call, estimated USD 0.009556; dry-run cost
  exceeded the v4 cap, so no patient execution for that attempt.

Known **calibration** API estimates total USD 0.05490425, separate from the
five complete predictions. All known clinical calls across calibration and
complete predictions total estimated USD 0.10343325. The v2 unknown request's
conservative reservation is additional and unresolved; two nonclinical access
probes, estimated USD 0.00075725, are also separate. These amounts must remain
visible in any research cost accounting. No calibration result is silently
counted as a scored case. No gold SQL, reference result or test rubric was
sent to GPT-5-mini during inference.

## Integrity and next gate

The model snapshot is `gpt-5-mini-2025-08-07`; manifest SHA-256 is
`46a816c289178f5b69470fef4cf335f1ff556ad1f4d40b83d600517d76a0ab5d`;
Schema RAG index SHA-256 is
`89ff2c2f8169c8b65c58821174545231854b374904ebaedd579977973710b318`.
The successful runs share runtime-code SHA-256
`52f98b21a7dd86beea243f7bfa5dfb85a94fe5f81bd6a4a2a0607e7a63042818`.
The source prompt's two dataset-project literals were adapted to the verified
project without editing paper source or gold data; see `BASELINE_ADAPTATION.md`.
Reader ADC, SQL Guard, allowlist, dry run, 120-second SQL timeout and
seven-day restricted result retention remained active. IAM remains
`READ_ONLY_LIKELY_WITH_APPROVED_RISK`, not `VERIFIED_READ_ONLY`.

Retention inspection shows all five artifacts `NOT_DUE`, with expiry between
20/11/2026 18:52 UTC and 21/11/2026 00:56 UTC. Deletion is **manual** via
`python run.py phase-c1-pilot retention --delete-expired` when due; there is no
background deletion task. The restricted artifacts contain MIMIC query
results, while application logs contain only SQL, metadata and job details.

Offline regression: **83/83 selected tests PASS** using system Python;
`paper_sources.py` confirms all three locked source checkouts. The separate
CLINSQL paper virtual environment does not contain pytest, so tests were run
with the existing system installation; this does not affect the pilot runtime.

**Full benchmark gate remains closed.** MAC-SQL and SDE-SQL still have documented
fidelity/data-policy gaps; Ours lacks locked real ICD/few-shot corpora; shared
real runners, evaluator parity, cost budgets and a frozen test protocol remain
to be completed. The Phase C.1 approval covers only these five CLINSQL cases,
not 152 development cases, 38 internal-check cases, 443 test cases, other
methods, SQL probes or the official judge. No further paid run follows from
this technical PASS.
