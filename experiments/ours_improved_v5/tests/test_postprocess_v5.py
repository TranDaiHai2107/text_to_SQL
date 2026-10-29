from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("postprocess_v5_under_test", Path(__file__).resolve().parents[1] / "postprocess_v5.py")
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def metadata():
    return module.metadata_from_rows({
        "d_icd_diagnoses": [
            ("icd9|unique", "long-term use"), ("icd10|other", "long term use"),
            ("icd9|ambiguous", "old label"), ("icd10|ambiguous", "new label"),
            ("icd10|dictionary_only", "absent from patient facts"),
            ("bare_valid", "a physically bare code"),
            ("icd9|same", "same-code title"), ("icd9|same", "same code title"),
        ],
        "d_icd_procedures": [("icd10|unique", "procedure label")],
    })


def record(route="a", sql="SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='unique'"):
    return {"route": route, "sql": sql,
            "execution": {"valid": True, "abstained": False, "empty": False, "error": None},
            "result_fingerprint": "original_raw", "result_summary": {"rows": 1, "columns": 1, "trivial_scalar": True},
            "contract": {"hard_issues": [], "soft_issues": []}, "static_issues": [],
            "call_hashes": [route], "finish_reason": "stop"}


class V5Tests(unittest.TestCase):
    def test_namespace_is_unique_within_resolved_dictionary(self):
        diagnosis = module.compile_namespace("q", "SELECT COUNT(*) FROM diagnoses_icd d WHERE d.icd_code='unique'", metadata())
        procedure = module.compile_namespace("q", "SELECT COUNT(*) FROM procedures_icd p WHERE p.icd_code='unique'", metadata())
        self.assertIn("icd9|unique", diagnosis["sql"])
        self.assertIn("icd10|unique", procedure["sql"])
        self.assertEqual(diagnosis["changes"][0]["evidence"]["dictionary"], "d_icd_diagnoses")

    def test_canonical_unknown_full_ambiguous_and_missing_codes_stay_unchanged(self):
        for value in ["icd9|unique", "icd10|unknown_full", "ambiguous", "not_in_dictionary", "bare_valid"]:
            sql = "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='" + value + "'"
            with self.subTest(value=value):
                result = module.compile_namespace("q", sql, metadata())
                self.assertFalse(result["changed"])
                self.assertEqual(result["sql"], sql)

    def test_no_literal_changes_outside_resolved_icd_positions(self):
        sql = "SELECT 'unique' FROM prescriptions WHERE drug='unique'"
        self.assertFalse(module.compile_namespace("q", sql, metadata())["changed"])
        sql = "SELECT a.icd_code FROM diagnoses_icd a JOIN procedures_icd b ON a.subject_id=b.subject_id WHERE icd_code='unique'"
        self.assertFalse(module.compile_namespace("q", sql, metadata())["changed"])

    def test_in_list_and_reverse_comparison_only_replace_targeted_tokens(self):
        sql = "SELECT 'unique' FROM diagnoses_icd d WHERE d.icd_code IN ('unique','ambiguous') AND 'dictionary_only'=d.icd_code"
        result = module.compile_namespace("q", sql, metadata())
        self.assertEqual(len(result["changes"]), 2)
        self.assertIn("SELECT 'unique'", result["sql"])
        self.assertIn("'ambiguous'", result["sql"])
        self.assertIn("icd10|dictionary_only", result["sql"])

    def test_exact_surface_binding_has_one_question_label_and_distinct_code(self):
        sql = "SELECT icd_code FROM d_icd_diagnoses WHERE long_title='long term use'"
        result = module.compile_namespace("Has long-term use occurred?", sql, metadata())
        self.assertTrue(result["changed"])
        self.assertIn("'long-term use'", result["sql"])
        self.assertEqual(result["changes"][0]["evidence"]["kind"], "unique_exact_question_surface")
        self.assertFalse(module.compile_namespace("long-term use and long term use", sql, metadata())["changed"])
        self.assertFalse(module.compile_namespace("long-term use", sql, metadata(), enable_exact_surface=False)["changed"])
        same = "SELECT icd_code FROM d_icd_diagnoses WHERE long_title='same code title'"
        self.assertFalse(module.compile_namespace("same-code title", same, metadata())["changed"])

    def test_record_and_true_source_remain_immutable_and_proposal_is_separate(self):
        source = record()
        original = deepcopy(source)
        with patch.object(module.V4_MODULE, "execute", return_value=[[1]]) as execute:
            normalized = module.normalize_candidate("q", source, metadata())
        self.assertEqual(source, original)
        self.assertEqual(normalized["v5_original_record"], original)
        self.assertEqual(normalized["v5_original_generation_sql"], original["sql"])
        self.assertTrue(normalized["namespace_repair"]["changed"])
        self.assertNotEqual(normalized["sql"], original["sql"])
        execute.assert_called_once_with(normalized["sql"])

    def test_can_revive_only_valid_empty_guard_when_rewrite_changes_sql(self):
        raw = record()
        source = deepcopy(raw)
        source.update(sql="null", guard_rejected=True, pre_guard_sql=raw["sql"],
                      pre_guard_execution={"valid": True, "abstained": False, "empty": True, "error": None},
                      execution={"valid": False, "abstained": True, "empty": None, "error": None}, result_fingerprint=None)
        with patch.object(module.V4_MODULE, "execute", return_value=[[1]]):
            result = module.normalize_candidate("q", source, metadata())
        self.assertTrue(result["namespace_repair"]["revived_gef_empty"])
        self.assertNotEqual(result["sql"], "null")
        self.assertFalse(result["guard_rejected"])
        self.assertEqual(result["v5_original_record"], source)
        self.assertEqual(result["pre_guard_execution"], source["pre_guard_execution"])
        source["pre_guard_sql"] = "SELECT COUNT(*) FROM diagnoses_icd WHERE icd_code='icd9|unique'"
        with patch.object(module.V4_MODULE, "execute") as execute:
            unchanged = module.normalize_candidate("q", source, metadata())
        execute.assert_not_called()
        self.assertEqual(unchanged["sql"], "null")
        self.assertFalse(unchanged["namespace_repair"]["changed"])

    def test_genuine_null_truncation_invalid_syntax_and_other_hard_issue_not_revived(self):
        for case in ["model_null", "truncated", "invalid_syntax", "other_hard"]:
            source = record()
            source.update(sql="null", guard_rejected=case != "model_null", pre_guard_sql=record()["sql"],
                          pre_guard_execution={"valid": case != "invalid_syntax", "abstained": False, "empty": case != "invalid_syntax", "error": None if case != "invalid_syntax" else "syntax error"},
                          execution={"valid": False, "abstained": True, "empty": None, "error": None})
            if case == "truncated": source["finish_reason"] = "length"
            if case == "other_hard": source["contract"]["hard_issues"] = ["introduced_patient_id"]
            with self.subTest(case=case), patch.object(module.V4_MODULE, "execute") as execute:
                result = module.normalize_candidate("q", source, metadata())
            execute.assert_not_called()
            self.assertEqual(result["sql"], "null")
            self.assertFalse(result["namespace_repair"]["changed"])

    def test_raw_baseline_uses_true_llm_source_after_compiler_changes(self):
        rows = []
        for route in ["a", "b", "c"]:
            with patch.object(module.V4_MODULE, "execute", return_value=[[1]]):
                rows.append(module.normalize_candidate("q", record(route), metadata()))
        raw = module.select_v5(rows, "strict3_raw")
        canonical = module.select_v5(rows, "strict3_canonical")
        self.assertEqual(raw["sql"], record()["sql"])
        self.assertIn("icd9|unique", canonical["sql"])
        self.assertTrue(canonical["selection"]["deterministic_proposal_selected"])
        self.assertFalse(raw["selection"]["namespace_compiler_enabled"])

    def test_re_normalization_unwraps_v4_or_v5_to_original_once(self):
        source = record()
        wrapped = {"v4_original_record": deepcopy(source), "sql": "null"}
        with patch.object(module.V4_MODULE, "execute", return_value=[[1]]):
            first = module.normalize_candidate("q", wrapped, metadata())
            second = module.normalize_candidate("q", first, metadata())
        self.assertEqual(second["v5_original_record"], source)
        self.assertNotIn("v5_original_record", second["v5_original_record"])
        self.assertEqual(first["sql"], second["sql"])


if __name__ == "__main__":
    unittest.main()
