# Three-method live pilot results

## Task 8 continuation · 15 November 2026

| Method | Completed with full result | Recorded execution outcomes | GPT-5-mini requests | BigQuery query jobs | Billed bytes | Rubric staging |
|---|---:|---|---:|---:|---:|---|
| CLINSQL CoT | 5/5 | 5 executed | 6 | 5 | 20,081,278,976 | 5 staged locally |
| SDE-SQL | 5/5 | 5 executed after probe correction | 36 | 122 | 275,476,643,840 | 5 staged locally |
| MAC-SQL | 0/5 | Local attempt stopped in column sampling | 0 | 27 | 679,477,248 | No final artifacts |
| Ours | 0/5 | 5 local attempts ended before generating final SQL | 0 | 0 | 0 | No final artifacts |

Historical counts include real pilot attempts and exclude dry runs, catalog
export and synthetic transport requests. MAC-SQL's `emar.charttime` sample
hit the one-million-row transfer limit. Sampling now computes the same
frequency order and NULL evidence in BigQuery and returns at most two
temporal rows, seven string or Boolean rows, or eleven numeric rows.
The string query checks every distinct value for the existing exclusion
rules before returning examples. Reader dry runs passed for representative
column types, including `emar.charttime`. Final SQL still uses the complete
paginated result contract.

The OpenAI Platform browser tab requested sign-in, so the exact API
project's Data Controls could not be verified. MAC-SQL `column_samples` and
Ours `dictionary_rag` are pending that verification for GPT-5-mini.

**SDE-SQL probe continuation · 5/5 `EXECUTED`.** Diagnostic Procedures
Easy/058, Vital Signs Easy/044, Laboratory Results Medium/079, Medication
Management Medium/012 and Patient Demographics Hard/058 each have a final
SQL and a verified complete one-row artifact. The restricted continuation
directory contains the five run records and `state.sqlite`.

The continuation used 30 GPT-5-mini requests and 121 BigQuery query jobs,
with 275,463,012,352 bytes billed. Including the earlier SDE clinical
attempts, the ledgers record 36 API requests and 122 query jobs, with
275,476,643,840 bytes billed and no pending reservations. Synthetic usage
and dry runs are excluded. Targeted regression passed 76 tests.

The Task 8 SDE-SQL pilot sent the generated probe SQL together with its
row-presence labels (`NULL` or `Not NULL`). Its target judge received the
selected SQL and result column names. The saved prompt hashes match this
reconstruction. Candidate result rows used for selection stayed local.
The local debug variants of MAC-SQL `column_samples` and Ours used
Qwen2.5-Coder-3B-Instruct Q4_K_M through `llama.cpp` bound to `127.0.0.1`.
The local model hash begins `724fb256bec1`. These runs use different models,
so they do not support a controlled same-model comparison.

In the first GPT-5-mini run, five SDE exploration requests each exhausted
the 4,096-token cap. The API ledger recorded 34,163 input and 20,480 output
tokens. No SQL was produced by that run. The follow-up omits the Chat
Completions token cap and uses the remaining 125 requests from the original
130-request budget. The previous run and its accounting remain available.
Three separate synthetic requests verified grouped `n=3` without a request
token cap.

The first uncapped run stopped during `sde.explore1` on job
`clinsql_4e071c2a7c504163b93b7724b13914d9`. BigQuery US reported `DONE`,
287,504 result rows, 13,177,999 bytes processed and 13,631,488 bytes billed.
The job grouped `procedures_icd` by `hadm_id` and counted distinct ICD codes.
The runner transferred only 100,000 rows and correctly marked that payload
incomplete. SDE exploration and diagnosis consume only empty/nonempty
feedback. The corrected path reads the completed job's `total_rows`
without iterating cells and keeps the original SQL. Candidate selection and
final execution still require all values within the existing resource caps.

The original checkpoint contained one probe SQL and job ID, but omitted the
full exploration response because the request used `store=false`. The
continuation verified the saved job against the original reservation and
reconstructed the missing group with one GPT-5-mini call. The new group
contained different SQL, so the old job was not substituted for a different
probe. Validated group responses are now saved in restricted storage and
bound to the full prompt hash before starting their SQL jobs.

The method-scoped records validated with the final user attestation. Catalog
export passed. MAC-SQL `column_samples`, SDE-SQL `grouped_3x3` and Ours
`dictionary_rag` each remain at 0/5. The OpenAI project's retention and
review controls have yet to be verified. No clinical inference calls or new
case checkpoints were created. Targeted regression passed 63 tests.

## Prior status

Task 8 recorded the [combined decision](TASK8_COMBINED_APPROVAL.md).
Activation is blocked by the missing policy or authorization reference.
Clinical outcomes remain MAC-SQL 0/5, SDE-SQL 0/5 and Ours 0/5.

**Task 7 clinical progress:** MAC-SQL 0/5, SDE-SQL 0/5, Ours 0/5.
The financial budget is approved. There were zero clinical API requests
and zero BigQuery jobs or billed bytes in Task 7. The separate synthetic
transport check used four requests, one rejected before generation and
three successful, with 69 input / 1,004 output tokens and estimated
$0.00202525 for confirmed generation.

Task 7 targeted offline regression: **58 passed**.

The shared runner uses dry-run-based SQL caps and a durable experiment
credit ledger. Task 8 decision processing submitted zero BigQuery jobs and
zero API calls. No method checkpoints advanced.

| Method | Live cases | Workflow status | API calls / SQL jobs |
|---|---:|---|---|
| MAC-SQL | 0/5 | `metadata_only` selected. Evidence reference pending, including row-presence/NULL feedback. | 0 / 0 |
| SDE-SQL | 0/5 | `grouped_3x3` selected and existing synthetic evidence revalidated. Clinical probe disclosure reference pending. | 0 / 0 |
| Ours | 0/5 | Dictionary and result-shape scope selected. Evidence reference and actual catalog digest pending. | 0 / 0 |

There is no new final SQL, result artifact or patient-case latency for these
methods. The five CoT predictions remain saved from the prior phase.
Synthetic API usage is recorded in [PILOT_API_BIGQUERY_USAGE.md](PILOT_API_BIGQUERY_USAGE.md).

Task 8 decision regression passed **62 tests** covering budget scopes,
method routing, transport, checkpoints and the selected baseline/Ours paths.
The CLI credit loader's missing `datetime` import was fixed and the pinned
VND envelope was rechecked offline.
