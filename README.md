# Text-to-SQL research workspace

## Current benchmark

`benchmarks/omnisql/` contains a pinned copy of the authors' OmniSQL source,
their exact BIRD-dev prompt file, the official BIRD `dev_20240627` SQLite
databases, and an adapter for comparing against the paper's GPT-4o reference
row. See [the benchmark README](benchmarks/omnisql/README.md) for the verified
assets, scoring protocol, and commands. No GPT-4o inference has been run for
this benchmark yet.

## Ours

`src/ehrqa/agentic/` and `src/ehrqa/clinsql/proposed.py` contain the existing
Ours pipeline. Some shared utilities remain in `src/ehrqa/clinsql/` because
Ours still imports them. Adapting Ours from BigQuery/MIMIC-IV to SQLite/BIRD
is separate work; the OmniSQL benchmark scaffold does not yet produce an
Ours-on-BIRD score.

## Archived work

The former CLIN-SQL and SDE-SQL baselines, their validation scripts, and
source locks are in `lock/un-using/`. They are no longer active comparison
methods. Historical research notes and results remain available.
