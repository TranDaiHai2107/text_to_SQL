"""Score full BIRD dev predictions with OmniSQL's unmodified EX evaluator."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from verify_assets import DATA, HERE, ROOT, verify

# The author default (20 processes, 10 s for each predicted+gold pair) depends on the hardware:
# on a 12-thread laptop heavy BIRD queries time out and EX is under-counted (62.3-63.8% instead of
# 63.9% for OmniSQL-7B). With 4 processes and 60 s the authors' released predictions reproduce
# every paper EX exactly (see AUDIT.md). Both values are passed to the author function unchanged.
# 60 s is chosen from measured gold runtimes on this machine: no gold SQL takes 20-170 s (q646 17.5 s
# always fits; q518 178 s and q701 891 s always time out, as with the authors' 10 s). 120 s sits too
# close to q518 and made it flip between runs.
DEFAULT_NUM_CPUS = 4
DEFAULT_TIMEOUT = 60


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("predictions", type=Path, help="JSON list in official infer.py format (each row has pred_sqls)")
    parser.add_argument("--mode", choices=("greedy_search", "major_voting"), default="greedy_search")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--num-cpus", type=int, default=DEFAULT_NUM_CPUS)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per predicted+gold SQL pair")
    args = parser.parse_args()
    asset_info = verify()
    rows = json.loads(args.predictions.read_text(encoding="utf-8"))
    expected_n = 1 if args.mode == "greedy_search" else 8
    if len(rows) != asset_info["questions"] or any(len(row.get("pred_sqls", [])) != expected_n for row in rows):
        raise ValueError(f"Expected {asset_info['questions']} rows with {expected_n} SQL predictions each")
    if any("row_index" in row for row in rows) and [row.get("row_index") for row in rows] != list(range(len(rows))):
        raise ValueError("Prediction rows are not aligned with BIRD dev order")
    if all("input_seq" in row for row in rows):
        prompts = json.loads((DATA / "omnisql_dev_bird.json").read_text(encoding="utf-8"))
        if any(row["input_seq"] != prompt["input_seq"] for row, prompt in zip(rows, prompts)):
            raise ValueError("Prediction prompts are not aligned with the pinned OmniSQL BIRD dev prompts")
    sys.path.insert(0, str(HERE / "official" / "train_and_evaluate"))
    import evaluate_bird  # exact archived author implementation

    gold_file = DATA / "dev_20240627" / "dev.json"
    db_path = DATA / "dev_20240627" / "dev_databases"

    if args.mode == "major_voting":
        # major_voting() in the author file hard-codes 20 processes / 10 s for executing the 8
        # candidates. Route that call through the same num_cpus/timeout as the scoring step; the
        # voting logic itself (and evaluate_bird.py on disk) is unchanged.
        author_execute = evaluate_bird.execute_sqls_parallel

        def execute_with_cli_limits(db_files, sqls, num_cpus=1, timeout=1):
            return author_execute(db_files, sqls, num_cpus=args.num_cpus, timeout=args.timeout)
        evaluate_bird.execute_sqls_parallel = execute_with_cli_limits

    def evaluate():
        return evaluate_bird.run_eval(str(gold_file), str(args.predictions), str(db_path), args.mode, False,
                                      num_cpus=args.num_cpus, timeout=args.timeout)

    # auto_evaluation.py (author source) scores each mode once as a warm-up,
    # then a second time as the recorded result. Preserve that behavior.
    warmup_score, _ = evaluate()
    score, selected_sql = evaluate()
    per_question = [row["correctness"] for row in evaluate_bird.evaluation_results]
    result = {"benchmark": "BIRD dev_20240627", "questions": asset_info["questions"],
              "mode": args.mode, "warmup_ex": warmup_score, "ex": score, "n_correct": sum(per_question),
              "num_cpus": args.num_cpus, "timeout_seconds": args.timeout,
              "source_commit": asset_info["source_commit"],
              "prediction_file": str(args.predictions.resolve())}
    if args.mode == "major_voting":
        result["note"] = "voting step executed with the same num_cpus/timeout (author default 20 / 10 s)"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        args.output.with_name(args.output.stem + "_selected_sql.json").write_text(
            json.dumps(selected_sql, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        args.output.with_name(args.output.stem + "_per_question.json").write_text(
            json.dumps(per_question) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
