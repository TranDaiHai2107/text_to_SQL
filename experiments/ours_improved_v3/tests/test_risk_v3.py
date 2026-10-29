"""Focused pure-policy tests: no network, corpus, database or model access."""
from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("risk_v3_under_test", Path(__file__).resolve().parents[1] / "risk_v3.py")
risk = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(risk)


def candidate(route, sql="SELECT 1", fingerprint="one", *, empty=False, valid=True,
              hard=(), soft=(), trivial=False, call_hash=None):
    return {
        "route": route, "sql": sql,
        "execution": {"valid": valid, "abstained": sql == "null",
                      "empty": None if sql == "null" or not valid else empty,
                      "error": None if valid or sql == "null" else "SQL validation failed"},
        "static_issues": list(hard), "contract": {"hard_issues": [], "soft_issues": list(soft)},
        "call_hashes": [call_hash or route], "result_fingerprint": fingerprint,
        "result_summary": {"rows": 0 if empty else 1, "columns": 1, "trivial_scalar": trivial},
    }


def model_null(route):
    return candidate(route, sql="null", fingerprint=None, valid=False)


def score(gold, predicted):
    if set(gold) != set(predicted):
        raise ValueError("Missing IDs")
    outcomes = {
        key: "correct" if gold[key] == predicted[key]
        else "abstained_answerable" if gold[key] != "null" and predicted[key] == "null"
        else "wrong" for key in gold
    }
    correct = sum(value == "correct" for value in outcomes.values())
    wrong = sum(value == "wrong" for value in outcomes.values())
    return {
        "n": len(gold), "correct": correct, "wrong": wrong,
        "abstained_answerable": sum(value == "abstained_answerable" for value in outcomes.values()),
        "per_question": outcomes,
        "scores": {name: 100 * (correct - penalty * wrong) / len(gold)
                   for name, penalty in [("RS0", 0), ("RS5", 5), ("RS10", 10), ("RSN", len(gold))]},
    }


class RiskTests(unittest.TestCase):
    def test_direct_preserves_a_without_mutating_any_input(self):
        candidates = [candidate("a"), candidate("b", sql="SELECT 2", fingerprint="two")]
        original = deepcopy(candidates)
        chosen = risk.select_record(candidates, "direct_guard")
        self.assertEqual(chosen["selected_candidate_index"], 0)
        self.assertEqual(chosen["call_hashes"], ["a", "b"])
        chosen["execution"]["valid"] = False
        self.assertEqual(candidates, original)

    def test_guarded_a_does_not_silently_turn_into_b(self):
        chosen = risk.select_record([candidate("a", hard=["Unrequested patient"]), candidate("b")], "direct_guard")
        self.assertEqual(chosen["sql"], "null")
        self.assertIsNone(chosen["selected_candidate_index"])

    def test_null_consensus_is_explicit_and_does_not_invent_sql_evidence(self):
        chosen = risk.select_record([model_null("a"), model_null("b")], "strict_two_agree")
        self.assertEqual(chosen["selection"]["reason"], "genuine_model_null_consensus")
        self.assertFalse(chosen["selection"]["features"]["all_nonnull_agree"])
        self.assertFalse(chosen["selection"]["features"]["execution_groups"])

    def test_explicit_guard_abstentions_are_not_genuine_model_null_votes(self):
        rows = [model_null("a"), model_null("b")]
        for row in rows:
            row.update(guard_rejected=True, pre_guard_sql="SELECT nonexistent FROM missing_table",
                       pre_guard_execution={"valid": False, "abstained": False, "empty": None,
                                            "error": "no such table: missing_table"})
        chosen = risk.select_record(rows, "strict_two_agree")
        self.assertEqual(chosen["sql"], "null")
        self.assertEqual(chosen["selection"]["features"]["genuine_model_null_indices"], [])
        self.assertEqual(chosen["selection"]["features"]["guard_rejected_indices"], [0, 1])
        self.assertEqual(chosen["selection"]["reason"], "insufficient_nonempty_execution_consensus")

    def test_empty_failed_or_missing_results_never_agree(self):
        cases = [
            [candidate("a", empty=True), candidate("b", empty=True)],
            [candidate("a", valid=False), candidate("b", valid=False)],
            [candidate("a", fingerprint=None), candidate("b", fingerprint=None)],
            [candidate("a"), model_null("b")],
        ]
        for rows in cases:
            with self.subTest(rows=rows):
                self.assertEqual(risk.select_record(rows, "majority_two_of_three")["sql"], "null")

    def test_cached_duplicate_request_is_not_two_votes(self):
        rows = [candidate("a", call_hash="same"), candidate("b", call_hash="same")]
        self.assertEqual(risk.select_record(rows, "strict_two_agree")["sql"], "null")
        rows[1]["call_hashes"] = ["different"]
        self.assertEqual(risk.select_record(rows, "strict_two_agree")["selected_candidate_index"], 0)

    def test_majority_can_choose_b_against_a_without_overwriting_a(self):
        rows = [candidate("a", sql="SELECT 2", fingerprint="two"), candidate("b"), candidate("c")]
        self.assertEqual(risk.select_record(rows, "strict_two_agree")["sql"], "null")
        chosen = risk.select_record(rows, "majority_two_of_three")
        self.assertEqual(chosen["selected_candidate_index"], 1)
        self.assertEqual(chosen["selection"]["supporting_candidate_indices"], [1, 2])
        self.assertEqual(rows[0]["sql"], "SELECT 2")

    def test_strict_three_requires_three_real_agreeing_executions(self):
        rows = [candidate("a"), candidate("b")]
        self.assertEqual(risk.select_record(rows, "strict_three_agree")["sql"], "null")
        rows.append(candidate("c"))
        self.assertEqual(risk.select_record(rows, "strict_three_agree")["selected_candidate_index"], 0)
        rows[2] = candidate("c", valid=False)
        self.assertEqual(risk.select_record(rows, "strict_three_agree")["sql"], "null")

    def test_structural_consensus_keeps_predicates_not_just_matching_values(self):
        rows = [candidate("a", sql="SELECT x FROM t WHERE x=1"),
                candidate("b", sql="SELECT x FROM t WHERE x>0")]
        self.assertEqual(risk.select_record(rows, "majority_two_of_three")["selected_candidate_index"], 0)
        self.assertEqual(risk.select_record(rows, "structural_consensus")["sql"], "null")
        rows[1]["sql"] = " select x from t where x = 1; -- same syntax "
        self.assertEqual(risk.select_record(rows, "structural_consensus")["selected_candidate_index"], 0)

    def test_trivial_scalar_exclusion_and_soft_issue_consensus(self):
        rows = [candidate("a", trivial=True), candidate("b", trivial=True)]
        self.assertEqual(risk.select_record(rows, "agree_exclude_trivial")["sql"], "null")
        rows = [candidate("a", soft=["Unclear admission scope"]), candidate("b")]
        self.assertEqual(risk.select_record(rows, "consensus_no_soft_issues")["sql"], "null")
        rows[0]["contract"]["soft_issues"] = []
        self.assertEqual(risk.select_record(rows, "consensus_no_soft_issues")["selected_candidate_index"], 0)

    def test_malformed_and_provider_failures_raise_instead_of_abstaining(self):
        for row in [{}, {**model_null("a"), "api_error": "HTTP 402"},
                    {**model_null("a"), "execution": {"valid": False, "abstained": True, "empty": None, "error": "Malformed API output"}}]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                risk.select_record([row, candidate("b")], "strict_two_agree")

    def test_fit_cannot_select_all_null_when_coverage_below_floor(self):
        rows = [{"id": str(i), "partition": "tune", "candidates": [candidate(f"a{i}"), candidate(f"b{i}", fingerprint="different")]}
                for i in range(10)]
        gold = {str(i): [[1]] if i < 6 else "null" for i in range(10)}
        answers = {str(i): [[[1]], [[2]]] for i in range(10)}
        result = risk.fit_policy(rows, gold, answers, score_fn=score,
                                 policies=["direct_guard", "strict_two_agree"])
        self.assertEqual(result["selected_policy"], "direct_guard")
        rejected = result["tune_grid"][1]
        self.assertGreater(rejected["scores"]["RS10"], result["tune_grid"][0]["scores"]["RS10"])
        self.assertFalse(rejected["feasible"])

    def test_no_feasible_policy_exposes_grid_and_does_not_lower_floor(self):
        rows = [{"id": "x", "candidates": [model_null("a"), model_null("b")]}]
        with self.assertRaises(risk.NoFeasiblePolicyError) as error:
            risk.fit_policy(rows, {"x": "null"}, {"x": ["null", "null"]}, score_fn=score)
        self.assertTrue(error.exception.grid)
        with self.assertRaises(ValueError):
            risk.fit_policy(rows, {"x": "null"}, {"x": ["null", "null"]}, score_fn=score, min_coverage=.34)

    def test_tied_rs10_prefers_precision_and_fewer_mistakes(self):
        rows = []
        gold = {}
        answers = {}
        for i in range(17):
            # Six accepted correct answers plus ten correct A answers withheld
            # and one wrong A answer withheld exactly tie RS10 with direct A.
            a_answer = [[1]] if i < 16 else [[2]]
            rows.append({"id": str(i), "candidates": [candidate(f"a{i}"), candidate(f"b{i}", fingerprint="one" if i < 6 else "other")]})
            gold[str(i)] = [[1]]
            answers[str(i)] = [a_answer, [[1]]]
        result = risk.fit_policy(rows, gold, answers, score_fn=score,
                                 policies=["direct_guard", "strict_two_agree"])
        self.assertEqual(result["selected_policy"], "strict_two_agree")
        self.assertAlmostEqual(result["tune_grid"][0]["scores"]["RS10"], result["tune_grid"][1]["scores"]["RS10"])

    def test_fit_rejects_audit_extra_missing_duplicate_and_candidate_misalignment(self):
        base = {"id": "x", "candidates": [candidate("a"), candidate("b")]}
        gold, answers = {"x": [[1]]}, {"x": [[[1]], [[1]]]}
        cases = [([dict(base, partition="audit")], gold, answers, {}),
                 ([base], dict(gold, test=[[1]]), answers, {}),
                 ([base, base], gold, answers, {}),
                 ([base], gold, {"x": [[[1]]]}, {}),
                 ([base], gold, answers, {"allowed_tune_ids": ["audit"]})]
        for rows, target, executed, kwargs in cases:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                risk.fit_policy(rows, target, executed, score_fn=score, **kwargs)


if __name__ == "__main__":
    unittest.main()
