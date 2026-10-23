"""Preparation, explicit-input postprocessing and scoring for all 11 paper rows.

`plan`, `list`, and `verify` never perform inference, model downloads or SQL execution.
`postprocess` and `score` are reserved for the later execution phase.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import sqlite3
import sys
import time
from datetime import datetime, timezone

from baseline_core import (apply_classifier, apply_entropy, apply_gef, apply_probgate, author_process_answer,
                           execute_readonly, post_process_sql, score_answers)

ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        raise ValueError(f"Output exists; choose a new output path: {path}") from exc


def provenance():
    names = ["baseline_core.py", "reproduce.py", "source_manifest.json", "configs/experiments.json"]
    return {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
            "platform": platform.system(),
            "sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in names}}


def registry():
    return load(ROOT / "configs/experiments.json")["experiments"]


def get_experiment(key):
    return next(e for e in registry() if e["id"] == key)


def verify(emit=True):
    manifest = load(ROOT / "source_manifest.json")
    for relative, expected in manifest["files"].items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError(f"Snapshot hash mismatch: {relative}")
    for split in ("train", "dev", "test"):
        ids = [r["id"] for r in load(ROOT / "data/inputs" / (split + ".json"))["data"]]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate IDs: {split}")
        labels = load(ROOT / "data/gold" / split / "label.json")
        answers = load(ROOT / "data/gold" / split / "answer.json")
        if set(ids) != set(labels) or set(ids) != set(answers):
            raise ValueError(f"Gold alignment error: {split}")
        if len(ids) != manifest["splits"][split]["count"]:
            raise ValueError(f"Split count mismatch: {split}")
        if {key for key, value in labels.items() if value == "null"} != {key for key, value in answers.items() if value == "null"}:
            raise ValueError(f"Answerability mismatch: {split}")
    db = ROOT / manifest["database_path"]
    with db.open("rb") as handle:
        if handle.read(16) != b"SQLite format 3\x00":
            raise ValueError("Invalid SQLite file")
    for row in registry():
        if not row["model"] or not row["source_files"]:
            raise ValueError(f"Incomplete registry entry: {row['id']}")
        for path in row["source_files"]:
            if not (ROOT / path).is_file():
                raise ValueError(f"Missing source: {path}")
    cached = load(ROOT / manifest["cached_test_predictions"])
    test_ids = {r["id"] for r in load(ROOT / "data/inputs/test.json")["data"]}
    if set(cached) != test_ids:
        raise ValueError("Cached SQL/logprob IDs do not match the test split")
    reserved = load(ROOT / "configs/reserved_words.json")
    from baseline_core import bottom_logprob
    for key, value in cached.items():
        if not isinstance(value, list) or len(value) != 2 or not isinstance(value[0], str) or not isinstance(value[1], list):
            raise ValueError(f"Malformed cached prediction: {key}")
        bottom_logprob(value[1], reserved)
    report = {"snapshot_verified": True, "baseline_rows": len(registry()),
              "splits": manifest["splits"], "inference_executed": False, "sql_executed": False}
    if emit:
        print(json.dumps(report, indent=2))
    return report


def preflight(split, timeout_s):
    report = verify(emit=False)
    manifest = load(ROOT / "source_manifest.json")
    gold = load(ROOT / "data/gold" / split / "label.json")
    errors, executed, empty, skipped = [], 0, 0, 0
    started = time.monotonic()
    for index, (key, sql) in enumerate(gold.items(), 1):
        if sql == "null":
            skipped += 1
        else:
            try:
                rows = execute_readonly(post_process_sql(sql), ROOT / manifest["database_path"], timeout_s)
                author_process_answer(rows)
                empty += not rows
                executed += 1
            except (sqlite3.Error, TypeError, ValueError) as error:
                errors.append({"id": key, "error": str(error)})
        if index % 100 == 0:
            print(f"Gold preflight: {index}/{len(gold)}", flush=True)
    report.update({"kind": "gold_preflight_not_model_evaluation", "split": split, "n": len(gold),
                   "gold_executed": executed, "gold_unanswerable": skipped, "gold_empty": empty,
                   "gold_errors": errors, "sql_timeout_s": timeout_s,
                   "elapsed_s": round(time.monotonic()-started, 3), "ready": not errors,
                   "sql_executed": True, "benchmark_scores_produced": False, "provenance": provenance()})
    return report


def summarize(run_dir, scorer, score_file="scores.json"):
    rows = []
    for experiment in registry():
        if not experiment["cached_predictions_available"]:
            continue
        scores = load(run_dir / experiment["id"] / score_file)
        if scores["split"] != experiment["split"] or scores["scorer"] != scorer:
            raise ValueError("Cannot mix splits or scorer modes in a comparison")
        comparison = {name: {"replayed": scores["scores"][name], "published": target,
                            "delta": round(scores["scores"][name]-target, 6),
                            "within_0_01_points": abs(scores["scores"][name]-target) <= 0.01+1e-9,
                            "matches_at_2_decimals": round(scores["scores"][name], 2) == target}
                      for name, target in zip(("RS0", "RS5", "RS10", "RSN"), experiment["published_scores"])}
        rows.append({"experiment": experiment["id"], "n": scores["n"], "comparison": comparison,
                     "execution_error_count": len(scores["execution_errors"]),
                     "postprocess": load(run_dir / experiment["id"] / "prediction.metadata.json")})
    return {"kind": "author_cache_replay_not_new_model_inference", "scorer": scorer,
            "paper_comparison_mode": scorer == "official", "experiments": rows,
            "comparison_note": "Official EHRSQL normalization is the main protocol; author raw helper is retained as a diagnostic. Strict two-decimal equality and absolute 0.01-point tolerance are both reported, without modifying published targets.",
            "all_published_scores_match_at_2_decimals": all(c["matches_at_2_decimals"] for row in rows for c in row["comparison"].values()),
            "all_published_scores_within_0_01_points": all(c["within_0_01_points"] for row in rows for c in row["comparison"].values()),
            "provenance": provenance()}


def predictions_from(raw):
    if isinstance(raw, list):
        if len({row["id"] for row in raw}) != len(raw):
            raise ValueError("Duplicate raw prediction IDs")
        return {r["id"]: post_process_sql(r["pred"]) for r in raw}
    return {key: post_process_sql(value if isinstance(value, str) else value[0]) for key, value in raw.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    subs.add_parser("verify")
    subs.add_parser("list")
    pre = subs.add_parser("preflight", help="Verify hashes and execute all gold SQL, without running a model")
    pre.add_argument("--split", choices=["dev", "test"], default="test")
    pre.add_argument("--sql-timeout", type=float, default=30)
    pre.add_argument("--output", type=Path, required=True)
    summary = subs.add_parser("summarize")
    summary.add_argument("--run-dir", type=Path, required=True)
    summary.add_argument("--scorer", choices=["author", "official"], required=True)
    summary.add_argument("--score-file", choices=["scores.json", "scores_official.json"], default="scores.json")
    summary.add_argument("--summary-file", choices=["comparison.json", "comparison_official.json"], default="comparison.json")
    plan = subs.add_parser("plan")
    plan.add_argument("--experiment", choices=[r["id"] for r in registry()])
    post = subs.add_parser("postprocess")
    post.add_argument("--experiment", required=True, choices=[r["id"] for r in registry()])
    post.add_argument("--raw", required=True, type=Path)
    post.add_argument("--classifier", type=Path)
    post.add_argument("--entropy-threshold", type=float)
    post.add_argument("--output", required=True, type=Path)
    post.add_argument("--sql-timeout", type=float, default=30)
    score = subs.add_parser("score")
    score.add_argument("--split", choices=["dev", "test"], required=True)
    score.add_argument("--predictions", type=Path, required=True)
    score.add_argument("--output", type=Path, required=True)
    score.add_argument("--scorer", choices=["author", "official"], default="official",
                       help="author: execute both gold/pred SQL with original raw comparison; official: stored gold, round 3 decimals, cap 100 rows")
    score.add_argument("--sql-timeout", type=float, default=30)
    args = parser.parse_args()
    if args.command == "verify":
        verify()
    elif args.command == "list":
        for row in registry():
            print(row["id"] + " | " + row["name"] + " | " + row["split"])
    elif args.command == "plan":
        rows = [get_experiment(args.experiment)] if args.experiment else registry()
        print(json.dumps({"mode": "plan_only", "experiments": rows}, ensure_ascii=False, indent=2))
    elif args.command == "preflight":
        report = preflight(args.split, args.sql_timeout)
        write_new(args.output, report)
        print(json.dumps(report, indent=2))
        if not report["ready"]:
            sys.exit("Gold SQL preflight failed; see report. No model was run.")
    elif args.command == "summarize":
        report = summarize(args.run_dir, args.scorer, args.score_file)
        write_new(args.run_dir / args.summary_file, report)
        for row in report["experiments"]:
            values = ", ".join(f"{name}={item['replayed']:.2f} (paper={item['published']:.2f})" for name, item in row["comparison"].items())
            print(row["experiment"] + ": " + values)
    elif args.command == "postprocess":
        verify(emit=False)
        row = get_experiment(args.experiment)
        raw = load(args.raw)
        manifest = load(ROOT / "source_manifest.json")
        ids = {r["id"] for r in load(ROOT / "data/inputs" / (row["split"] + ".json"))["data"]}
        predictions = predictions_from(raw)
        if set(predictions) != ids:
            raise ValueError("Raw outputs do not match the experiment split exactly")
        metadata = {"experiment": row["id"], "stages": [], "model_execution_performed": False,
                    "raw_sha256": hashlib.sha256(args.raw.read_bytes()).hexdigest(),
                    "sql_timeout_s": args.sql_timeout, "provenance": provenance()}
        for stage in row["stages"]:
            if stage == "probgate":
                predictions, detail = apply_probgate(raw, load(ROOT / "configs/reserved_words.json"), row["rank_index"], row["bottom_n"])
                metadata["stages"].append({"stage": stage, **detail})
            elif stage == "entropy_filter":
                if args.entropy_threshold is None or not isinstance(raw, list):
                    raise ValueError("Requires T5 evaluation records and a calibrated --entropy-threshold; no threshold is guessed")
                predictions = apply_entropy(predictions, {r["id"]: r["entropy"] for r in raw}, args.entropy_threshold)
            elif stage == "classifier":
                if args.classifier is None:
                    raise ValueError("Requires predictions from the named trained classifier")
                predictions = apply_classifier(predictions, load(args.classifier))
            elif stage == "gef":
                predictions, errors = apply_gef(predictions, ROOT / manifest["database_path"], args.sql_timeout)
                metadata["stages"].append({"stage": stage, "execution_errors": errors})
        write_new(args.output, predictions)
        write_new(args.output.with_suffix(".metadata.json"), metadata)
    else:
        verify(emit=False)
        manifest = load(ROOT / "source_manifest.json")
        predictions = load(args.predictions)
        gold = load(ROOT / "data/gold" / args.split / ("label.json" if args.scorer == "author" else "answer.json"))
        if set(predictions) != set(gold):
            raise ValueError("IDs differ; scoring refuses to drop questions")
        results, errors = {}, []
        if args.scorer == "author":
            executed_gold = {}
            for index, (key, sql) in enumerate(gold.items(), 1):
                executed_gold[key] = "null" if sql == "null" else execute_readonly(post_process_sql(sql), ROOT / manifest["database_path"], args.sql_timeout)
                if index % 100 == 0:
                    print(f"Execute gold: {index}/{len(gold)}", flush=True)
            gold = executed_gold
        for index, (key, sql) in enumerate(predictions.items(), 1):
            if index % 100 == 0:
                print(f"Score predictions: {index}/{len(predictions)}", flush=True)
            if sql == "null":
                results[key] = "null"
                continue
            try:
                result = execute_readonly(post_process_sql(sql), ROOT / manifest["database_path"], args.sql_timeout)
                results[key] = author_process_answer(result) if args.scorer == "author" else result
            except Exception as error:
                results[key] = "error_pred"
                errors.append({"id": key, "error": str(error)})
        metrics = score_answers(gold, results, scorer=args.scorer)
        metrics["scorer"] = args.scorer
        metrics["execution_errors"] = errors
        metrics["split"] = args.split
        metrics["source_manifest"] = "source_manifest.json"
        metrics["prediction_sha256"] = hashlib.sha256(args.predictions.read_bytes()).hexdigest()
        metrics["sql_timeout_s"] = args.sql_timeout
        metrics["provenance"] = provenance()
        write_new(args.output, metrics)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, StopIteration) as exc:
        sys.exit(str(exc))
