"""Read-only final audit of locked V6 SQL and saved English predictions.

Independent SQLite execution, SQL scoring and controlled-English fact parsing.
Lexical regrading deliberately uses the already locked/validated scorer.
No inference, credentials, policy fitting, or changes to existing run artifacts.
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
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
EXPERIMENTS = HERE.parent
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
V5_RUN = EXPERIMENTS / "ours_improved_v5/runs/deepseek_flash_v5_20261029_r1"
ENGLISH = EXPERIMENTS / "sql_to_text_evaluation"
DB = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
SYSTEMS = ("V5_frozen", "V6_dev_selected")


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=_object)


def lines(path):
    return [json.loads(line, object_pairs_hook=_object) for line in Path(path).read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(condition, explanation):
    if not condition:
        raise ValueError(explanation)


def close(actual, expected, explanation):
    check(isinstance(actual, (int, float)) and math.isfinite(actual) and abs(actual - expected) < 1e-9, explanation)


def sql_cell(value):
    try:
        value = round(float(value), 3)
    except (ValueError, TypeError):
        pass
    return str(value)


def official_answer(value):
    try:
        value = ast.literal_eval(value)
    except (ValueError, TypeError, SyntaxError):
        pass
    if isinstance(value, str):
        return value
    return str(sorted([[sql_cell(v) for v in row] for row in value])[:100])


def full_rows(rows):
    values = [[None if v is None else sql_cell(v) for v in row] for row in rows]
    return sorted(values, key=lambda row: tuple(("None" if v is None else v, v is not None) for v in row))


def execute(connection, sql, timeout=120):
    check(bool(sql.strip()), "Empty exported statement is not valid SQL")
    deadline = time.monotonic() + timeout
    connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    return connection.execute(sql).fetchall()


def independent_score(gold, sqls, connection):
    check(set(gold) == set(sqls), "Exact gold/prediction ID coverage required")
    details, correct = {}, 0
    wrong = abstained = execution_errors = correct_sql = 0
    for key, sql in sqls.items():
        check(isinstance(sql, str), "Prediction SQL must be text")
        if sql == "null":
            answer = "null"
        else:
            try:
                answer = execute(connection, sql)
            except (sqlite3.Error, ValueError):
                answer = "error_pred"
                execution_errors += 1
        if official_answer(gold[key]) == official_answer(answer):
            outcome = "correct"
            correct += 1
            correct_sql += gold[key] != "null"
        elif gold[key] != "null" and sql == "null":
            outcome = "abstained_answerable"
            abstained += 1
        else:
            outcome = "wrong"
            wrong += 1
        details[key] = outcome
    n = len(gold)
    answerable = sum(v != "null" for v in gold.values())
    answered = sum(v != "null" for v in sqls.values())
    return {"n": n, "correct": correct, "wrong": wrong, "abstained_answerable": abstained,
            "scores": {name: 100 * (correct - penalty * wrong) / n for name, penalty in
                       (("RS0", 0), ("RS5", 5), ("RS10", 10), ("RSN", n))},
            "EX": 100 * correct_sql / answerable,
            "VSR": 100 * (answered - execution_errors) / n,
            "coverage": 100 * answered / n,
            "answer_precision": 100 * correct_sql / answered if answered else None,
            "correct_answerable_sql": correct_sql, "execution_errors": execution_errors,
            "correct_abstentions": correct - correct_sql, "per_question": details}


def parse_English(text):
    if text == "This question cannot be answered using the available database.":
        return False, None
    if text == "The query returned no rows.":
        return True, []
    prefix = "The returned value is "
    if text.startswith(prefix) and text.endswith("."):
        rows = [[json.loads(text[len(prefix):-1])]]
    else:
        segments = text.split("\n")
        match = re.fullmatch(r"The query returned ([1-9][0-9]*) rows\.", segments[0])
        check(match is not None and len(segments) == int(match[1]) + 1, "Invalid English row header/count")
        rows = []
        for i, segment in enumerate(segments[1:], 1):
            start = f"Row {i}: "
            check(segment.startswith(start) and segment.endswith("."), "Invalid English row grammar")
            rows.append(json.loads(segment[len(start):-1]))
    check(all(isinstance(row, list) and row for row in rows), "Invalid English result shape")
    check(all(v is None or isinstance(v, str) for row in rows for v in row), "Noncanonical English scalar")
    normalized = full_rows(rows)
    if len(normalized) == 1 and len(normalized[0]) == 1:
        expected = prefix + json.dumps(normalized[0][0], ensure_ascii=False) + "."
    else:
        expected = "\n".join([f"The query returned {len(normalized)} rows."] +
                             [f"Row {i}: {json.dumps(row, ensure_ascii=False)}." for i, row in enumerate(normalized, 1)])
    check(expected == text, "Noncanonical or unparsed additional English claim")
    return True, normalized


def original_hash_check():
    lock = load(EXPERIMENTS / "research_validation/V5_LOCK.json")
    for name, expected in lock["files"].items():
        check(sha(WORKSPACE / name) == expected, "Frozen original changed: " + name)
    return len(lock["files"])


def audit(run, *, sql_only=False):
    started = time.monotonic()
    run = Path(run).resolve()
    check((run / "TEST_COMPLETE.json").is_file(), "Parent must finish the single locked test before audit")
    frozen_count = original_hash_check()
    db_hash = sha(DB)
    lock, protocol, policy = (load(run / name) for name in ("TEST_LOCK.json", "protocol.json", "policy.json"))
    check(sha(run / "policy.json") == lock["policy_sha256"], "Policy lock changed")
    check(sha(run / "protocol.json") == lock["protocol_sha256"], "Protocol lock changed")
    check(lock["selected_policy"] == policy["selected_policy"], "Selected policy inconsistent")
    for name, expected in lock["implementation_sha256"].items():
        path = ENGLISH / name.split("/", 1)[1] if name.startswith("english_dependency/") else HERE / name
        check(sha(path) == expected, "Locked implementation changed: " + name)
    check(sha(ENGLISH / "data/MANIFEST.json") == protocol["English_reference_manifest_sha256"], "English reference manifest changed")
    for split, expected in protocol["English_reference_sha256"].items():
        check(sha(ENGLISH / f"data/references/{split}.jsonl") == expected, "English reference file changed: " + split)
    for phase, expected in protocol["source_records_sha256"].items():
        check(sha(V5_RUN / phase / "records.jsonl") == expected, "Inherited candidate source changed: " + phase)
    completion = load(run / "TEST_COMPLETE.json")
    check(sha(run / "test/evaluation.json") == completion["evaluation_sha256"], "Completed SQL report changed")
    report = load(run / "test/evaluation.json")
    check(report["primary_policy"] == lock["selected_policy"], "Test used another policy")
    gold = load(BASELINE / "data/gold/test/answer.json")
    inputs = load(BASELINE / "data/inputs/test.json")["data"]
    ids = [row["id"] for row in inputs]
    check(len(ids) == len(set(ids)) == len(gold) == 1167 and set(ids) == set(gold), "Original full test coverage differs")
    conn = sqlite3.connect(DB.resolve().as_uri() + "?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON")
    systems, predictions = {}, {}
    try:
        for name in SYSTEMS:
            predictions[name] = load(run / "test" / (name + ".prediction.json"))
            fresh = independent_score(gold, predictions[name], conn)
            saved = report["systems"][name]
            for key in ("n", "correct", "wrong", "abstained_answerable", "correct_answerable_sql", "correct_abstentions", "execution_errors", "per_question"):
                check(fresh[key] == saved[key], "Fresh official result mismatch: " + name + "/" + key)
            for metric in ("EX", "VSR", "coverage", "answer_precision"):
                close(fresh[metric], saved[metric], "Saved metric differs: " + name + "/" + metric)
            for metric, value in fresh["scores"].items():
                close(value, saved["scores"][metric], "Saved RS differs: " + name + "/" + metric)
            systems[name] = {k: v for k, v in fresh.items() if k != "per_question"}
        historical = load(V5_RUN / "test/evaluation.json")["variants"]["v5_selected"]
        check(report["systems"]["V5_frozen"]["per_question"] == historical["per_question"], "V5 historical per-question outcomes changed")
        transition = Counter(report["systems"]["V5_frozen"]["per_question"][key] + " -> " + report["systems"]["V6_dev_selected"]["per_question"][key] for key in gold)
        check(dict(transition) == report["transitions_vs_V5"], "Transition counts differ")
        junit = ET.parse(HERE / "TEST_RESULTS.xml").getroot()
        suites = list(junit.iter("testsuite"))
        test_counts = {key: sum(int(s.attrib.get(key, 0)) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
        check(test_counts["tests"] == 114 and test_counts["failures"] == test_counts["errors"] == test_counts["skipped"] == 0,
              "Expected109 tests+5subtests/114passingJUnitcases")
        result = {"date": "2026-11-01", "state": "SQL_verified_English_pending" if sql_only else "fully_verified",
                  "new_model_API_calls": 0, "run": str(run), "selected_policy": lock["selected_policy"],
                  "frozen_original_files_verified": frozen_count, "SQL_fresh_replay": systems,
                  "all_2_times_1167_per_question_SQL_outcomes_match": True,
                  "V5_matches_historical": True, "transitions_vs_V5": dict(transition),
                  "unit_tests": test_counts, "test_count_note": "109 test functions plus5successfulsubtests are114JUnitcases",
                  "policy_protocol_and_implementation_unchanged": True,
                  "English_reference_manifest_locked_and_unchanged": True,
                  "English": {}, "reviewed_without_method_edits_after_test": True}
        if not sql_only:
            # Load original postprocessing only, never the production renderer.
            spec = importlib.util.spec_from_file_location("final_audit_author_postprocess", BASELINE / "upstream/src/scoring_program/postprocessing.py")
            postprocess = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(postprocess)
            for name in SYSTEMS:
                directory = run / "english" / name
                saved = load(directory / "ENGLISH_EVALUATION.json")
                scores = load(directory / "english_scores.json")
                records = lines(directory / "english_predictions.jsonl")
                check(saved["state"] == "complete" and saved["mode"] == "end_to_end", "English run incomplete or oracle substituted: " + name)
                check(saved["gold_SQL_used_to_generate_end_to_end_answers"] is False and saved["reference_English_used_to_generate_answers"] is False,
                      "English provenance incorrectly allows gold substitution")
                check(len(records) == 1167 and {r["id"] for r in records} == set(gold), "English IDs missing/extra/duplicated")
                check(sha(directory / "english_predictions.jsonl") == saved["English_prediction_sha256"], "Saved English predictions changed")
                check(sha(directory / "english_scores.json") == saved["scores_sha256"], "Saved English scores changed")
                check(saved["prediction_source"]["sha256"] == sha(run / "test" / (name + ".prediction.json")), "English used another system SQL mapping")
                actual_status = Counter()
                for row in records:
                    sql = predictions[name][row["id"]]
                    check(row["sql_prediction"] == sql, "English output substituted a different SQL")
                    if sql == "null":
                        expected_status, expected = "abstained", (False, None)
                    else:
                        processed = postprocess.post_process_sql(sql)
                        try:
                            rows = execute(conn, processed)
                            expected_status, expected = "executed", (True, full_rows(rows))
                        except (sqlite3.Error, ValueError):
                            expected_status, expected = "execution_error", None
                        if expected_status == "executed":
                            check(row["executed_sql"] == processed, "English executed SQL differs from declared prediction/postprocessing")
                    check(row["status"] == expected_status, "English status differs from actual predicted-SQL execution")
                    actual_status[expected_status] += 1
                    if expected_status == "execution_error":
                        check(row["output_text"] == "The system could not execute the query.", "Failed SQL became another answer/refusal")
                    else:
                        check(parse_English(row["output_text"]) == expected, "English text does not preserve actual predicted SQL result")
                check(dict(actual_status) == saved["execution_status_counts"], "English status totals differ")
                # Only after text-vs-predicted-SQL checks, inspect reference English.
                refs = lines(ENGLISH / "data/references/test.jsonl")
                by_id = {row["id"]: row for row in records}
                correct = parseable = 0
                for ref in refs:
                    check(parse_English(ref["output_text"]) == (ref["answerable"], ref["result_rows"]), "Reference English contradicts structured facts")
                    try:
                        parsed = parse_English(by_id[ref["id"]]["output_text"])
                        parseable += 1
                        correct += parsed == (ref["answerable"], ref["result_rows"])
                    except (ValueError, json.JSONDecodeError):
                        pass
                close(100 * correct / 1167, scores["controlled"]["fact_EM"], "Independent English factEM differs")
                close(100 * parseable / 1167, scores["controlled"]["parse_coverage"], "Independent English parse coverage differs")
                # Lexical algorithm was separately independently audited; replay
                # it here on the exact files whose facts were just checked.
                sys.path.insert(0, str(WORKSPACE))
                from experiments.sql_to_text_evaluation.english_metrics import score_records
                replay = score_records(refs, records)
                check(replay["per_question"] == scores["per_question"], "English regrading per-question differs")
                check(replay["lexical"] == scores["lexical"] and replay["groups"] == scores["groups"], "English aggregate regrading differs")
                result["English"][name] = {"n": 1167, "text_facts_match_predicted_SQL_execution": 1167,
                                            "gold_SQL_substitution": False, "status_counts": dict(actual_status),
                                            "independent_controlled_fact_EM": 100 * correct / 1167,
                                            "lexical_replay_matches": True, "scores": scores["lexical"]}
        check(sha(DB) == db_hash, "Database changed during readonly audit")
        check(original_hash_check() == frozen_count, "Original file lock changed")
        result.update(database_unchanged=True, errors=[], elapsed_seconds=time.monotonic() - started,
                      scope_limits=["English uses deterministic controlled-language renderer, not an LLM",
                                    "English full numeric3 facts have no100rowcap; SQL officialscorecaps100",
                                    "No claim of expert clinical validation or independent research superiority"])
        (HERE / "FINAL_AUDIT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        text = ["# Final audit V6 — 01/11/2026", "", f"Trạng thái: {result['state']}. Không API/model call, không chỉnh phương pháp.", "",
                "Policy/protocol/code và reference manifest khớp lock;147 file gốc và database nguyên vẹn.",
                "Fresh SQLite read-only + normalizer/scorer độc lập khớp toàn bộ2×1.167 kết quả chấm SQL; V5 khớp lịch sử.",
                "109 test và5 subtest đạt (114caseJUnit).", ""]
        for name, value in systems.items():
            text.append(f"- {name}: RS10={value['scores']['RS10']:.8f}; EX={value['EX']:.8f}%; VSR={value['VSR']:.8f}%; wrong={value['wrong']}.")
        text += ["", "Transitions V5→V6: " + json.dumps(dict(transition), ensure_ascii=False) + ".", ""]
        for name, value in result["English"].items():
            text.append(f"- English {name}:1167/1167 output đã đối chiếu trực tiếp với kết quả SQL prediction; fact-EM độc lập={value['independent_controlled_fact_EM']:.8f}%; không thay bằng goldSQL.")
        text += ["", "English là renderer theo mẫu, không phải LLM sinh tự do hoặc gold được chuyên gia duyệt. Full-result English không cap100, khác quy ước officialSQL; không so như cùng metric. Lexical replay dùng scorer đã khóa, còn SQL scoring và English fact parsing/thực thi trong audit này là độc lập."]
        (HERE / "FINAL_AUDIT.md").write_text("\n".join(text) + "\n", encoding="utf-8")
        print(json.dumps({"state": result["state"], "policy": result["selected_policy"], "SQL_systems": len(systems), "English_systems": len(result["English"]), "errors": 0}, ensure_ascii=False))
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--sql-only", action="store_true", help="Before English reports finish, verify SQL and explicitly mark English pending")
    args = parser.parse_args()
    audit(args.run_dir, sql_only=args.sql_only)
