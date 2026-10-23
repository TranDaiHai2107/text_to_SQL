import unittest
from decimal import Decimal

import pandas as pd

from unittest.mock import patch
from evaluate import compute_metrics, evaluate_one, normalize_df


class EvaluationNormalizationTests(unittest.TestCase):
    def test_ignores_row_order_and_output_aliases(self):
        left = pd.DataFrame({"patient": [1, 2], "count": [3.0, 4.0]})
        right = pd.DataFrame({"x": [2, 1], "y": [4.0, 3.0]})
        self.assertEqual(normalize_df(left), normalize_df(right))

    def test_swapped_column_values_do_not_count_as_equal(self):
        self.assertNotEqual(normalize_df(pd.DataFrame([[1, 2]])),
                            normalize_df(pd.DataFrame([[2, 1]])))

    def test_preserves_duplicate_rows(self):
        duplicated = pd.DataFrame({"value": [1, 1]})
        single = pd.DataFrame({"value": [1]})
        self.assertNotEqual(normalize_df(duplicated), normalize_df(single))

    def test_normalizes_nulls_but_preserves_text_case_and_spaces(self):
        left = pd.DataFrame({"a": [None], "b": ["Female"]})
        right = pd.DataFrame({"x": [pd.NA], "y": ["Female"]})
        self.assertEqual(normalize_df(left), normalize_df(right))
        self.assertNotEqual(normalize_df(left), normalize_df(pd.DataFrame([[None, "female"]])))
        self.assertNotEqual(normalize_df(left), normalize_df(pd.DataFrame([[None, " Female "]])))

    def test_treats_equivalent_numeric_types_as_equal(self):
        left = pd.DataFrame({"value": [1, 2.5]})
        right = pd.DataFrame({"value": [Decimal("1.000"), Decimal("2.5000001")]})
        self.assertEqual(normalize_df(left), normalize_df(right))

    def test_generation_failure_stays_in_ex_denominator(self):
        item = {"id": "a", "question_vi": "test"}
        with patch("evaluate.generate_sql", side_effect=RuntimeError("generation failed")):
            failed = evaluate_one(item, "base", pd.DataFrame([[1]]))
        self.assertIs(failed["execution_match"], False)
        passed = {**failed, "id": "b", "valid_sql": True, "execution_match": True, "error": None}
        metrics = compute_metrics([passed, failed])
        self.assertEqual(metrics["ex"], 50)
        self.assertEqual(metrics["ex_eligible"], 2)

    def test_old_null_failure_does_not_inflate_ex(self):
        rows = [{"valid_sql": True, "execution_match": True, "gold_empty": False, "latency_s": 1},
                {"valid_sql": False, "execution_match": None, "gold_empty": False, "latency_s": 1},
                {"valid_sql": True, "execution_match": None, "gold_empty": True, "latency_s": 1}]
        self.assertEqual(compute_metrics(rows)["ex"], 50)
        self.assertEqual(compute_metrics(rows)["empty_gold"], 1)


if __name__ == "__main__":
    unittest.main()
