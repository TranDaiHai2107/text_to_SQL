"""Independent adversarial audit of the English metrics; no API/model calls.

Records each run so fixes can be verified without hiding the initial findings.
Only files in this audit folder and unique workspace temp files are written.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import itertools
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[1]
WORKSPACE = PACKAGE.parents[1]
sys.path.insert(0, str(PACKAGE))
from english_metrics import edit_distance, lcs_length, load_records, score_records
from reference_renderer import ABSTENTION_TEXT, EMPTY_TEXT, EXECUTION_ERROR_TEXT, render_answer
from answer_from_sql import verbalize


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def independent_dp(a, b):
    distance = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    lcs = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        distance[i][0] = i
    for j in range(len(b) + 1):
        distance[0][j] = j
    for i, x in enumerate(a, 1):
        for j, y in enumerate(b, 1):
            distance[i][j] = min(distance[i-1][j]+1, distance[i][j-1]+1,
                                 distance[i-1][j-1]+(x != y))
            lcs[i][j] = lcs[i-1][j-1]+1 if x == y else max(lcs[i-1][j], lcs[i][j-1])
    return distance[-1][-1], lcs[-1][-1]


def refs(rows, answerable=True):
    return [{"id": "x", "answerable": answerable, "result_rows": rows,
             "output_text": render_answer(rows, answerable=answerable)}]


def score(rows, text, answerable=True):
    return score_records(refs(rows, answerable), {"x": text})


def audit(phase):
    findings, checks = [], []
    code_hashes = {name: sha(PACKAGE / name) for name in (
        "english_metrics.py", "reference_renderer.py", "answer_from_sql.py", "validate_delivery.py")}
    seqs = [list(t) for n in range(5) for t in itertools.product(("a", "b"), repeat=n)]
    for a in seqs:
        for b in seqs:
            expected_edit, expected_lcs = independent_dp(a, b)
            assert edit_distance(a, b) == expected_edit
            assert lcs_length(a, b) == expected_lcs
    checks.append({"check": "independent_full_matrix_DP_vs_implementation", "sequence_pairs": len(seqs)**2, "passed": True})

    cases = [
        ("wrong_number", [[3]], render_answer([[4]]), True, 0),
        ("changed_sign", [[-3]], render_answer([[3]]), True, 0),
        ("wrong_decimal", [[3.123]], render_answer([[3.124]]), True, 0),
        ("same_numeric3", [[3.12349]], render_answer([[3.12340]]), True, 100),
        ("appended_negation", [[3]], render_answer([[3]]) + " The result is not true.", True, 0),
        ("missing_duplicate", [["a"], ["a"]], render_answer([["a"]]), True, 0),
        ("wrong_column_order", [["a", "b"]], render_answer([["b", "a"]]), True, 0),
        ("extra_row", [["a"]], render_answer([["a"], ["b"]]), True, 0),
        ("full_result_tail", [[str(i)] for i in range(101)], render_answer([[str(i)] for i in range(100)]), True, 0),
        ("NULL_not_refusal", [[None]], ABSTENTION_TEXT, True, 0),
        ("NULL_not_empty", [[None]], EMPTY_TEXT, True, 0),
        ("empty_not_refusal", [], ABSTENTION_TEXT, True, 0),
        ("false_refusal", [[3]], ABSTENTION_TEXT, True, 0),
        ("correct_refusal", None, ABSTENTION_TEXT, False, 100),
        ("fabricated_on_unanswerable", None, render_answer([[3]]), False, 0),
        ("error_not_correct_refusal", None, EXECUTION_ERROR_TEXT, False, 0),
        ("empty_prediction_failure", [[3]], "", True, 0),
        ("malformed_JSON", [[3]], 'The returned value is {bad}.', True, 0),
        ("valid_but_wrong_JSON_type", [[3]], 'The returned value is {"a":3}.', True, 0),
        ("deep_JSON", [[3]], 'The returned value is ' + '['*2000 + '"3"' + ']'*2000 + '.', True, 0),
        ("escaped_prose_in_actual_cell", [['a\nRow 2: deceptive.']], render_answer([['a\nRow 2: deceptive.']]), True, 100),
    ]
    for name, rows, text, answerable, expected in cases:
        report = score(rows, text, answerable)
        actual = report["controlled"]["fact_EM"]
        assert actual == expected, (name, expected, actual)
        checks.append({"check": name, "fact_EM": actual, "passed": True})

    # Same content can be unparseable if it is outside strict canonical grammar.
    canonical_constraint = {
        "numeric_spelling_3_instead_of_3_point_0": score([[3]], 'The returned value is "3".')["controlled"],
        "same_rows_different_serialized_order": score([["a"], ["b"]], 'The query returned 2 rows.\nRow 1: ["b"].\nRow 2: ["a"].')["controlled"],
        "assessment": "Declared strict canonical format restriction; document this alongside numeric3/unordered-row claims, not an unrestricted semantic metric."
    }

    temp_parent = PACKAGE / ".test_tmp"
    temp_parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="independent-metric-audit-", dir=temp_parent) as temporary:
        temp = Path(temporary).resolve()
        assert temp.is_relative_to(PACKAGE.resolve())
        fixture = temp / "duplicate.json"
        fixture.write_text('{"x":"incorrect first output","x":' + json.dumps(render_answer([[3]])) + '}', encoding="utf-8")
        try:
            loaded = load_records(fixture)
            accepted = score_records(refs([[3]]), loaded)["controlled"]["fact_EM"]
        except ValueError:
            accepted = None
        if accepted is not None:
            findings.append({"id": "M1", "severity": "P2", "title": "Duplicate JSON object IDs silently overwritten",
                             "observed_fact_EM": accepted, "reproduction": 'load_records on {"x":"incorrect first output","x":"correct controlled text"}',
                             "expected": "Reject duplicate IDs before Python dict construction", "impact": "Prediction input integrity; does not change audited existing artifacts"})
        checks.append({"check": "duplicate_JSON_mapping_rejected", "passed": accepted is None})

        # Inconsistent gold can otherwise create contradictory lexical/fact truth.
        inconsistent = [{**refs([[3]])[0], "output_text": render_answer([[4]])}]
        try:
            inconsistent_score = score_records(inconsistent, {"x": render_answer([[3]])})
        except ValueError:
            inconsistent_score = None
        if inconsistent_score is not None:
            findings.append({"id": "M2", "severity": "P2", "title": "Controlled reference text may disagree with its result_rows",
                             "observed": {"raw_EM": inconsistent_score["lexical"]["raw_EM"], "fact_EM": inconsistent_score["controlled"]["fact_EM"]},
                             "reproduction": 'Reference output_text renders 4.0 while result_rows holds 3.0; prediction renders 3.0',
                             "expected": "Reject inconsistent controlled references", "impact": "Future edited/imported references; current7454 independently audited consistent"})
        checks.append({"check": "inconsistent_controlled_reference_rejected", "passed": inconsistent_score is None})

        db = temp / "fixture.sqlite"
        with sqlite3.connect(db) as conn:
            conn.execute("CREATE TABLE example(value INTEGER)")
            conn.executemany("INSERT INTO example VALUES (?)", [(3,), (4,), (4,)])
        conn.close()
        before = sha(db)
        sqls = {"correct": "SELECT value FROM example", "wrong": "SELECT 99", "null": "null",
                "empty": "", "invalid": "SELECT no_column FROM example", "write": "DELETE FROM example"}
        outputs = {r["id"]: r for r in verbalize(sqls, [{"id": key} for key in sqls], database=db)}
        assert outputs["wrong"]["output_text"] == render_answer([[99]])
        assert outputs["null"]["output_text"] == ABSTENTION_TEXT
        assert all(outputs[k]["output_text"] == EXECUTION_ERROR_TEXT for k in ("empty", "invalid", "write"))
        assert sha(db) == before
        checks.append({"check": "bridge_never_substitutes_gold_or_turns_error_into_refusal_and_database_unchanged", "passed": True})

    for predictions in ({}, {"y": render_answer([[3]])}, [{"id": "x", "output_text": "a"}]*2):
        try:
            score_records(refs([[3]]), predictions)
        except ValueError:
            continue
        raise AssertionError("Missing/extra/list-duplicate ID accepted")
    checks.append({"check": "missing_extra_list_duplicate_ID_rejected", "passed": True})
    injected = score_records(refs([[3]]), {"x": {"output_text": render_answer([[4]]), "result_rows": [[3]]}})
    assert injected["controlled"]["fact_EM"] == 0
    checks.append({"check": "prediction_self_reported_rows_cannot_override_wrong_text", "passed": True})

    lock = load(WORKSPACE / "experiments/research_validation/V5_LOCK.json")
    assert all(sha(WORKSPACE / name) == digest for name, digest in lock["files"].items())
    saved_tests = load(PACKAGE / "results/DELIVERY_VALIDATION.json")["unit_tests"]
    report = {"phase": phase, "date": "2026-11-01", "new_model_API_calls": 0,
              "code_sha256": code_hashes, "checks": checks, "findings": findings,
              "strict_grammar_constraints": canonical_constraint,
              "frozen_files_unchanged": len(lock["files"]), "prior_test_JUnit_counts": saved_tests,
              "test_count_note": "JUnit includes successful subtests. Original delivery had51functions+5subtests=56cases; current parent delivery has61functions+5subtests=66cases.",
              "selfcheck_note": "SCORER_SELF_CHECK explicitly says not model performance; no unsupported generation score found."}
    output = HERE / "metric_audit.json"
    history = load(output) if output.exists() else {"runs": []}
    history["initial_interactive_findings_before_parent_fix"] = [
        {"id": "M1", "severity": "P2", "title": "Duplicate JSON mapping IDs silently overwritten",
         "observed": {"JSON": '{"x":"incorrect", "x":"correct controlled answer"}', "loaded_records": 1, "fact_EM": 100.0},
         "expected": "Reject duplicate IDs before dict construction",
         "evidence_origin": "Independent interactive Python probe in this agent before root patch; not an original code snapshot"},
        {"id": "M2", "severity": "P2", "title": "Controlled reference text/result_rows contradiction accepted",
         "observed": {"reference_text_value": "4.0", "reference_result_rows": [["3.0"]], "prediction_text_value": "3.0", "raw_EM": 0.0, "fact_EM": 100.0, "WER": 20.0},
         "expected": "Reject inconsistent controlled reference before prediction grading",
         "evidence_origin": "Independent interactive Python probe in this agent before root patch; current7454references were already audited consistent"}
    ]
    history["initial_interactive_findings_resolution"] = "resolved" if not findings else "still_reproducible"
    history["timeline_note"] = "Parent applied fixes before first persistent script run; pre-fix findings were independently reproduced in earlier interactive probe and communicated before edits."
    history["interactive_pre_fix_observations"] = {
        "evidence_kind": "Earlier interactive tool-observed Python probes, not captured by a formal run of this script against an original snapshot",
        "pre_fix_english_metrics_sha256": "6c4c435f1f7d9ed1fc93bb00eef743e1d6240114c73ccd9fd42bd5704ad820cd",
        "hash_provenance": "Original delivery validation artifact; this script did not restore or rerun that snapshot",
        "duplicate_mapping_probe": {
            "file_input": '{"x":"incorrect", "x":"The returned value is \\\"3.0\\\"."}',
            "actual_loaded_mapping": {"x": 'The returned value is "3.0".'},
            "actual_fact_EM": 100.0,
            "expected": "ValueError for duplicate JSON object key before dict construction"
        },
        "inconsistent_reference_probe": {
            "reference_output_text": 'The returned value is "4.0".',
            "reference_result_rows": [["3.0"]],
            "prediction_output_text": 'The returned value is "3.0".',
            "actual_raw_EM": 0.0, "actual_fact_EM": 100.0, "actual_WER": 20.0,
            "expected": "ValueError for controlled reference text/result_rows contradiction"
        }
    }
    for prior in history["runs"]:
        if prior["phase"] == "initial_independent_audit":
            prior["original_phase_label"] = prior["phase"]
            prior["phase"] = "initial_script_audit_after_fixes"
            prior["provenance_note"] = "Recorded codehash324402... and findings[] are after parent fixes; this is not a scripted pre-fix audit."
    history["current_unit_test_JUnit_counts"] = saved_tests
    history["runs"].append(report)
    output.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Audit độc lập bộ chấm tiếng Anh", "", f"Lần audit: {phase}. Không API; {len(lock['files'])} file đóng băng không đổi.", "",
             f"Kiểm tra DP độc lập trên {len(seqs)**2} cặp chuỗi; các case số sai, dấu âm, số thập phân, phủ định, duplicate, column order, >100 rows, NULL/empty/refusal/errors và JSON lỗi đã chạy.", ""]
    if findings:
        for item in findings:
            lines += [f"- **{item['id']} / {item['severity']}: {item['title']}**. {item['impact']}.", f"  Expected: {item['expected']}."]
    else:
        lines += ["Không còn finding tái hiện được trong phạm vi script này."]
    lines += ["", "Hai lỗi input integrity đã tái hiện trước khi parent sửa: JSON mapping có ID trùng bị ghi đè; reference controlled text có thể trái result_rows. Cả hai hiện được kiểm tra lại và từ chối. Các lỗi này không làm thay đổi7454nhãn đã audit hoặc kết quả Text-to-SQL cũ."]
    lines += ["", "Grammar hiện yêu cầu đúng spelling numeric chuẩn và sorted serialization; prose tương đương ngoài grammar bị factEM=0. Đây là giới hạn định dạng đã khai báo, không phải validator ngữ nghĩa tự do.",
              "", "Self-check dữ liệu không bị gán là kết quả model. Bản giao trước có51testfunction+5subtest=56JUnitcase; hiện tại61testfunction+5subtest=66JUnitcase. Số56trong run cũ chỉ là lịch sử.",
              "", "Hai finding trước sửa được ghi nhận bằng probe Python tương tác, không phải lần chạy script trên snapshot cũ. Tất cả run script đã lưu đều chạy sau khi parent sửa; JSON giữ original phase label và ghi rõ hash/status sau sửa. Hash code cũ lấy từ artifact bàn giao trước, không phải một formal scripted pre-fix rerun."]
    (HERE / "metric_audit.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(json.dumps({"phase": phase, "findings": findings, "checks": len(checks), "frozen": len(lock['files'])}, ensure_ascii=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="initial_independent_audit")
    audit(parser.parse_args().phase)
