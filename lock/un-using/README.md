# Archived, unused baselines

CLIN-SQL and SDE-SQL are frozen here as historical material. They are no longer
part of the active benchmark. `adapted/` contains the former runnable adapters,
validation scripts, and their baseline-specific tests. The official CLIN-SQL
and SDE-SQL Git checkouts are stored locally in this directory and remain
unmodified; their commits and key hashes are in `PAPER_SOURCE_LOCK.json`.

The two official checkouts are ignored by the parent repository because the
CLIN-SQL tree contains a large released dataset. On another machine, run
`python lock/un-using/restore_official.py` to fetch their recorded commits,
then `python lock/un-using/verify_archive.py` to verify the original trees and
the archived adapted code.
`BASELINE_LOCK.json` records the original adaptation and
the validation-v9 settings. Historical results remain under `results/`.

The shared `src/ehrqa/clinsql` utility code remains in place because the Ours
implementation still imports portions of it. No archived CoT or SDE runner is
invoked by the new OmniSQL/BIRD benchmark.
