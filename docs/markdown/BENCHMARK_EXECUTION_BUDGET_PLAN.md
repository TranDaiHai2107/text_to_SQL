# Proposed pilot budgets

## Task 6 research credit policy

**Task 7 supersedes the pending financial status below.** Budget gate
`BIGQUERY_RESEARCH_BUDGET_APPROVED` for the dated snapshot. The user
confirmed project linkage to account `013047-311AC0-9ADD4D` and approved
**6,962,660.25 VND** with **773,628.92 VND** reserved. Google Billing Pricing
Table CSV confirms SKU `1DF5-1F98-1DD1`, BigQuery Analysis / On Demand,
0 VND at tier 0 and 161,556.250422631 VND/TiB from tier 1. The ledger uses
the paid rate conservatively across all bytes. The Decimal byte ceiling is
47,386,132,601,505 bytes before per-method and per-query constraints.
[Approved envelope](../TASK7_RESEARCH_CREDIT_VND.json).

Envelope SHA-256 for authorized method records is
`54a4be23a0fdde9af167d8e62a4b67d6beaa7cfb79842829aa2638d1b0e11eb1`.
Credit and price evidence are valid through the November 14 observation day
(Asia/Bangkok). Refresh both before a later run and reconcile external usage
against the balance. The shared ledger keeps pending reservations and
blocks a changed envelope on an existing ledger for review. Task 7 has
zero BigQuery jobs and zero billed bytes. The financial approval leaves
dictionary export and patient-data evidence approvals separate.

Credit balance status is `VERIFIED_WITH_USER_CONSOLE_EVIDENCE` as of
2026-11-14. The CSV embeds account `013047-311AC0-9ADD4D` in the Credit ID.
It confirms 7,754,701.00 VND original, 7,736,289.17 VND remaining
(99.7626%) and 18,411.83 VND used. The CSV end date is 2027-02-10.
The user reports prior gcloud verification for `kltn-text-to-sql`.
The saved gcloud project-to-account output was unavailable for independent
verification in this task. Reader Billing HTTP 403 only indicates lack of
permission. See the [evidence record](../TASK7A_CREDIT_EVIDENCE.json).

Google describes BigQuery as available under the trial and lists on-demand
queries as standard BigQuery usage. The CSV's scope refers to the trial
terms. This establishes general coverage for eligible BigQuery on-demand
queries. The account's VND SKU price still needs a Billing pricing record.
[Google Cloud Free Trial](https://docs.cloud.google.com/free/docs/free-cloud-features) ·
[BigQuery pricing](https://cloud.google.com/bigquery/pricing)

Task 7A proposed allocation is **6,962,660.25 VND** with **773,628.92 VND**
reserved. The spending amount rounds down to the nearest 0.01 VND. Budget
activation remains pending explicit approval, saved project linkage output
and the account's VND rate for the US on-demand Analysis SKU. Google's
public US list rate is USD 6.25/TiB. The Pricing Table provides the rate in
the billing account currency. A VND envelope requires `price_reference`
and a timezone-aware `price_valid_until` in addition to credit expiry.
The earlier of those deadlines blocks new reservations.
[Cloud Billing Pricing Table](https://docs.cloud.google.com/billing/docs/how-to/pricing-table)

The live CLI requires a credit JSON pinned by `credit_sha256` in each
method approval. It takes `mode=RESEARCH_CREDIT_AWARE`, `billing_account`,
`project`, `currency=VND`, `verified_credit`, `approved_spend`, `reserve`, `price_per_tib`,
`expires_at` (timezone-aware), `experiment_byte_limit` and
`evidence_reference`. All four BigQuery scopes use the same credit envelope.
The evidence reference should identify a Billing Console record showing
linkage, current trial/paid state, used and remaining credits, expiry and
coverage for BigQuery on-demand queries. The approved VND spend plus the
positive reserve must fit within the verified balance. The evidence record
leaves the VND SKU price, approved spend and reserve unset until supplied.
The ledger
accounts for the experiment's query jobs. Cloud Billing is authoritative
for other workloads, storage and the account balance.

The query cap starts at the dry-run estimate rounded to MiB and a minimum
of 10 MiB per referenced table. Headroom is 12.5% of the estimate, with a
16 MiB minimum and 1 GiB maximum. The reservation is bounded by per-query,
per-case, per-method and experiment limits. In research mode the SQL budget
field `max_bytes_per_experiment` acts as the method cap and the shared
credit envelope carries the experiment cap. The ledger reserves a job ID
before submission, reconciles actual billed bytes, and retains uncertain
reservations. `reconcile-sql` accepts the original approval, SQL budget and
credit files and reads existing jobs without resubmitting them. Resource
failures are recorded as `RESOURCE_BUDGET_BLOCKED`.
[BigQuery billing minimums](https://docs.cloud.google.com/bigquery/docs/troubleshoot-queries)

The GPT-5-mini budget accepts `policy=UNLIMITED_RESEARCH_NOV_2026` with
`max_cost_usd=null`. Request and token limits still apply. See the usage
report for the two live synthetic requests. The static 16 GiB calculations
below remain historical sizing examples.

These are capacity calculations for the five-case pilot. Select actual caps
after reviewing dry-run estimates and approving evidence. No existing CoT
approval can fund these runs.

| Path | Model capacity per case | SQL capacity per case |
|---|---|---|
| CoT reuse | 0 new requests | 0 new jobs |
| MAC metadata only | Up to 5 calls | Up to 4 jobs including final evaluation |
| MAC with values | Up to 5 calls | 225 column probes plus up to 4 jobs on the current manifest |
| SDE | Up to 24 requests with all JSON retries and three diagnosis rounds | 13 execution jobs plus a separate probe cap |
| Ours | 24 calls maximum | Up to 18 executions, including three branches with one semantic repair and up to three executions per proposal |
| Catalog export | 0 | Four dictionary queries once |
| SDE synthetic transport | Two calls once, with 9 and 3 choices | 0 |

Five-case upper bounds are 25 MAC calls, 120 SDE calls and 120 Ours calls.
At current runner output caps this reserves up to 204,800, 655,360 and
983,040 completion tokens respectively. SDE's worst request count comes
from 14 exploration calls, one nine-choice call and nine refinement calls
on the fallback path. The three-choice judge is an alternative branch.
Use `input_tokens × approved input rate + output_tokens × approved output rate`
with prices per token. Input budgets must include full schema, retrieval
context and feedback. For a model rate of $2 per million output tokens,
those output caps are about $0.41, $1.31 and $1.97 before input charges.
These figures are estimates using the existing experiment rate, not a
current billing quote. The separate synthetic check reserves 6,144 output
tokens.

At an illustrative cap of 16 GiB per job, the worst-case five-case MAC
metadata reservation is 320 GiB. MAC with all column samples is 18,320 GiB.
For SDE, a provisional 20-probe budget gives 33 jobs/case and 2,640 GiB
across five cases. Ours at 18 jobs/case would reserve 1,440 GiB. The SQL
ledger reserves the cap per submitted job and reconciles to billed bytes
when reported. These are ceilings, not expected charges. Incomplete
results or exhausted probe/bytes capacity stop the case and remain separate
from model accuracy. Probe fan-out is data dependent. The proposed SDE
cap requires review from observed pilot counts before larger runs.

The API JSON fields are `max_calls`, `max_input_tokens`,
`max_output_tokens`, `max_cost_usd`, `input_per_million_usd`,
`output_per_million_usd` and optional `policy=CAPPED`. The SQL budget
JSON uses `max_calls_per_question`, `max_probes_per_question`,
`max_bytes_per_question`, `max_bytes_per_experiment`. The approval
adds per-query bytes, timeout, row and result-byte caps. Pin the SHA-256
of each approved budget file. Size catalog limits separately because a
complete dictionary can exceed the pilot result row cap.

Scale validation budgets from observed pilot jobs, probe fan-out, tokens,
output bytes and failure modes. Keep development and internal-check
accounting separate. Set the final test and scoring budgets after
configuration freeze and separate authorization.
