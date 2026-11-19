"""Replay the authors' released BIRD predictions through their untouched evaluator.

This audit uses no model API and writes its detailed evaluator output to an ignored
data directory. It checks row alignment and voting selections against the arrays
released by the OmniSQL authors before recording EX.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import zipfile

from verify_assets import DATA, HERE, verify


ARCHIVE = DATA / "OmniSQL_eval_results.zip"
OUT = DATA / "omnisql_paper_score_audit"
EXPECTED = {
    "7B": {"greedy_search": 0.639, "major_voting": 0.661},
    "14B": {"greedy_search": 0.642, "major_voting": 0.659},
    "32B": {"greedy_search": 0.645, "major_voting": 0.670},
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=EXPECTED, required=True)
    parser.add_argument("--mode", choices=("greedy_search", "major_voting", "released_majority"), required=True,
                        help="released_majority scores the SQL the authors selected by voting, without re-voting")
    parser.add_argument("--num-cpus", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    assets = verify()
    if not ARCHIVE.is_file():
        raise FileNotFoundError(ARCHIVE)
    lock = json.loads((HERE / "SOURCE_LOCK.json").read_text(encoding="utf-8"))
    with ARCHIVE.open("rb") as stream:
        archive_hash = hashlib.file_digest(stream, "sha256").hexdigest()
    if archive_hash != lock["official_predictions_archive_sha256"]:
        raise ValueError("Official prediction ZIP differs from pinned release")
    OUT.mkdir(parents=True, exist_ok=True)
    prefix = f"OmniSQL_eval_results/OmniSQL-{args.model}_dev_bird/"
    pred_member = "greedy_search_.json" if args.mode == "greedy_search" else "sampling_.json"
    selected_member = ("greedy_search__pred_greedy_search_sqls.json"
                       if args.mode == "greedy_search" else "sampling__pred_major_voting_sqls.json")
    with zipfile.ZipFile(ARCHIVE) as archive:
        pred_bytes = archive.read(prefix + pred_member)
        rows = json.loads(pred_bytes)
        released_selected = json.loads(archive.read(prefix + selected_member))
    prompt_rows = json.loads((DATA / "omnisql_dev_bird.json").read_text(encoding="utf-8"))
    expected_n = 1 if args.mode == "greedy_search" else 8
    if len(rows) != assets["questions"] or len(released_selected) != assets["questions"]:
        raise ValueError("Official prediction count differs from BIRD dev")
    if any(len(row["pred_sqls"]) != expected_n for row in rows):
        raise ValueError("Official candidate count differs from paper")
    if any(row["input_seq"] != ref["input_seq"] or row["output_seq"] != ref["output_seq"]
           for row, ref in zip(rows, prompt_rows)):
        raise ValueError("Prediction prompts/gold differ from pinned OmniSQL dataset")

    stem = f"{args.model}_{args.mode}"
    pred_path = OUT / f"{stem}_official_predictions.json"
    eval_mode = args.mode
    if args.mode == "released_majority":
        # Score the authors' voted SQL directly (one SQL per question) with the greedy EX path.
        pred_path.write_text(json.dumps([{"pred_sqls": [sql]} for sql in released_selected],
                                        ensure_ascii=False), encoding="utf-8")
        eval_mode = "greedy_search"
    else:
        pred_path.write_bytes(pred_bytes)
    log_path = OUT / f"{stem}_evaluator.log"
    sys.path.insert(0, str(HERE / "official" / "train_and_evaluate"))
    import evaluate_bird  # author's unmodified evaluator

    def evaluate():
        return evaluate_bird.run_eval(
            str(DATA / "dev_20240627" / "dev.json"), str(pred_path),
            str(DATA / "dev_20240627" / "dev_databases"), eval_mode, False,
            num_cpus=args.num_cpus, timeout=args.timeout,
        )
    with log_path.open("w", encoding="utf-8") as log, contextlib.redirect_stdout(log):
        warmup_score, _ = evaluate()
        score, actual_selected = evaluate()
    per_question = [row["correctness"] for row in evaluate_bird.evaluation_results]
    selection_mismatches = sum(a != b for a, b in zip(actual_selected, released_selected))
    mismatch_indices = [index for index, (a, b) in enumerate(zip(actual_selected, released_selected)) if a != b]
    result = {
        "model": args.model,
        "mode": args.mode,
        "questions": len(rows),
        "candidates_per_question": expected_n,
        "num_cpus": args.num_cpus,
        "timeout_seconds": args.timeout,
        "released_prediction_sha256": hashlib.sha256(pred_bytes).hexdigest(),
        "warmup_ex": warmup_score,
        "ex": score,
        "n_correct": sum(per_question),
        "ex_percent_one_decimal": round(score * 100, 1),
        "paper_ex_percent_one_decimal": round(EXPECTED[args.model]["major_voting" if args.mode == "released_majority" else args.mode] * 100, 1),
        "selected_sql_mismatches_vs_author_release": selection_mismatches,
        "selected_sql_mismatch_indices": mismatch_indices,
    }
    (OUT / f"{stem}_actual_selected_sql.json").write_text(
        json.dumps(actual_selected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / f"{stem}_result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
