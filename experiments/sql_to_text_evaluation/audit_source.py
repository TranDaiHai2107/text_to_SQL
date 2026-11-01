"""Independent offline audit of EHRSQL source SQL/answer pairs.

Writes only into this extension. It never edits the official splits or database,
and makes no model/API calls. This is a programmatic data audit, not clinical
validation or a natural-language quality guarantee.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sqlite3
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
DATABASE = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
POSTPROCESS = BASELINE / "upstream/src/scoring_program/postprocessing.py"


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def cell(value):
    # Independent implementation of official numeric3 normalization.
    try:
        return str(round(float(value), 3))
    except (ValueError, TypeError, OverflowError):
        return str(value)


def canonical(rows):
    return sorted([[cell(v) for v in row] for row in rows])


def object_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def processed_sql(sql):
    spec = importlib.util.spec_from_file_location("sqltext_source_audit_postprocess", POSTPROCESS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.post_process_sql(sql)


def audit(output=HERE, timeout=30.0):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    files = [DATABASE, POSTPROCESS]
    for split in ("train", "dev", "test"):
        files += [BASELINE / f"data/inputs/{split}.json",
                  BASELINE / f"data/gold/{split}/label.json",
                  BASELINE / f"data/gold/{split}/answer.json"]
    before = {str(p.relative_to(WORKSPACE)).replace("\\", "/"): digest(p) for p in files}
    totals, summaries, failures, known_truncations, seen_ids = Counter(), {}, [], [], set()
    all_max_rows = 0
    details = []
    connection = sqlite3.connect(DATABASE.resolve().as_uri() + "?mode=ro", uri=True)
    connection.text_factory = lambda value: value.decode(errors="ignore")
    connection.execute("PRAGMA query_only=ON")
    try:
        for split in ("train", "dev", "test"):
            questions = load(BASELINE / f"data/inputs/{split}.json")["data"]
            labels = load(BASELINE / f"data/gold/{split}/label.json")
            answers = load(BASELINE / f"data/gold/{split}/answer.json")
            counts = Counter()
            max_rows = 0
            if set(r["id"] for r in questions) != set(labels) or set(labels) != set(answers):
                raise ValueError(f"ID coverage mismatch for {split}")
            if len(questions) != len(labels):
                raise ValueError(f"Duplicate IDs in {split}")
            for question in questions:
                key, text = question["id"], question["question"]
                sql, answer = labels[key], answers[key]
                if key in seen_ids:
                    raise ValueError(f"Cross-split ID duplication: {key}")
                seen_ids.add(key)
                counts["questions"] += 1
                detail = {"split": split, "id": key}
                if sql == "null":
                    counts["unanswerable"] += 1
                    match = answer == "null"
                    detail.update({"status": "unanswerable", "gold_consistent": match})
                    if not match:
                        failures.append({"split": split, "id": key, "reason": "null_sql_nonnull_answer"})
                    details.append(detail)
                    continue
                counts["answerable"] += 1
                if not re.match(r"^\s*(?:select|with)\b", sql, re.I):
                    raise ValueError(f"Non-read-query gold SQL: {key}")
                try:
                    deadline = time.monotonic() + timeout
                    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                    cursor = connection.execute(processed_sql(sql))
                    columns = [description[0] for description in cursor.description]
                    raw_rows = cursor.fetchall()
                    max_rows = max(max_rows, len(raw_rows))
                    actual = canonical(raw_rows)
                    expected = ast.literal_eval(answer)
                    expected_canonical = canonical(expected)
                    official_equal = actual[:100] == expected_canonical[:100]
                    full_equal = actual == expected_canonical
                    counts["executed"] += 1
                    counts["official_equal"] += int(official_equal)
                    counts["full_equal"] += int(full_equal)
                    counts["empty_result"] += int(not raw_rows)
                    counts["result_over_100_rows"] += int(len(raw_rows) > 100)
                    counts["multiple_columns"] += int(len(columns) > 1)
                    counts["scalar"] += int(len(raw_rows) == 1 and len(columns) == 1)
                    counts["contains_sql_null"] += int(any(v is None for row in raw_rows for v in row))
                    counts["duplicate_rows"] += int(len({tuple(r) for r in actual}) < len(actual))
                    counts["percentile_question"] += int("percentile" in text.lower())
                    counts["cost_question"] += int(bool(re.search(r"\b(?:cost|pay|price)\b", text, re.I)))
                    counts["yes_no_question"] += int(bool(re.match(r"(?:is|are|was|were|does|do|did|has|have|had|can)\b", text, re.I)))
                    counts["top_k_question"] += int(bool(re.search(r"\btop\s+(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\b", text, re.I)))
                    counts["dense_rank_sql"] += int("DENSE_RANK" in sql.upper())
                    counts["clock_substitution"] += int("current_time" in sql)
                    counts["gold_sql_null_cell_strings"] += int(any(v == "None" for r in expected for v in r))
                    counts["nonfinite_numeric_cell"] += int(any(isinstance(v, float) and not math.isfinite(v) for row in raw_rows for v in row))
                    counts["control_character_cell"] += int(any(isinstance(v, str) and any(ord(ch) < 32 for ch in v) for row in raw_rows for v in row))
                    detail.update({"status": "executed", "official_equal": official_equal,
                                   "full_equal": full_equal, "execution_row_count": len(raw_rows),
                                   "gold_row_count": len(expected), "column_count": len(columns),
                                   "has_sql_null": any(v is None for row in raw_rows for v in row),
                                   "has_duplicate_rows": len({tuple(r) for r in actual}) < len(actual),
                                   "columns": columns,
                                   "numeric3_full_sha256": object_digest(actual),
                                   "numeric3_gold_sha256": object_digest(expected_canonical)})
                    if not official_equal:
                        failures.append({"split": split, "id": key, "reason": "official_answer_mismatch",
                                         "actual": actual, "gold": expected_canonical})
                    elif not full_equal:
                        if len(expected) == 100 and len(actual) > 100 and actual[:100] == expected_canonical:
                            known_truncations.append({"split": split, "id": key, "reason": "released_gold_answer_cap100",
                                                      "actual_row_count": len(actual), "gold_row_count": len(expected)})
                        else:
                            failures.append({"split": split, "id": key, "reason": "unexpected_full_answer_mismatch",
                                             "actual_row_count": len(actual), "gold_row_count": len(expected)})
                except (sqlite3.Error, ValueError, TypeError, SyntaxError) as error:
                    counts["execution_or_parse_errors"] += 1
                    detail.update({"status": "error", "error": str(error)})
                    failures.append({"split": split, "id": key, "reason": "execution_or_parse_error", "error": str(error)})
                details.append(detail)
            summaries[split] = dict(counts)
            summaries[split]["max_execution_rows"] = max_rows
            all_max_rows = max(all_max_rows, max_rows)
            totals.update(counts)
    finally:
        connection.close()
    after = {str(p.relative_to(WORKSPACE)).replace("\\", "/"): digest(p) for p in files}
    if before != after:
        raise ValueError("Source file hash changed during independent audit")
    report = {
        "status": "passed" if not failures else "requires_review",
        "scope": "All existing EHRSQL2024 source question, gold SQL and gold execution-answer pairs",
        "clinical_or_human_validation": False,
        "new_model_API_calls": 0,
        "database_opened_readonly": True,
        "fixed_current_time": "2100-12-31 23:59:00",
        "normalization": "round numeric-convertible cells to 3 decimals; preserve strings, tuples, duplicates; sort rows lexicographically; report both full rows and official cap100",
        "totals": dict(totals), "splits": summaries,
        "max_execution_rows": all_max_rows,
        "failure_count": len(failures), "failures": failures,
        "known_gold_truncation_count": len(known_truncations),
        "known_gold_truncations": known_truncations,
        "source_files_unchanged": True, "source_sha256": before,
        "sqlite_version": sqlite3.sqlite_version,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "caveats": [
            "Unanswerable SQL sentinel 'null' means cannot answer from benchmark data, not an empty result and not a negative clinical claim.",
            "DENSE_RANK ties can return more rows than the requested top-k; retain all rows and do not assert a strict rank order.",
            "Do not invent units or currency absent from SQL result/evidence.",
            "PERCENT_RANK output is a fraction; do not silently multiply by100 or call a rounded value a clinical percentile without a declared rule.",
            "Numeric3 database agreement is not validation of natural-language entailment, fluency, or clinical suitability.",
            "Official answer normalization discards order; gold execution answers cannot support ordering claims without separately proving the SQL semantics.",
            "SQL NULL cells are distinct from the benchmark unanswerable sentinel and zero counts.",
            "Source question and SQL can contain mismatched natural-language scope; this audit confirms the released SQL-answer relationship, not clinical intent."
        ]
    }
    (output / "SOURCE_AUDIT.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "SOURCE_EXECUTION_AUDIT.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in details), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    result = audit(args.output, args.timeout)
    print(json.dumps({k: result[k] for k in ("status", "totals", "failure_count", "elapsed_seconds")}, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "passed" else 1)
