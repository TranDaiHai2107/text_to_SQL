# Pilot API and BigQuery usage

The 15 November continuation used six BigQuery dry runs to validate
the MAC-SQL sampling SQL. It created zero billable query jobs and made zero
GPT-5-mini requests. Historical four-method totals are in the
[pilot results](THREE_METHOD_LIVE_PILOT_RESULTS.md). The separate Qwen run
for Ours used seven local model requests with 82,695 input and 13,996 output
tokens. These tokens incurred no model API charge.

The Task 8 catalog used four BigQuery query jobs and 41,943,040 billed bytes,
approximately 6.16 VND at the pinned on-demand rate before free tier and
credits. Catalog recovery read the existing job results.
[Catalog receipt summary](CLINICAL_CATALOG_EXPORT_FINAL.md)

Task 8 preparation submitted zero API requests and zero BigQuery jobs.
Clinical billed bytes and incremental Task 8 execution costs are zero.
Processing the Task 8 combined decision also used **0 requests, 0 tokens,
0 BigQuery jobs, 0 billed bytes and 0 VND BigQuery cost**. The saved SDE
synthetic receipt was checked locally without a new request.

| Scope | Requests | Input / output tokens | BigQuery jobs / billed bytes | Runtime |
|---|---:|---|---|---|
| Prior CoT, five saved cases | 6 | 24,660 / 21,182 | 5 / 20,081,278,976 | 261.72 s across saved cases |
| Task 6 MAC-SQL, SDE-SQL and Ours clinical pilot | 0 | 0 / 0 | 0 / 0 | No clinical run |
| Task 6 synthetic SDE transport | 2 | 23 / 292 confirmed. Separate pending reservation of 152 / 4,608. | 0 / 0 | 8.10 s command wall time |

The synthetic SDE request with three choices estimates to **$0.00058975**
at the configured GPT-5-mini rates. The ledger includes the unresolved
nine-choice reservation and reports **$0.00984375** total reserved plus
confirmed usage. The reservation is not a confirmed charge. No retries were
submitted after the two checks. [OpenAI GPT-5-mini pricing](https://developers.openai.com/api/docs/models/gpt-5-mini)

The prior CoT audit estimated $0.04852900 inference and $0.11414886 BigQuery
on-demand equivalent. Those estimates exclude earlier calibration runs
and were not incurred during Task 6. Cloud Billing credit and invoice
figures remain unverified.
