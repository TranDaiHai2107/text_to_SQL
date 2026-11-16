# Four-method CLINSQL pilot readiness

The final user attestation authorizes the five pilot questions. Ours pins
the verified catalog SHA-256. CoT and SDE-SQL each have five locally staged
predictions. The 20-case manifest awaits ten complete MAC-SQL and Ours
artifacts. Those runs require verification of the OpenAI project's data
controls for their restricted sampling and catalog evidence.
[PhysioNet guidance](https://physionet.org/news/post/llm-responsible-use/) ·
[OpenAI Data Controls](https://developers.openai.com/api/docs/guides/your-data)

The native rubric backend requires Azure GPT-5-Chat deployment `gpt-5-chat`,
API version `2024-12-01-preview`, temperature `0.2`, and a 1,024-token
completion cap. Live rubric calls require the deployment preflight and
separate authorization to transmit complete result rows.
[Judge configuration](CLINSQL_JUDGE_BACKEND_STATUS.md)

The [Task 8 decision record](TASK8_COMBINED_APPROVAL.md) consolidates the decisions
and exact limits for catalog export and the three live pilot methods.

**Task 7:** The financial gate is approved for the dated VND envelope.
Grouped SDE transport passed live synthetic verification. A combined
decision still needs to authorize dictionary-only export and restricted
storage, MAC metadata-only A/C/E (or separate D for column sampling), SDE
grouped A/C/E, and Ours A/B/C/E. Each approval must bind the five pilot
cases or dictionary-only scope, the evidence policy, method budgets,
and the current configuration and credit hashes.

`plan --method sde_sql --variant grouped_3x3` prints the configuration hash
for the verified adaptation. The grouped route requires a distinct approval
and reserves capacity for up to 130 requests across the five cases.

**Task 6 status: PARTIALLY_COMPLETED.** Reader ADC verified. Cloud Billing
returned HTTP 403 and the credit balance remains unverified. MAC-SQL,
SDE-SQL and Ours each have zero new clinical cases. SDE's live synthetic
three-choice request passed. Its nine-choice request returned HTTP 400.
The clinical catalog awaits separate local export authorization.

Supply a verified credit envelope with `--credit <credit.json>` for
`execute`, `export-catalog` and `reconcile-sql`. Pin the envelope hash
as `credit_sha256` in each authorization. After approvals are in place,
the runner moves through the five cases without confirmation between
cases. It stops on infrastructure, security or uncertain transport
outcomes. The expansion to 190 validation cases remains closed pending the
pilots, resource accounting and separate validation approval.

**CoT 5/5 reused locally.**
The new checkpoint records reference the five existing CoT artifacts and
preserve their expiry dates. The importer verified the saved job, predicted
SQL, row count and artifact digest. It issued zero API or BigQuery requests.

**Offline regression: 71 passed.** The suite covers final SQL attribution,
method routing, synthetic multi-choice transport, catalog export and retrieval,
reader and SQL guard checks, budget scope, checkpoint replay, completeness and
local staging without gold SQL.

## Implementation and method scope

The shared runner uses the pinned validation questions and 31-table schema,
reader ADC, SQL Guard, durable per-approval API/SQL ledgers, private result
artifacts and a manifest-locked experiment state. Completed checkpoints are
replayed after digest and scope checks. Interrupted cases require
reconciliation before any retry. The CLI runs cases sequentially and stops
after the first non-executable prediction for review.

- **CLINSQL CoT:** saved results imported into the common checkpoint contract.
  No new inference approval is needed for local reuse within artifact retention.
- **MAC-SQL:** routes Selector, Decomposer and up to three Refiner turns.
  `metadata_only` is a restricted adaptation. `column_samples` uses the
  guarded sampler and needs authorization for the actual values it can expose.
- **SDE-SQL:** uses the shared backend for exploration, selection and
  refinement. The preflight command requests 9 and 3 choices with synthetic
  text and persists successful compatibility verification. The clinical pilot
  needs separate authorization for probe feedback and result column names.
- **Ours:** uses the approved catalog hash, frozen development examples,
  schema index, verification and bounded repair. Restricted traces record
  retrieved evidence and correction categories. The shared run record holds
  LLM/SQL counts and latency. A real authorized catalog export is pending.

For either MAC-SQL or SDE-SQL, a final unexecuted correction runs as a separate
evaluation execution. Only the complete result from that final SQL is stored.
Incomplete results, infrastructure failures and model failures have separate
statuses. `check-staging` verifies a checkpoint and builds the scorer's local
file layout temporarily under restricted storage. Azure scoring requires
separate approval. Run `retention` to inspect expiry and
`retention --delete-expired` to apply it for new methods. CoT remains under
its original retention command and policy.

## Evidence and approval

Task 8 selected `metadata_only` for MAC-SQL, `grouped_3x3` for SDE-SQL
and `dictionary_rag` for Ours. The [combined decision](TASK8_COMBINED_APPROVAL.md)
records the choices and scoped IAM risk acceptance. Live activation is
pending the actual data policy or authorization reference. Ours additionally
needs the verified digest from the local catalog export.

The existing CoT policy covers its five cases and English questions, schema
and sanitized SQL feedback. It does not authorize another method. For new
runs, `FourMethodApproval` uses `phase=four_method_validation_pilot` and binds
the reader, case IDs, schema and index hashes, model, runtime configuration
hash, policy reference and API/SQL budget hashes. The following are the exact
evidence entries each variant requires. E grants only the stated feedback.
Raw result cells have no authorized transmission path.

- A = `question_and_schema`, B = `dictionary_metadata`, C =
  `sql_and_sanitized_errors`, D = `approved_column_samples`.
- MAC metadata-only needs A, C and E = `row_presence_and_null`. Full sampling
  additionally needs D. The native Refiner's empty and NULL messages disclose
  result-derived facts even in metadata-only mode.
- SDE needs A, C and E = `probe_labels_and_column_names`.
- Ours needs A, B, C and E = `shape_and_row_counts`.
- Local catalog export needs B for local storage. Synthetic transport
  verification uses an empty evidence map and no BigQuery transport.

Use the shared approval fields in the existing CoT draft as field
documentation only. The new schema additionally requires `method`, `variant`,
`evidence`, `policy_reference`, `index_sha256`, `catalog_sha256` and
`configuration_sha256`. For the export and synthetic transport, the case
list contains only `catalog_export` or `sde_transport` respectively. Unused
budget hash fields use 64 zeroes. Approval files must reflect actual
authorization. The commands below use placeholders for those files.

## Commands

```powershell
py -3 run.py four-method-pilot reuse-cot
py -3 run.py four-method-pilot plan --method mac_sql --variant metadata_only
py -3 run.py four-method-pilot plan --method sde_transport --variant synthetic_only
py -3 run.py four-method-pilot task6-synthetic-sde
py -3 run.py four-method-pilot plan --method sde_sql --variant probe_labels_only
py -3 run.py four-method-pilot plan --method ours --variant dictionary_rag --catalog <catalog.json>
py -3 run.py four-method-pilot execute --approval <method-approval.json> --api-budget <method-api.json> --sql-budget <method-sql.json> --credit <credit.json>
py -3 run.py four-method-pilot execute --approval <ours-approval.json> --api-budget <ours-api.json> --sql-budget <ours-sql.json> --catalog <catalog.json> --credit <credit.json>
py -3 run.py four-method-pilot check-staging --record <checkpoint.json>
```

Each execute command consumes its five approved development cases. The
existing experiment state retains the 152 development and 38 internal-check
partitions. The CLI opens only this pilot. Before expanding to 190, reconcile
all pilot failures, finalize the evidence policy and budgets, and authorize
the two validation scopes independently. Seal the 443 test cases until
configuration freeze and separate authorization. The official scorer is
unchanged.
