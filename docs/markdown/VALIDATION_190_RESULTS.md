# CLINSQL validation (152 development + 38 internal-check)

**Status: NOT_RUN.** The five completed CLINSQL CoT development cases are a
technical pilot and do not constitute the 152-case development experiment or
the 38-case internal-check. Official SQL/Execution Score is unavailable even
for the pilot because the source Azure GPT-5-Chat judge requires a separate
data-transfer approval and budget. MAC-SQL, SDE-SQL and Ours have zero live
validation predictions. No aggregate validation accuracy or method ranking
is reported.
The user's current decision also prohibits transmitting saved result rows to
the official Azure judge. Development can continue offline; no official score
is inferred from diagnostic shape comparison.

The master 152/38 question-only split is locked in
`data/clinsql/master_experiment_pre_freeze_v1.json`. The 145-example Ours
few-shot corpus excludes pilot/holdout/test and two unsupported `derived`
examples. Phase C.1's 160 GiB budget is scoped to five cases and cannot be
reused for full validation. Before this file can contain scores, all four
method runners, fidelity/data gates, separate BigQuery approval, judge policy
and durable checkpoint accounting must pass.
