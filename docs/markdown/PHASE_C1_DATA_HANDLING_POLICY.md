# Phase C.1 data handling decision — 14/11/2026

Scope: the five case IDs in `data/clinsql/pilot_5_validation_development_v1.json`
only. User Trần Đại Hải, the project-level experiment lead and stated decision
maker, explicitly accepted `READ_ONLY_LIKELY_WITH_APPROVED_RISK` for Phase C.1.
This is risk acceptance for the unverified Organization/Folder IAM inheritance,
not an assertion of Organization authorization or `VERIFIED_READ_ONLY`.

The approved BigQuery limits are 256 MiB maximum billed per SQL, at most three
SQL executions per case, 3.75 GiB reserved aggregate over the five cases and
120 seconds per query. The draft benchmark profile additionally limits output
to 10,000 rows and 16 MiB serialized result per query. A result exceeding a cap
is `INCOMPLETE_RESULT` or `BUDGET_EXCEEDED`, never a model accuracy failure.
No cap may be increased automatically. Phase A approval is not reused.

Result artifacts may be retained in `results/restricted` for at most seven days
after each case completes. The directory ACL permits only the current account,
Administrators and SYSTEM. Raw patient rows are excluded from application logs
and must not be sent to OpenAI. The model receives the English validation
question, approved schema metadata and sanitized SQL error messages only.
The retention command is manual and must be run when artifacts become due;
there is no background deletion task.

Source of decision: the user's two Phase C.1 approval answers in this chat,
following the 14/11/2026 access and budget report. The decision does not
authorize MAC-SQL/SDE-SQL probes, full validation/test batches, CLINSQL judge,
or transmission of clinical values to a model.
