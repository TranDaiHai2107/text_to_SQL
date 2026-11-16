# Four-method CLINSQL validation pilot — current state 14/11/2026

**Status: NOT_RUN_AS_FOUR_METHOD_COMPARISON.** Only CLINSQL CoT +
Self-Refinement has five complete GPT-5-mini/BigQuery validation-development
predictions. See `GPT5_MINI_LIVE_PILOT_RESULTS.md` for five job IDs, actual
tokens/billed bytes and versioned approvals. Its official score is unavailable.

MAC-SQL, SDE-SQL and Proposed System have **zero live predictions**. Their
offline parity/mock progress and blockers are documented in
`MAC_SQL_FIDELITY_FINAL.md`, `SDE_SQL_FIDELITY_FINAL.md` and
`PROPOSED_SYSTEM_FINAL.md`. The Phase C.1 approval covers only the five
CLINSQL CoT cases; it does not permit other methods or SQL probes. All four
method scores, paired differences and cost comparison remain `NOT_AVAILABLE`.
The user's no-result-transfer decision keeps the official judge closed but
does not halt offline method development. There is no still-valid scoped
BigQuery approval for MAC-SQL, SDE-SQL or Ours patient queries/probes.
