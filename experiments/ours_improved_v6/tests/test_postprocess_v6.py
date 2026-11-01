from copy import deepcopy
from pathlib import Path
import sqlite3
import sys

import pytest
from sqlglot import parse_one

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from postprocess_v6 import V5_MODULE, V4_MODULE, compile_v6, enhance_candidate


@pytest.fixture
def metadata():
    return V5_MODULE.metadata_from_rows({
        "d_icd_diagnoses": [("icd10|z6838", "body mass index"), ("icd9|42", "old"), ("icd10|42", "new")],
        "d_icd_procedures": [("icd10|x1", "procedure")],
    })


def test_period_projection_removed_but_grouping_filters_aggregate_remain(metadata):
    sql = "SELECT strftime('%Y-%m', lab.charttime) AS month, AVG(lab.value) FROM lab WHERE lab.patient=11 GROUP BY strftime('%Y-%m',lab.charttime)"
    result = compile_v6("Show the monthly average value for patient 11", sql, metadata)
    ast = parse_one(result["sql"], read="sqlite")
    assert len(ast.expressions) == 1
    assert "AVG(lab.value)" in result["sql"] and "GROUP BY" in result["sql"] and "lab.patient = 11" in result["sql"]
    assert result["changes"][0]["kind"] == "period_aggregate_output_contract"


@pytest.mark.parametrize("question", ["Show month and monthly average", "Include the month and monthly maximum", "Give dates with the monthly average", "When was the monthly maximum?"])
def test_explicit_period_output_not_removed(metadata, question):
    sql = "SELECT strftime('%Y-%m',t.ts), AVG(t.v) FROM t GROUP BY strftime('%Y-%m',t.ts)"
    assert not compile_v6(question, sql, metadata)["changed"]


@pytest.mark.parametrize("sql", [
    "SELECT patient, AVG(value) FROM lab GROUP BY patient",
    "SELECT strftime('%Y-%m',ts), MAX(value) FROM lab GROUP BY strftime('%Y-%m',ts)",
    "SELECT strftime('%Y-%m',ts) AS month, AVG(value) FROM lab GROUP BY strftime('%Y-%m',ts) ORDER BY month",
    "SELECT DISTINCT strftime('%Y-%m',ts), AVG(value) FROM lab GROUP BY strftime('%Y-%m',ts)",
])
def test_projection_repair_does_not_guess_other_shapes(metadata, sql):
    assert not compile_v6("What was the monthly average value?", sql, metadata)["changed"]


@pytest.mark.parametrize("period_word,explicit", [
    ("monthly", "by month"), ("daily", "per day"),
    ("yearly", "for each year"), ("weekly", "each week"),
])
def test_explicit_by_per_each_period_output_is_preserved(metadata, period_word, explicit):
    sql = "SELECT strftime('%Y-%m',ts), AVG(v) FROM t GROUP BY strftime('%Y-%m',ts)"
    question = f"Show {period_word} average cost {explicit}"
    result = compile_v6(question, sql, metadata)
    assert result["sql"] == sql and not result["changed"]


@pytest.mark.parametrize("order", ["1", "1 DESC", "(1)"])
def test_ordinal_order_projection_removal_can_change_selected_group_and_is_skipped(metadata, order):
    with sqlite3.connect(":memory:") as connection:
        connection.execute("CREATE TABLE t(ts TEXT, v REAL)")
        connection.executemany("INSERT INTO t VALUES (?,?)", [("2100-01-02", 100), ("2100-02-02", 1)])
        sql = ("SELECT strftime('%Y-%m',ts) AS month, AVG(v) FROM t "
               f"GROUP BY strftime('%Y-%m',ts) ORDER BY {order} LIMIT 1")
        result = compile_v6("Show monthly average cost", sql, metadata)
        assert result["sql"] == sql and not result["changed"]
        original = connection.execute(sql).fetchall()
        unsafe = connection.execute(sql.replace("strftime('%Y-%m',ts) AS month, ", "")).fetchall()
        assert original[0][1] != unsafe[0][0]


def test_organism_notnull_is_added_to_first_last_positive_lookup(metadata):
    sql = "SELECT org_name FROM microbiologyevents WHERE subject_id=11 ORDER BY charttime LIMIT 1"
    result = compile_v6("What was the organism found in the first urine test?", sql, metadata)
    assert result["changed"] and "NOT org_name IS NULL" in result["sql"]


@pytest.mark.parametrize("question,sql", [
    ("What was the organism missing in the first test?", "SELECT org_name FROM microbiologyevents ORDER BY charttime LIMIT 1"),
    ("What was the first organism?", "SELECT org_name FROM other_table ORDER BY charttime LIMIT 1"),
    ("What was the first organism?", "SELECT org_name FROM microbiologyevents WHERE org_name IS NULL ORDER BY charttime LIMIT 1"),
    ("What was the first organism?", "SELECT org_name FROM microbiologyevents WHERE org_name IS NOT NULL ORDER BY charttime LIMIT 1"),
])
def test_organism_rule_respects_null_questions_and_table_scope(metadata, question, sql):
    assert not compile_v6(question, sql, metadata)["changed"]


def test_unique_casefold_code_binding_and_ambiguous_suffix_skip(metadata):
    result = compile_v6("irrelevant", "SELECT * FROM diagnoses_icd WHERE icd_code IN ('Z6838','42')", metadata)
    assert result["changed"] and "'icd10|z6838'" in result["sql"] and "'42'" in result["sql"]
    assert len(result["changes"]) == 1
    already = compile_v6("irrelevant", "SELECT * FROM diagnoses_icd WHERE icd_code='icd10|z6838'", metadata)
    assert not already["changed"]


def test_full_code_spelling_repaired_within_same_dictionary_only(metadata):
    assert compile_v6("q", "SELECT * FROM diagnoses_icd WHERE icd_code='ICD10|Z6838'", metadata)["changed"]
    assert not compile_v6("q", "SELECT * FROM procedures_icd WHERE icd_code='Z6838'", metadata)["changed"]
    assert not compile_v6("q", "SELECT * FROM diagnoses_icd WHERE unrelated='Z6838'", metadata)["changed"]


def candidate(sql):
    return {"sql": sql, "execution": {"valid": True, "abstained": False, "empty": False, "error": None},
            "finish_reason": "stop", "contract": {"hard_issues": [], "soft_issues": ["output_shape: warning"]},
            "static_issues": [], "call_hashes": ["original-request"], "route": "direct"}


def test_changed_proposal_reexecutes_and_keeps_source_immutable(metadata, monkeypatch):
    sql = "SELECT strftime('%Y-%m',ts), AVG(v) FROM t GROUP BY strftime('%Y-%m',ts)"
    row = candidate(sql)
    old = deepcopy(row)
    calls = []
    monkeypatch.setattr(V4_MODULE, "execute", lambda query: calls.append(query) or [(2.5,)])
    result = enhance_candidate("Show monthly average", row, metadata)
    assert row == old and result["v6_original_record"] == old
    assert calls == [result["sql"]]
    assert result["execution"]["valid"] and result["v6_repair"]["proposal_accepted"]
    assert result["call_hashes"] == old["call_hashes"]


def test_failed_proposal_keeps_V5_prediction(metadata, monkeypatch):
    sql = "SELECT strftime('%Y-%m',ts), AVG(v) FROM t GROUP BY strftime('%Y-%m',ts)"
    row = candidate(sql)
    monkeypatch.setattr(V4_MODULE, "execute", lambda query: [])
    result = enhance_candidate("Show monthly average", row, metadata)
    assert result["sql"] == sql and result["v6_repair"]["proposal_accepted"] is False


@pytest.mark.parametrize("variant", ["null", "truncated", "hard_issue"])
def test_no_revival_of_model_null_truncation_or_hard_issue(metadata, variant):
    row = candidate("SELECT org_name FROM microbiologyevents ORDER BY charttime LIMIT 1")
    if variant == "null":
        row.update(sql="null", execution={"valid": False, "abstained": True, "empty": None, "error": None})
    elif variant == "truncated":
        row["finish_reason"] = "length"
    else:
        row["contract"]["hard_issues"] = ["forbidden"]
    assert enhance_candidate("What was the first organism?", row, metadata)["sql"] == row["sql"]
