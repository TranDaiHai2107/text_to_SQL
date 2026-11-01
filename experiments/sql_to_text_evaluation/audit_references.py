"""Independently check every derived English answer against fresh gold SQL.

Intentionally does not import the builder or renderer: its own grammar parser,
normalization, SQL connection and CSV checks exercise different code paths.
This is exhaustive mechanical validation, not human/clinical review.
"""
from __future__ import annotations

import argparse
import ast
from collections import Counter
import csv
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
DB = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
ABSTENTION = "This question cannot be answered using the available database."
EMPTY = "The query returned no rows."


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_value(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return str(value)
    if not math.isfinite(number):
        raise ValueError("Nonfinite value")
    return str(round(number, 3))


def normalize_full(rows):
    result = [[normalize_value(v) for v in row] for row in rows]
    return sorted(result, key=lambda row: tuple(("None" if v is None else v, v is not None) for v in row))


def independent_parse(text):
    if text == ABSTENTION:
        return False, None
    if text == EMPTY:
        return True, []
    prefix = "The returned value is "
    if text.startswith(prefix) and text.endswith("."):
        rows = [[json.loads(text[len(prefix):-1])]]
    else:
        parts = text.split("\n")
        match = re.fullmatch(r"The query returned ([1-9][0-9]*) rows\.", parts[0])
        if match is None or len(parts) != int(match[1]) + 1:
            raise ValueError("Bad English row-count header")
        rows = []
        for index, line in enumerate(parts[1:], 1):
            start = f"Row {index}: "
            if not line.startswith(start) or not line.endswith("."):
                raise ValueError("Bad row grammar")
            value = json.loads(line[len(start):-1])
            if not isinstance(value, list) or not value:
                raise ValueError("Invalid row shape")
            rows.append(value)
    if any(v is not None and not isinstance(v, str) for row in rows for v in row):
        raise ValueError("Noncanonical scalar type")
    if rows and any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("Inconsistent row width")
    # Never discard unparsed trailing prose or extra facts.
    if len(rows) == 1 and len(rows[0]) == 1:
        expected = "The returned value is " + json.dumps(rows[0][0], ensure_ascii=False) + "."
    else:
        expected = "\n".join([f"The query returned {len(rows)} rows."] +
                             [f"Row {i}: {json.dumps(row, ensure_ascii=False)}." for i, row in enumerate(rows, 1)])
    if text != expected:
        raise ValueError("Unexpected prose or noncanonical serialization")
    return True, rows


def audit(data=HERE / "data", output=HERE / "REFERENCE_AUDIT.json", timeout=120.0):
    data, output = Path(data), Path(output)
    started = time.monotonic()
    manifest = load(data / "MANIFEST.json")
    errors, totals, split_results = [], Counter(), {}
    if manifest.get("official_English_benchmark") is not False or manifest.get("human_or_clinician_validated") is not False:
        raise ValueError("Misleading official/human label")
    if manifest.get("text_result_row_cap") is not None:
        raise ValueError("Full-result references must not silently truncate rows")
    source_hashes = {name: sha(WORKSPACE / name) for name in manifest["source_sha256"]}
    if source_hashes != manifest["source_sha256"]:
        raise ValueError("Source manifest mismatch")
    for name, expected in manifest["implementation_sha256"].items():
        if sha(HERE / name) != expected:
            raise ValueError("Builder implementation hash changed: " + name)
    lock = load(WORKSPACE / "experiments/research_validation/V5_LOCK.json")
    if any(sha(WORKSPACE / path) != expected for path, expected in lock["files"].items()):
        raise ValueError("Original frozen files changed")
    spec = importlib.util.spec_from_file_location("independent_reference_audit_postprocess", BASELINE / "upstream/src/scoring_program/postprocessing.py")
    postprocess = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(postprocess)
    connection = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    connection.execute("PRAGMA query_only=ON")
    connection.text_factory = lambda value: value.decode(errors="ignore")
    try:
        for split, original in (("train", "train"), ("validation", "dev"), ("test", "test")):
            counts = Counter()
            questions = load(BASELINE / f"data/inputs/{original}.json")["data"]
            sqls = load(BASELINE / f"data/gold/{original}/label.json")
            gold = load(BASELINE / f"data/gold/{original}/answer.json")
            references = read_jsonl(data / "references" / f"{split}.jsonl")
            clean = read_jsonl(data / "inputs" / f"{split}.jsonl")
            verbalizer = read_jsonl(data / "sql_to_text_inputs" / f"{split}.jsonl")
            with (data / "references" / f"{split}.csv").open(encoding="utf-8-sig", newline="") as stream:
                csv_rows = list(csv.DictReader(stream))
            source_ids = [q["id"] for q in questions]
            if [r["id"] for r in references] != source_ids or [r["id"] for r in csv_rows] != source_ids:
                raise ValueError("Reference ordering/coverage mismatch: " + split)
            if clean != [{"id": q["id"], "input_text": q["question"]} for q in questions]:
                raise ValueError("Input file includes labels or differs from source: " + split)
            expected_verbalizer = [{"id": r["id"], "input_text": r["input_text"],
                                    "input_sql": r["input_sql"], "executable_sql": r["executable_gold_sql"],
                                    "result_rows": r["result_rows"], "answerable": r["answerable"]}
                                   for r in references]
            if verbalizer != expected_verbalizer:
                raise ValueError("SQL-to-text input differs or includes reference English: " + split)
            counts["clean_input_rows_verified"] = len(clean)
            counts["isolated_verbalizer_input_rows_verified"] = len(verbalizer)
            for q, reference, csv_row in zip(questions, references, csv_rows):
                key = q["id"]
                counts["references"] += 1
                try:
                    if reference["id"] != key or reference["input_text"] != q["question"] or reference["input_sql"] != sqls[key]:
                        raise ValueError("Original input/question/SQL changed")
                    if reference["official_gold_answer"] != gold[key] or reference["source_split"] != original or reference["split"] != split:
                        raise ValueError("Original answer/split changed")
                    if reference["annotation_status"] != "automatic_reference_not_human_validated":
                        raise ValueError("Misleading annotation status")
                    csv_expected = {k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else ("" if v is None else str(v)) for k, v in reference.items()}
                    if csv_expected != csv_row:
                        raise ValueError("CSV/JSONL mismatch")
                    counts["csv_roundtrip_verified"] += 1
                    answerable = sqls[key] != "null"
                    if reference["answerable"] is not answerable:
                        raise ValueError("Answerability changed")
                    if not answerable:
                        expected_rows = None
                        if gold[key] != "null" or reference["executable_gold_sql"] is not None or reference["full_result_rows"] is not None:
                            raise ValueError("Unanswerable source mismatch")
                        counts["unanswerable_verified"] += 1
                    else:
                        processed = postprocess.post_process_sql(sqls[key])
                        if reference["executable_gold_sql"] != processed:
                            raise ValueError("Executable SQL/clock mismatch")
                        deadline = time.monotonic() + timeout
                        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
                        raw = connection.execute(processed).fetchall()
                        expected_rows = normalize_full(raw)
                        if expected_rows[:100] != normalize_full(ast.literal_eval(gold[key]))[:100]:
                            raise ValueError("Fresh SQL differs from official gold")
                        if reference["full_result_rows"] != len(raw):
                            raise ValueError("Result row count differs")
                        if reference["official_gold_uses_100_row_cap"] is not (len(raw) > 100):
                            raise ValueError("Cap warning incorrect")
                        counts["fresh_sql_execution_verified"] += 1
                        counts["full_results_beyond_official_100_preserved"] += int(len(raw) > 100)
                        counts["empty_results_verified"] += int(not raw)
                    parsed_answerable, parsed_rows = independent_parse(reference["output_text"])
                    if parsed_answerable is not answerable or parsed_rows != expected_rows or reference["result_rows"] != expected_rows:
                        raise ValueError("Text changes result facts or row multiplicity/order")
                    counts["independent_text_facts_verified"] += 1
                except (ValueError, TypeError, KeyError, SyntaxError, sqlite3.Error) as error:
                    errors.append({"split": split, "id": key, "error": str(error)})
            expected_hashes = manifest["splits"][split]
            for folder, extension, field in (("references", "jsonl", "reference_sha256"), ("references", "csv", "csv_sha256"), ("inputs", "jsonl", "input_sha256"), ("sql_to_text_inputs", "jsonl", "sql_to_text_input_sha256")):
                if sha(data / folder / f"{split}.{extension}") != expected_hashes[field]:
                    raise ValueError("Extension manifest hash differs: " + split + ":" + field)
            split_results[split] = dict(counts)
            totals.update(counts)
    finally:
        connection.close()
    if source_hashes != {name: sha(WORKSPACE / name) for name in source_hashes}:
        raise ValueError("Source changed during verification")
    report = {
        "status": "passed" if not errors else "failed", "new_model_API_calls": 0,
        "human_or_clinician_validated": False,
        "audit_method": "Independent grammar parser plus independent fresh read-only SQL execution, numeric3 full rows without cap; input, CSV, source and frozen code hashes checked",
        "independent_of_builder_and_renderer_imports": True,
        "totals": dict(totals), "splits": split_results,
        "errors": errors, "error_count": len(errors),
        "original_files_unchanged": True, "frozen_files_verified": len(lock["files"]),
        "source_sha256": source_hashes,
        "reference_manifest_sha256": sha(data / "MANIFEST.json"),
        "audit_script_sha256": sha(Path(__file__)),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "limitations": [
            "Pass certifies this controlled English format preserves executed gold results under declared numeric3 equivalence.",
            "It does not validate clinical correctness, original question-to-SQL semantic correctness, free-form language quality, or expert acceptance.",
            "This is reference-dataset verification; existing systems have not thereby been evaluated on SQL-to-text generation.",
            "Clean input exports contain only IDs and English questions; original held-out test references remain evaluation-only."
        ]
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("status", "totals", "error_count", "elapsed_seconds")}))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=HERE / "data")
    parser.add_argument("--output", type=Path, default=HERE / "REFERENCE_AUDIT.json")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    result = audit(args.data, args.output, args.timeout)
    raise SystemExit(0 if result["status"] == "passed" else 1)
