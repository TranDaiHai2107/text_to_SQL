"""Offline English -> predicted SQL -> result -> controlled-English evaluation.

The answer generator is the existing deterministic renderer, NOT an LLM.
End-to-end mode never reads gold SQL or reference English before saving answers.
Oracle mode is explicitly a gold-SQL renderer functionality baseline.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
if str(WORKSPACE) not in sys.path:
    sys.path.insert(1, str(WORKSPACE))

from experiments.sql_to_text_evaluation.answer_from_sql import verbalize
from experiments.sql_to_text_evaluation.common_io import DATABASE, verify_frozen
from experiments.sql_to_text_evaluation.english_metrics import load_records, score_records
from experiments.sql_to_text_evaluation.reference_renderer import RENDERER_VERSION

ENGLISH = WORKSPACE / "experiments/sql_to_text_evaluation"
SPLITS = ("train", "validation", "test")
MODES = ("end_to_end", "oracle_renderer")


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(2**20), b""):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _inputs(path):
    rows = load_records(path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Clean input must be a nonempty JSONL/list")
    ids = []
    for row in rows:
        if (not isinstance(row, dict) or set(row) != {"id", "input_text"}
                or not isinstance(row["id"], str) or not row["id"]
                or not isinstance(row["input_text"], str)):
            raise ValueError("Question-only input must contain exactly id and input_text")
        ids.append(row["id"])
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate question input IDs")
    return rows


def _sql_mapping(value):
    if (not isinstance(value, dict) or not value
            or any(not isinstance(k, str) or not k or not isinstance(v, str) for k, v in value.items())):
        raise ValueError("SQL predictions must be a nonempty ID-to-SQL-string JSON mapping")
    return value


def evaluate(*, output_dir, sql_predictions=None, split="test", mode="end_to_end", timeout_s=30,
             inputs_path=None, references_path=None, database=DATABASE, oracle_input_path=None,
             verify_originals=True):
    """Save English predictions FIRST, then load gold English solely for scoring.

    Path overrides and verify_originals=False support isolated synthetic tests.
    Public CLI uses the pinned EHRSQL inputs, references and original database.
    """
    if split not in SPLITS or mode not in MODES:
        raise ValueError("Unknown split or task mode")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("SQL timeout must be finite and positive")
    if mode == "end_to_end" and sql_predictions is None:
        raise ValueError("End-to-end mode requires predictions produced by a SQL system")
    if mode == "oracle_renderer" and sql_predictions is not None:
        raise ValueError("Oracle mode must not be confused with a system prediction file")
    destination = Path(output_dir).resolve()
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("Use a new/empty output directory; historical outputs cannot be overwritten")
    input_file = Path(inputs_path) if inputs_path is not None else ENGLISH / f"data/inputs/{split}.jsonl"
    reference_file = Path(references_path) if references_path is not None else ENGLISH / f"data/references/{split}.jsonl"
    database = Path(database)
    original_files = verify_frozen() if verify_originals else None
    database_hash = sha(database)
    started = time.monotonic()
    events = ["question_only_inputs_loaded"]
    inputs = _inputs(input_file)
    input_hash = sha(input_file)
    if mode == "end_to_end":
        prediction_file = Path(sql_predictions)
        sqls = _sql_mapping(load_records(prediction_file))
        prediction_source = {"kind": "system_SQL_predictions", "path": str(prediction_file.resolve()),
                             "sha256": sha(prediction_file)}
    else:
        component_file = Path(oracle_input_path) if oracle_input_path is not None else ENGLISH / f"data/sql_to_text_inputs/{split}.jsonl"
        components = load_records(component_file)
        if (not isinstance(components, list) or len(components) != len(inputs)
                or [r.get("id") for r in components] != [r["id"] for r in inputs]):
            raise ValueError("Oracle component inputs must cover question IDs exactly in source order")
        if any("output_text" in row for row in components):
            raise ValueError("Oracle generation input must not contain reference English")
        sqls = _sql_mapping({row["id"]: row["input_sql"] for row in components})
        prediction_source = {"kind": "gold_SQL_oracle_component_inputs", "path": str(component_file.resolve()),
                             "sha256": sha(component_file)}
    events.append("SQL_inputs_loaded_without_reference_English")
    # This function reads predicted SQL, question IDs and the read-only database.
    # It has no gold reference parameter and does not infer correct answers.
    answers = verbalize(sqls, inputs, database=database, timeout_s=timeout_s)
    destination.mkdir(parents=True, exist_ok=True)
    answer_file = destination / "english_predictions.jsonl"
    answer_file.write_text("".join(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n" for row in answers), encoding="utf-8")
    answer_hash = sha(answer_file)
    events.append("English_predictions_saved_before_loading_reference_English")
    # References become visible ONLY after predictions are durable.
    refs = load_records(reference_file)
    events.append("reference_English_loaded_for_scoring_only")
    if references_path is None:
        manifest = load_records(ENGLISH / "data/MANIFEST.json")
        if sha(reference_file) != manifest["splits"][split]["reference_sha256"]:
            raise ValueError("Reference English no longer matches its audited dataset manifest")
    scores = score_records(refs, load_records(answer_file))
    events.append("all_IDs_scored_without_dropping_failed_outputs")
    task = ("English_question_to_predicted_SQL_to_controlled_English" if mode == "end_to_end"
            else "gold_SQL_to_controlled_English_renderer_functionality_oracle")
    scores.update(task=task, mode=mode, generator="deterministic_controlled_English_renderer_NOT_LLM",
                  official_paper_metric=False, LLM_English_generation_evaluated=False,
                  oracle_is_not_system_performance=mode == "oracle_renderer")
    dump(destination / "english_scores.json", scores)
    if sha(answer_file) != answer_hash:
        raise ValueError("English predictions changed during scoring")
    if sha(database) != database_hash:
        raise ValueError("Database changed during read-only evaluation")
    if sha(input_file) != input_hash or sha(Path(prediction_source["path"])) != prediction_source["sha256"]:
        raise ValueError("Question/SQL generation inputs changed during evaluation")
    if verify_originals:
        verify_frozen()
    status_counts = dict(Counter(row["status"] for row in answers))
    report = {
        "state": "complete", "task": task, "mode": mode, "split": split,
        "questions": scores["n"], "execution_status_counts": status_counts,
        "generator": "deterministic_controlled_English_renderer_NOT_LLM",
        "renderer_version": RENDERER_VERSION, "new_model_API_calls": 0,
        "gold_SQL_used_to_generate_end_to_end_answers": False if mode == "end_to_end" else True,
        "reference_English_used_to_generate_answers": False,
        "oracle_is_not_system_performance": mode == "oracle_renderer",
        "scoring_order": events, "frozen_original_files_verified": original_files,
        "database_sha256_before_and_after": database_hash,
        "prediction_source": prediction_source,
        "input_path": str(input_file.resolve()), "input_sha256": input_hash,
        "reference_path": str(reference_file.resolve()), "reference_sha256": sha(reference_file),
        "English_prediction_sha256": answer_hash,
        "scores_sha256": sha(destination / "english_scores.json"),
        "implementation_sha256": {p.name: sha(p) for p in [Path(__file__), ENGLISH / "answer_from_sql.py",
                                    ENGLISH / "reference_renderer.py", ENGLISH / "english_metrics.py"]},
        "lexical": scores["lexical"], "controlled": scores["controlled"], "groups": scores["groups"],
        "elapsed_seconds": time.monotonic() - started,
        "interpretation": [
            "Actual saved predicted SQL is executed and rendered; failed SQL remains an English execution failure, never a correct refusal.",
            "English reference labels are generated silver controlled-language answers, not official paper English-answer gold or clinician review.",
            "Fact EM evaluates full numeric3 results with no100-row cap and exact controlled grammar; it is not the paper SQL metric.",
            "Lexical similarity and renderer oracle accuracy do not establish free-form clinical language quality.",
        ],
    }
    dump(destination / "ENGLISH_EVALUATION.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sql-predictions", type=Path)
    parser.add_argument("--split", choices=SPLITS, default="test")
    parser.add_argument("--mode", choices=MODES, default="end_to_end")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--sql-timeout", type=float, default=30)
    args = parser.parse_args()
    report = evaluate(output_dir=args.output_dir, sql_predictions=args.sql_predictions,
                      split=args.split, mode=args.mode, timeout_s=args.sql_timeout)
    print(json.dumps({k: report[k] for k in ("state", "task", "questions", "execution_status_counts", "lexical", "controlled")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
