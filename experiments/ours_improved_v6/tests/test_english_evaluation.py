"""Synthetic integration tests; never read paper test data or prediction labels."""
from pathlib import Path
import json
import sqlite3
import sys

import pytest

V6 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(V6))
import english_evaluation as evaluator
from experiments.sql_to_text_evaluation.reference_renderer import render_answer


def fixture(tmp_path):
    db = tmp_path / "synthetic.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.executemany("INSERT INTO records VALUES (?)", [("x",), ("x",), ("y",)])
    inputs = tmp_path / "inputs.jsonl"
    refs = tmp_path / "refs.jsonl"
    data = [
        {"id": "correct", "input_text": "List records.", "answerable": True, "result_rows": [["x"], ["x"], ["y"]]},
        {"id": "wrong", "input_text": "Count records.", "answerable": True, "result_rows": [[3]]},
        {"id": "unanswerable", "input_text": "Recommend treatment.", "answerable": False, "result_rows": None},
        {"id": "invalid", "input_text": "Count missing.", "answerable": False, "result_rows": None},
        {"id": "empty", "input_text": "List empty group.", "answerable": True, "result_rows": []},
    ]
    inputs.write_text("".join(json.dumps({k: row[k] for k in ("id", "input_text")}) + "\n" for row in data), encoding="utf-8")
    refs.write_text("".join(json.dumps({**row, "output_text": render_answer(row["result_rows"], answerable=row["answerable"])}) + "\n" for row in data), encoding="utf-8")
    predictions = tmp_path / "SQL.json"
    predictions.write_text(json.dumps({"correct": "SELECT value FROM records", "wrong": "SELECT 99",
                                       "unanswerable": "null", "invalid": "SELECT missing FROM records",
                                       "empty": "SELECT value FROM records WHERE 0"}), encoding="utf-8")
    return db, inputs, refs, predictions


def test_actual_SQL_then_saved_English_then_reference_scoring(tmp_path, monkeypatch):
    db, inputs, refs, predictions = fixture(tmp_path)
    destination = tmp_path / "result"
    original_loader = evaluator.load_records
    def checked_loader(path):
        if Path(path) == refs:
            assert (destination / "english_predictions.jsonl").is_file()
            saved = original_loader(destination / "english_predictions.jsonl")
            assert saved[1]["output_text"] == render_answer([[99]])
        return original_loader(path)
    monkeypatch.setattr(evaluator, "load_records", checked_loader)
    before = db.read_bytes()
    report = evaluator.evaluate(output_dir=destination, sql_predictions=predictions,
                                inputs_path=inputs, references_path=refs, database=db, verify_originals=False)
    assert report["questions"] == 5
    assert report["controlled"]["fact_EM"] == 60
    assert report["execution_status_counts"] == {"executed": 3, "abstained": 1, "execution_error": 1}
    assert report["reference_English_used_to_generate_answers"] is False
    assert report["gold_SQL_used_to_generate_end_to_end_answers"] is False
    assert db.read_bytes() == before
    scores = original_loader(destination / "english_scores.json")
    assert scores["per_question"]["invalid"]["controlled_fact_EM"] is False
    assert scores["groups"]["unanswerable"]["n"] == 2


def test_duplicate_SQL_JSON_ID_rejected(tmp_path):
    db, inputs, refs, predictions = fixture(tmp_path)
    predictions.write_text('{"correct":"SELECT 1","correct":"SELECT 2"}', encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        evaluator.evaluate(output_dir=tmp_path / "result", sql_predictions=predictions,
                           inputs_path=inputs, references_path=refs, database=db, verify_originals=False)


def test_missing_SQL_ID_is_not_dropped(tmp_path):
    db, inputs, refs, predictions = fixture(tmp_path)
    predictions.write_text('{"correct":"SELECT 1"}', encoding="utf-8")
    with pytest.raises(ValueError, match="cover input IDs"):
        evaluator.evaluate(output_dir=tmp_path / "result", sql_predictions=predictions,
                           inputs_path=inputs, references_path=refs, database=db, verify_originals=False)
    assert not (tmp_path / "result").exists()


def test_existing_output_cannot_be_overwritten(tmp_path):
    db, inputs, refs, predictions = fixture(tmp_path)
    output = tmp_path / "result"
    output.mkdir()
    marker = output / "historic.txt"
    marker.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="historical outputs"):
        evaluator.evaluate(output_dir=output, sql_predictions=predictions,
                           inputs_path=inputs, references_path=refs, database=db, verify_originals=False)
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_oracle_is_explicit_and_never_claimed_model_performance(tmp_path):
    db, inputs, refs, predictions = fixture(tmp_path)
    components = tmp_path / "oracle.jsonl"
    ids = [row["id"] for row in evaluator.load_records(inputs)]
    sqls = evaluator.load_records(predictions)
    sqls["wrong"] = "SELECT COUNT(*) FROM records"
    sqls["invalid"] = "null"
    components.write_text("".join(json.dumps({"id": key, "input_sql": sqls[key]}) + "\n" for key in ids), encoding="utf-8")
    report = evaluator.evaluate(output_dir=tmp_path / "oracle_result", mode="oracle_renderer",
                                inputs_path=inputs, references_path=refs, database=db,
                                oracle_input_path=components, verify_originals=False)
    assert report["controlled"]["fact_EM"] == 100
    assert report["oracle_is_not_system_performance"] is True
    assert report["gold_SQL_used_to_generate_end_to_end_answers"] is True
    assert report["new_model_API_calls"] == 0
    with pytest.raises(ValueError, match="must not be confused"):
        evaluator.evaluate(output_dir=tmp_path / "bad", mode="oracle_renderer", sql_predictions=predictions)


def test_generation_input_cannot_contain_gold_text(tmp_path):
    db, inputs, refs, predictions = fixture(tmp_path)
    inputs.write_text('{"id":"correct","input_text":"Question","output_text":"secret gold"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="exactly id and input_text"):
        evaluator.evaluate(output_dir=tmp_path / "result", sql_predictions=predictions,
                           inputs_path=inputs, references_path=refs, database=db, verify_originals=False)


def test_full_results_more_than_100_rows_and_duplicates(tmp_path):
    db = tmp_path / "full.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE records (value TEXT)")
        conn.executemany("INSERT INTO records VALUES (?)", [("x",)] * 101)
    inputs, refs, predictions = [tmp_path / name for name in ("inputs.jsonl", "refs.jsonl", "SQL.json")]
    inputs.write_text('{"id":"q","input_text":"List all values"}\n', encoding="utf-8")
    rows = [["x"]] * 101
    refs.write_text(json.dumps({"id": "q", "answerable": True, "result_rows": rows, "output_text": render_answer(rows)}) + "\n", encoding="utf-8")
    predictions.write_text('{"q":"SELECT value FROM records"}', encoding="utf-8")
    result = evaluator.evaluate(output_dir=tmp_path / "full_result", sql_predictions=predictions,
                                inputs_path=inputs, references_path=refs, database=db, verify_originals=False)
    assert result["controlled"]["fact_EM"] == 100
    output_text = evaluator.load_records(tmp_path / "full_result/english_predictions.jsonl")[0]["output_text"]
    assert "Row 101:" in output_text


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf")])
def test_invalid_runtime_configuration_stops_before_padding_failures(tmp_path, timeout):
    with pytest.raises(ValueError, match="finite and positive"):
        evaluator.evaluate(output_dir=tmp_path / "unused", sql_predictions=tmp_path / "missing.json", timeout_s=timeout)
