from pathlib import Path
import sqlite3
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from answer_from_sql import verbalize
from reference_renderer import ABSTENTION_TEXT, EMPTY_TEXT, EXECUTION_ERROR_TEXT, parse_controlled_answer


def test_predicted_sql_is_executed_not_gold_substituted(tmp_path):
    db = tmp_path / "test.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE values_table (value INTEGER)")
        conn.executemany("INSERT INTO values_table VALUES (?)", [(3,), (4,), (4,)])
    sqls = {"correct": "SELECT value FROM values_table", "wrong": "SELECT 99",
            "refuse": "null", "invalid": "SELECT missing_column FROM values_table",
            "empty_statement": "", "zero_rows": "SELECT value FROM values_table WHERE 0",
            "write": "DELETE FROM values_table"}
    before = db.read_bytes()
    outputs = {r["id"]: r for r in verbalize(sqls, [{"id": k} for k in sqls], database=db)}
    assert parse_controlled_answer(outputs["correct"]["output_text"])["rows"] == [["3.0"], ["4.0"], ["4.0"]]
    assert parse_controlled_answer(outputs["wrong"]["output_text"])["rows"] == [["99.0"]]
    assert outputs["refuse"]["output_text"] == ABSTENTION_TEXT
    assert outputs["zero_rows"]["output_text"] == EMPTY_TEXT
    for key in ("invalid", "empty_statement", "write"):
        assert outputs[key]["output_text"] == EXECUTION_ERROR_TEXT
        assert outputs[key]["status"] == "execution_error"
    assert db.read_bytes() == before


def test_missing_id_never_disappears():
    with pytest.raises(ValueError):
        verbalize({"a": "SELECT 1"}, [{"id": "a"}, {"id": "b"}])
