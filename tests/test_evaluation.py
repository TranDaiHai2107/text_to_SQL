import unittest
from decimal import Decimal

import pandas as pd

from evaluate import normalize_df


class EvaluationNormalizationTests(unittest.TestCase):
    def test_ignores_row_order_and_output_aliases(self):
        left = pd.DataFrame({"patient": [1, 2], "count": [3.0, 4.0]})
        right = pd.DataFrame({"x": [4.0, 3.0], "y": [2, 1]})
        self.assertEqual(normalize_df(left), normalize_df(right))

    def test_preserves_duplicate_rows(self):
        duplicated = pd.DataFrame({"value": [1, 1]})
        single = pd.DataFrame({"value": [1]})
        self.assertNotEqual(normalize_df(duplicated), normalize_df(single))

    def test_normalizes_nulls_and_text_case(self):
        left = pd.DataFrame({"a": [None], "b": ["  Female "]})
        right = pd.DataFrame({"x": ["female"], "y": [pd.NA]})
        self.assertEqual(normalize_df(left), normalize_df(right))

    def test_treats_equivalent_numeric_types_as_equal(self):
        left = pd.DataFrame({"value": [1, 2.5]})
        right = pd.DataFrame({"value": [Decimal("1.000"), Decimal("2.5000001")]})
        self.assertEqual(normalize_df(left), normalize_df(right))


if __name__ == "__main__":
    unittest.main()
