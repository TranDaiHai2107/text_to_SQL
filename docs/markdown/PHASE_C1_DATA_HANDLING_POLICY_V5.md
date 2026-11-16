# Phase C.1 extended BigQuery budget — 14/11/2026

User Trần Đại Hải approved a revised BigQuery budget for **the same five**
CLINSQL validation-development pilot case IDs: at most **16 GiB billed per SQL**
and **160 GiB aggregate**, no more than three SQL executions per case, timeout
120 seconds/query, output cap 10,000 rows and 16 MiB serialized result/query.
At $6.25/TiB, the 160 GiB configured ceiling is approximately USD 0.9766
before free tier, billing-plan differences and taxes; it is not an invoice.
The decision followed measured dry runs of 7.91 GiB for Vital Signs and 2.66
GiB for Medication, both blocked by the earlier 256 MiB cap. No SQL beyond
the earlier cap was executed before this approval.

All other controls in `PHASE_C1_DATA_HANDLING_POLICY.md` remain in force:
reader Service Account, `READ_ONLY_LIKELY_WITH_APPROVED_RISK` without an
Organization IAM attestation, SQL Guard, table allowlist, dry run, persistent
SQL ledger, restricted ACL, no raw rows in application logs, no patient results
sent to LLM, and seven-day artifact retention with manual expiry deletion.
The existing ledger includes BigQuery bytes already billed for the same pilot;
the expanded budget does not reset that expenditure. This approval does not
authorize full validation, test, MAC-SQL/SDE-SQL probes or official judge runs.
