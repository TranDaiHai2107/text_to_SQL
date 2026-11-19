# OmniSQL / BIRD dev reproduction

**Audit status (2026-11-19):** source is byte-identical to upstream, benchmark files
and prompts are hash-verified, the authors' released predictions reproduce all six
paper EX numbers exactly, and a real rerun of `gpt-4o-mini-2024-07-18` gives
58.9 greedy / 62.0 majority-8 (paper 58.8 / 61.5). OmniSQL weights were not rerun
(no suitable GPU). See [AUDIT.md](AUDIT.md).
For the selected GPT-4o-mini baseline, see
[GPT4O_MINI_CODE_FIDELITY.md](GPT4O_MINI_CODE_FIDELITY.md) for what the
implementation can and cannot prove from public author code.

## Scope and fidelity

- Paper: [Li et al., OmniSQL, PVLDB 18(11), 2025](https://www.vldb.org/pvldb/vol18/p4695-li.pdf).
- Exact upstream source snapshot: `official/`, commit `a66d732010c89fac4353488d1c59e0b06f92b742`, key hashes in `SOURCE_LOCK.json`. Files in `official/` are unmodified.
- Benchmark: BIRD `dev_20240627`, 1,534 questions, 11 SQLite databases. The downloaded archive is from the official BIRD host, SHA-256 in `SOURCE_LOCK.json`.
- Prompts: `data/benchmarks/bird/omnisql_dev_bird.json` is the exact `data/dev_bird.json` member of the authors' `OmniSQL-datasets/data.zip` release at Hugging Face revision `e1db8bb10ef11f92eacd8d87801d716ba0e9e9be`. Only this member was fetched from the 22 GB ZIP. Its SHA-256 is pinned. Every question and gold SQL is aligned in order with official BIRD dev.
- Metric: `score_bird.py` imports `official/train_and_evaluate/evaluate_bird.py` without changing it. EX compares sets of result rows after executing predicted and gold SQL on the dated BIRD SQLite database. The authors' default (20 processes, 10 s per predicted+gold pair) under-counts on a laptop, so this repo scores with `--num-cpus 4 --timeout 60`, chosen from measured gold runtimes (see AUDIT.md), and applies the same limits to the voting step. Report these settings and use them for every compared method.
- OpenAI reference rows, paper Table 4 (BIRD dev EX, greedy / majority-8): `gpt-4o-mini-2024-07-18` 58.8 / 61.5, rerun here 58.9 / 62.0; `gpt-4o-2024-11-20` 61.9 / 64.0, not rerun.

The released upstream `eval_open_source_models.py` runs the open model weights
through vLLM. It does **not** contain the GPT-4o or GPT-4o-mini API inference code.
`run_gpt4o_reference.py` is therefore an explicitly reconstructed adapter,
not verbatim author code. It sends only `input_seq` to the API; the released
prompt records also contain `output_seq` (gold SQL), which must never be sent
to the model. The adapter uses the source's final-`sql`-fence extraction,
temperature 0 for greedy, or temperature 0.8 with 8 candidates for majority.
The exact proprietary API implementation cannot be proved from the released
source; the adapter's `max_tokens=2048` comes from the author's open-model
`infer.py`, not a published GPT API setting. Each mode writes a manifest with
model snapshot, request settings, input/evaluator/adapter hashes. OpenAI sampling
is not bit-deterministic, so a rerun matches the paper within noise, not exactly.

This benchmark covers English question to SQL only. BIRD is not MIMIC-IV and
does not score SQL-result-to-English answers. The original Ours pipeline still
targets BigQuery/MIMIC-IV and has not yet been adapted to BIRD SQLite.

## Prepare data

From the repository root (the two download scripts require internet):

```powershell
python benchmarks/omnisql/download_bird_dev.py
python benchmarks/omnisql/fetch_official_prompt.py
python benchmarks/omnisql/verify_assets.py
```

`download_bird_dev.py` resumes the official 346 MB ZIP by HTTP ranges and
extracts both the outer release and nested database ZIP.

The ZIP, databases and prompts live under `data/benchmarks/bird/` and are
ignored by Git because the databases are large. The scripts and hashes remain
tracked, so another machine can rebuild the same inputs. Never use BIRD dev
gold SQL or `output_seq` in a retrieval corpus or inference prompt.

## Environment and scoring

```powershell
py -3.12 -m venv .venv_bird
.\.venv_bird\Scripts\python.exe -m pip install -r environment/requirements-omnisql-bird.txt
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/verify_assets.py
$env:PYTHONUTF8='1' # needed by the author's evaluator on Windows
```

To inspect the chosen GPT-4o-mini baseline with zero API calls:

```powershell
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/run_gpt4o_reference.py --mode greedy_search
```

An actual call requires both `--execute` and an explicit per-invocation
`--max-requests` limit (`--workers` sets concurrency, default 8). Results go to
`results/omnisql/<model snapshot>/`. Checkpoints are appended after each question. When all
1,534 questions finish, the runner writes a JSON file in the authors' expected
`pred_sqls` format. The evaluator can then score it:

```powershell
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/gpt-4o-mini-2024-07-18/greedy_search.json --mode greedy_search --output results/omnisql/gpt-4o-mini-2024-07-18/greedy_search_score.json
```

For majority voting, use `--mode major_voting` in both commands. It generates
8 outputs per question and costs more. Keep the greedy and majority scores
separate when comparing with the paper.

To rerun an **OmniSQL model** rather than the GPT-4o reference, use
`run_official_model.py --model seeklhy/OmniSQL-7B --mode greedy_search`
to inspect the author-inference and author-evaluator commands. For `--execute`,
download the exact model revision listed in `SOURCE_LOCK.json` using a Hugging
Face snapshot path and pass it as `--model-path`. The wrapper rejects unpinned
remote weights for an actual run. The upstream model weights are released in
7B/14B/32B sizes. This path has not been executed locally.
Recreating SynSQL-2.5M and training the weights requires substantially more
compute and is not necessary to evaluate the released model.

## Ours on BIRD (port, 2026-11-19)

`run_ours_bird.py` runs the repository's full-agentic pipeline (`src/ehrqa/agentic`, profile
`bird`) with the same `gpt-4o-mini-2024-07-18` snapshot, temperature 0, and the same scorer
settings. Per question it receives the question, BIRD's evidence, and the schema text of the
baseline prompt (DDL with descriptions and example values). Gold SQL is never loaded.

- RAG layers: lexical schema retrieval, stored-value retrieval (`src/ehrqa/bird/values.py`,
  index cached in `data/benchmarks/bird/ours_value_index/`), and 3 BM25 demonstrations from
  BIRD **train** (`fetch_bird_train.py`; no database or question is shared with dev).
- Variants: `v6` (default: link, decompose, 3 branches, local result-fingerprint vote, LLM
  selector only on disagreement), `lite`, `full`.
- SQLite is the authority on executability. Static-analysis findings are advisory.
- Linker and plan outputs get deterministic, meaning-preserving interface repairs
  (`contracts.normalize_linking_generic`, `normalize_decomposition_generic`).

```powershell
$env:PYTHONUTF8='1'
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/run_ours_bird.py --variant v6 --execute --max-usd 6 --workers 6
.\.venv_bird\Scripts\python.exe benchmarks/omnisql/score_bird.py results/omnisql/ours/gpt-4o-mini-2024-07-18/v6/greedy_search.json --mode greedy_search --output results/omnisql/ours/gpt-4o-mini-2024-07-18/v6/greedy_search_score.json
```

The 30-question pilots (`results/omnisql/ours/pilot30_*`, seed 20261119) were used only to
fix interface failures, not to tune answers.

### Results (2026-11-19, BIRD dev, scorer num_cpus 4 / timeout 60)

| Method | EX all (1534) | EX held-out (1234) | Calls/q | Cost |
|---|---|---|---|---|
| Baseline greedy (rerun) | 58.93 | 58.51 | 1 | $0.71 |
| Baseline majority-8 (rerun) | 61.99 | 61.18 | 1 (n=8) | $2.41 |
| Ours v6 (JSON agentic stages) | 60.04 | 60.70 | 5.31 | $3.74 |
| Ours v8 | 63.30 | 63.05 | 2.13 | $3.29 |
| **Ours v9** | **65.06** | **64.83** | 3.21 | $6.46 |

v8 vs majority-8 on held-out: 66 vs 43 discordant, exact McNemar p = 0.035 (all dev: p = 0.10).
v8 vs greedy: p < 0.001. Split and tests: `compare_ours.py`, `results/omnisql/ours/splits.json`.

v9 = v8 + a plan-prompt generator (8 more samples at T=0.8), result vote by row *set* (the
metric's and the baseline vote's equivalence) and a 5-sample listwise selector called only when
no result group holds a majority (161 questions). Every design choice was made on the
300-question tuning split with `v9_lab.py` (reusing v8 candidates); the full run was done once.

| v9 vs | split | v9 only / other only | exact McNemar p |
|---|---|---|---|
| majority-8 | all dev | 105 / 58 | 0.0003 |
| majority-8 | held-out | 87 / 42 | 0.0001 |
| greedy | all dev | 142 / 48 | < 0.0001 |
| v8 | all dev | 63 / 36 | 0.0086 |

By difficulty vs majority-8: simple 71.24 vs 67.35 (p = 0.0002), moderate 57.11 vs 54.96
(p = 0.27), challenging 51.03 vs 50.34 (p = 1.0). Tuning-split lab findings: LLM selection
above a 50% vote share broke as many answers as it fixed; weighting generators did not help.
v9 costs 2.7x the majority baseline ($6.46 vs $2.41).

**Equal sample budget (re-voting the v9 run's own candidates, local set-EX = official, 998/998
reproduced; `v9/candidate_executions.json`).** Majority-8 baseline = 61.99.

| Ours, 8 samples only (no greedy, repair, selector) | EX all | vs maj-8 (all) | held-out p |
|---|---|---|---|
| 4 base-prompt + 4 plan-prompt samples | 63.62 | 97 / 72, p = 0.065 | 0.030 |
| 8 base-prompt samples (values + few-shot enrichment) | 63.62 | 83 / 58, p = 0.043 | 0.012 |
| 8 plan-prompt samples | 62.45 | p = 0.68 | 0.49 |
| random 4 + 4 subsets (30 draws) | 63.90 ± 0.35 | | |
| 16 samples (8 + 8), vote only | 64.80 | 105 / 62, p = 0.001 | 0.0001 |

A baseline majority over 16 samples has not been run, so the 8 -> 16 gain is not yet separated
from the effect of sampling more.
