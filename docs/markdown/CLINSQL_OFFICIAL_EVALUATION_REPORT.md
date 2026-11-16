# Official CLINSQL evaluator status — 14/11/2026

**`OFFICIAL_SCORE_NOT_AVAILABLE` for every method.** The locked official scorer
is `external/clinsql_official/evaluation/clinical_rubric_scorer.py`, SHA-256
`3a3b9734cab64fafbde7f387d5cb84f569d9072acbb6e7e072311f2b858f475c`.
It requires Azure GPT-5-Chat and sends predicted result rows in judge prompts.
No patient-result transfer or judge budget is approved; no judge call was made.
The user expressly selected the no-result-transfer option while confirming
MIMIC-IV research-use rights. This decision blocks only external judge scoring;
offline diagnostics, fidelity work and separately approved execution continue.
The five CLINSQL CoT saved results were staged temporarily and parsed by the
native scorer's CSV loader, 5/5 PASS, then deleted from temporary staging.
No reference or rubric was used in inference.

The pilot diagnostic found 0/5 strict column/shape matches against validation
reference CSVs. That is **not** official SQL Score or Execution Score and does
not establish five wrong clinical answers. See `PILOT_5_ACCURACY_EVALUATION.md`
and `results/phase_c1_pilot_diagnostic.json`. The official aggregation,
critical/sequential rubric rules and judge prompts remain unchanged in source.
Once policy, Azure configuration, 110-call budget, artifact retention and
failure accounting are approved, score saved predictions without new
generation or BigQuery execution.
