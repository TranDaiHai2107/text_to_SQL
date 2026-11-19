# Active benchmark environment

The OmniSQL/BIRD scoring and GPT-4o reference adapter use
`requirements-omnisql-bird.txt` in a separate `.venv_bird` environment.
See [`benchmarks/omnisql/README.md`](../benchmarks/omnisql/README.md) for
the benchmark commands. The former CLIN-SQL and SDE-SQL dependency locks
are stored under `lock/un-using/adapted/environment/`.

Running the released OmniSQL 7B/14B/32B weights requires a separate Linux,
CUDA and vLLM environment as specified in the author's unmodified
`benchmarks/omnisql/official/train_and_evaluate/README.md`.
