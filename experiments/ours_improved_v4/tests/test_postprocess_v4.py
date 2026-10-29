"""Focused v4 tests, with synthetic metadata and a mocked readonly executor."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import tempfile
import sqlite3
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("postprocess_v4_under_test", Path(__file__).resolve().parents[1] / "postprocess_v4.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def metadata():
    return module.metadata_from_rows({
        "d_icd_diagnoses": [
            ("icd9|a", "long-term use"), ("icd10|b", "long term use"),
            ("icd10|absent_from_facts", "a valid dictionary-only diagnosis"),
            ("bare_valid", "physically valid bare dictionary code"),
            ("icd9|same", "same-code title"), ("icd9|same", "same code title"),
        ],
        "d_icd_procedures": [("icd9|p", "procedure label")],
    })


def record(route, sql="SELECT 1", fingerprint="raw"):
    return {"route": route, "sql": sql,
            "execution": {"valid": True, "abstained": False, "empty": False, "error": None},
            "result_fingerprint": fingerprint, "result_summary": {"rows": 1, "columns": 1, "trivial_scalar": False},
            "contract": {"hard_issues": [], "soft_issues": []}, "static_issues": [],
            "call_hashes": [route], "finish_reason": "stop"}


def normalized(route, sql="SELECT 1", rows=None):
    with patch.object(module, "execute", return_value=[[1]] if rows is None else rows):
        return module.normalize_candidate("question", record(route, sql), metadata())


class V4Tests(unittest.TestCase):
    def test_full_fingerprint_uses_official_numeric_rounding_without_row_cap(self):
        first, _ = module.fingerprint_round3([[1.0001], ["2"], [None]])
        second, _ = module.fingerprint_round3([[None], [2.0], [1.0002]])
        self.assertEqual(first, second)
        self.assertNotEqual(module.fingerprint_round3([[1], [1]])[0], module.fingerprint_round3([[1]])[0])
        self.assertNotEqual(module.fingerprint_round3([[1, 2]])[0], module.fingerprint_round3([[1], [2]])[0])
        rows = [[i] for i in range(101)]
        changed = deepcopy(rows)
        changed[-1] = [999]
        self.assertNotEqual(module.fingerprint_round3(rows)[0], module.fingerprint_round3(changed)[0])

    def test_full_dictionary_code_validity_is_not_observed_fact_presence(self):
        sql = "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='icd10|absent_from_facts'"
        with patch.object(module, "execute", return_value=[[0]]) as execute:
            result = module.normalize_candidate("question", record("a", sql), metadata())
        execute.assert_called_once_with(sql)
        self.assertEqual(result["sql"], sql)
        self.assertFalse(result.get("v4_guard_rejected", False))

    def test_invalid_bare_code_guard_before_execution_and_preserve_history(self):
        source = record("a", "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='a'")
        source.update(pre_guard_sql="older SQL", pre_guard_execution={"error": "older error"})
        original = deepcopy(source)
        with patch.object(module, "execute") as execute:
            result = module.normalize_candidate("question", source, metadata())
        execute.assert_not_called()
        self.assertEqual(source, original)
        self.assertEqual(result["sql"], "null")
        self.assertTrue(result["guard_rejected"])
        self.assertEqual(result["pre_guard_sql"], "older SQL")
        self.assertEqual(result["v4_original_record"], original)
        self.assertEqual(result["v4_pre_guard_sql"], original["sql"])

    def test_a_physically_existing_bare_code_is_not_rejected(self):
        sql = "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='bare_valid'"
        self.assertFalse(module.dictionary_issues("question", sql, metadata())["hard_issues"])

    def test_facts_use_corresponding_dictionary_not_other_icd_universe(self):
        diagnosis = module.dictionary_issues("q", "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='p'", metadata())
        procedure = module.dictionary_issues("q", "SELECT COUNT(*) FROM procedures_icd WHERE icd_code='p'", metadata())
        self.assertIn("d_icd_diagnoses", diagnosis["hard_issues"][0])
        self.assertIn("d_icd_procedures", procedure["hard_issues"][0])

    def test_surface_collision_soft_not_hard_and_resolves_aliases(self):
        sql = "SELECT x.icd_code FROM d_icd_diagnoses x WHERE x.long_title='long term use'"
        issues = module.dictionary_issues("Has the long-term use diagnosis occurred?", sql, metadata())
        self.assertFalse(issues["hard_issues"])
        self.assertTrue(issues["soft_issues"][0].startswith("dictionary_surface_ambiguity:"))
        with patch.object(module, "execute", return_value=[["icd10|b"]]):
            result = module.normalize_candidate("long-term use diagnosis", record("a", sql), metadata())
        self.assertEqual(result["sql"], sql)
        self.assertFalse(result.get("v4_guard_rejected", False))

    def test_same_code_alias_and_nonexact_question_do_not_create_ambiguity(self):
        same = "SELECT icd_code FROM d_icd_diagnoses WHERE long_title='same code title'"
        self.assertFalse(module.dictionary_issues("same-code title", same, metadata())["soft_issues"])
        other = "SELECT icd_code FROM d_icd_diagnoses WHERE long_title='long term use'"
        self.assertFalse(module.dictionary_issues("a different diagnosis", other, metadata())["soft_issues"])

    def test_round3_consensus_and_raw_baseline_are_separate(self):
        rows = [normalized("a", rows=[[1.0001]]), normalized("b", rows=[[1.0002]]), normalized("c", rows=[[1.0003]])]
        for index, row in enumerate(rows):
            row["v4_original_record"]["result_fingerprint"] = "raw" + str(index)
        self.assertEqual(module.select_v4(rows, "strict3_round3")["selected_candidate_index"], 0)
        self.assertEqual(module.select_v4(rows, "strict3_raw")["sql"], "null")

    def test_trivial_and_surface_risk_gates_do_not_mutate_candidates(self):
        rows = [normalized(route, rows=[[0]]) for route in ["a", "b", "c"]]
        original = deepcopy(rows)
        self.assertEqual(module.select_v4(rows, "strict3_round3")["selected_candidate_index"], 0)
        self.assertEqual(module.select_v4(rows, "strict3_round3_no_trivial")["sql"], "null")
        self.assertEqual(rows, original)
        for row in rows:
            row["result_summary"]["trivial_scalar"] = False
        rows[0]["contract"]["soft_issues"] = ["dictionary_surface_ambiguity: synthetic example"]
        self.assertEqual(module.select_v4(rows, "strict3_round3")["selected_candidate_index"], 0)
        rejected = module.select_v4(rows, "strict3_round3_exact_binding")
        self.assertEqual(rejected["sql"], "null")
        self.assertNotIn(0, rejected["selection"]["features"]["genuine_model_null_indices"])

    def test_failed_empty_incomplete_and_api_failures_are_distinct(self):
        with patch.object(module, "execute", side_effect=ValueError("no such table")):
            failed = module.normalize_candidate("q", record("a"), metadata())
        self.assertEqual(failed["v4_guard_reason"], "readonly_execution_failure")
        with patch.object(module, "execute", return_value=[]):
            empty = module.normalize_candidate("q", record("a"), metadata())
        self.assertEqual(empty["v4_guard_reason"], "empty_readonly_execution")
        incomplete = record("a")
        incomplete["finish_reason"] = "length"
        with patch.object(module, "execute") as execute:
            result = module.normalize_candidate("q", incomplete, metadata())
        execute.assert_not_called()
        self.assertEqual(result["sql"], "null")
        with self.assertRaises(ValueError):
            module.normalize_candidate("q", {**record("a"), "api_error": "HTTP 402"}, metadata())

    def test_re_normalization_keeps_one_immutable_source_snapshot(self):
        source = record("a")
        with patch.object(module, "execute", return_value=[[1]]):
            first = module.normalize_candidate("q", source, metadata())
            second = module.normalize_candidate("q", first, metadata())
        self.assertEqual(second["v4_original_record"], source)
        self.assertNotIn("v4_original_record", second["v4_original_record"])
        self.assertEqual(first["result_fingerprint"], second["result_fingerprint"])

    def test_partial_metadata_cannot_be_used_for_hard_code_validation(self):
        partial = metadata()
        partial["complete_dictionary_universes"] = False
        with self.assertRaises(ValueError):
            module.dictionary_issues("q", "SELECT icd_code FROM diagnoses_icd WHERE icd_code='a'", partial)


if __name__ == "__main__":
    unittest.main()
