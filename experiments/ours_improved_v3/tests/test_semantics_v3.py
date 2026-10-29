import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from semantics_v3 import BENCHMARK_CONVENTIONS, RULE_EVIDENCE, contract_issues


class SemanticsTests(unittest.TestCase):
    def test_introduced_patient_identifier_only_checks_subject_id_literals(self):
        issue = contract_issues("Count admissions for patient 10000001", "SELECT COUNT(*) FROM admissions WHERE subject_id=10000002", {})
        self.assertTrue(any(x.startswith("introduced_patient_id:") for x in issue["hard_issues"]))
        self.assertFalse(contract_issues("Count admissions for patient 10000001", "SELECT COUNT(*) FROM admissions WHERE subject_id=10000001 AND age>60", {})["hard_issues"])
        self.assertFalse(contract_issues("Find item 220001", "SELECT itemid FROM d_items WHERE itemid=220001", {})["hard_issues"])

    def test_complete_structural_enum_is_hard_but_partial_catalog_is_soft(self):
        sql = "SELECT cost FROM cost c WHERE c.event_type='lab'"
        complete = {("cost", "event_type"): {"labevents", "diagnoses_icd"}}
        self.assertTrue(any(x.startswith("unknown_enum:") for x in contract_issues("lab test cost", sql, complete)["hard_issues"]))
        partial = {("cost", "event_type"): {"values": ["labevents"], "complete": False}}
        self.assertFalse(contract_issues("lab test cost", sql, partial)["hard_issues"])

    def test_explicit_absent_question_literal_does_not_prove_unanswerability(self):
        known = {("d_items", "label"): {"heart rate"}}
        result = contract_issues("Was hypothetical oxygen measured?", "SELECT itemid FROM d_items WHERE label='hypothetical oxygen'", known)
        self.assertFalse(result["hard_issues"])
        self.assertTrue(result["soft_issues"])

    def test_alias_shadowing_does_not_mix_nested_query_enumerations(self):
        known = {("cost", "event_type"): {"labevents"}, ("prescriptions", "route"): {"iv"}}
        sql = "SELECT c.cost FROM cost c WHERE c.event_type='labevents' AND EXISTS(SELECT 1 FROM prescriptions c WHERE c.route='iv')"
        self.assertFalse(contract_issues("List lab costs for IV prescriptions", sql, known)["hard_issues"])
        invalid = sql.replace("'labevents'", "'lab'")
        self.assertEqual(len(contract_issues("List lab costs for IV prescriptions", invalid, known)["hard_issues"]), 1)

    def test_wrapped_equivalent_value_expression_not_falsely_hard_rejected(self):
        known = {("d_items", "label"): {"heart rate"}}
        sql = "SELECT itemid FROM d_items WHERE LOWER(label)='HEART RATE'"
        self.assertFalse(contract_issues("heart rate", sql, known)["hard_issues"])

    def test_output_shape_is_only_advisory_and_never_changes_sql(self):
        sql = "SELECT strftime('%Y', charttime), MAX(value) FROM outputevents GROUP BY strftime('%Y', charttime)"
        result = contract_issues("List the yearly maximum output", sql, {})
        self.assertFalse(result["hard_issues"])
        self.assertTrue(any(x.startswith("output_shape:") for x in result["soft_issues"]))
        self.assertIn("strftime", sql)

    def test_month_day_and_calendar_year_diagnostics_are_soft(self):
        bad = contract_issues("What occurred on this month/07?", "SELECT starttime FROM prescriptions WHERE strftime('%m',starttime)='07'", {})
        good = contract_issues("What occurred on this month/07?", "SELECT starttime FROM prescriptions WHERE date(starttime)='2100-12-07'", {})
        self.assertTrue(any(x.startswith("relative_month_day:") for x in bad["soft_issues"]))
        self.assertFalse(good["soft_issues"])
        self.assertTrue(any(x.startswith("calendar_year:") for x in contract_issues("How many procedures in the previous year?", "SELECT COUNT(*) FROM procedures_icd WHERE charttime>=datetime('2100-12-31','-1 year')", {})["soft_issues"]))
        self.assertFalse(contract_issues("How many procedures in the previous year?", "SELECT COUNT(*) FROM procedures_icd WHERE charttime>='2099-01-01' AND charttime<'2100-01-01'", {})["soft_issues"])

    def test_fractional_days_and_current_visit_are_soft_checks(self):
        result = contract_issues("How many days since the test in this hospital visit?", "SELECT CAST(julianday('2100-12-31')-julianday(MAX(charttime)) AS INT) FROM labevents", {})
        self.assertFalse(result["hard_issues"])
        self.assertTrue(any(x.startswith("fractional_days:") for x in result["soft_issues"]))
        self.assertTrue(any(x.startswith("current_visit:") for x in result["soft_issues"]))

    def test_dense_rank_ties_are_not_rejected(self):
        sql = "SELECT drug FROM (SELECT drug,DENSE_RANK() OVER(ORDER BY COUNT(*) DESC) AS r FROM prescriptions GROUP BY drug) WHERE r<=3"
        self.assertEqual(contract_issues("List the top three most common drugs", sql, {}), {"hard_issues": [], "soft_issues": []})

    def test_no_global_enum_guessing_through_cte_scope(self):
        sql = "WITH x AS (SELECT event_type FROM cost) SELECT * FROM x WHERE event_type='lab'"
        self.assertFalse(contract_issues("List costs", sql, {("cost", "event_type"): {"labevents"}})["hard_issues"])

    def test_evidence_ids_are_real_train_dev_only(self):
        baseline = ROOT.parents[1] / "baselines/probgate_ehrsql_2024"
        for split in ["train", "dev"]:
            rows = json.loads((baseline / "data/inputs" / (split + ".json")).read_text(encoding="utf-8"))["data"]
            ids = {r["id"] for r in rows}
            labels = json.loads((baseline / "data/gold" / split / "label.json").read_text(encoding="utf-8"))
            for evidence in RULE_EVIDENCE.values():
                self.assertEqual({x["split"] for x in evidence}, {"train", "dev"})
                for row in evidence:
                    if row["split"] == split:
                        self.assertIn(row["id"], ids)
                        self.assertNotEqual(labels[row["id"]], "null")
        self.assertIn("fractional", BENCHMARK_CONVENTIONS)
        self.assertIn("DENSE_RANK", BENCHMARK_CONVENTIONS)


if __name__ == "__main__":
    unittest.main()
