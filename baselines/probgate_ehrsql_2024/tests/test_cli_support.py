"""Guard comparison provenance and duplicate-ID handling without any model/SQL."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reproduce import predictions_from, summarize


class CliSupportTests(unittest.TestCase):
    def test_duplicate_t5_predictions_cannot_be_silently_overwritten(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            predictions_from([{"id": "a", "pred": "SELECT 1"}, {"id": "a", "pred": "SELECT 2"}])

    def test_comparison_preserves_precision_and_rejects_mixed_protocols(self):
        experiment = {"id": "test_row", "split": "test", "cached_predictions_available": True,
                      "published_scores": [73.52, -58.87, -191.25, -30826.47]}
        scores = {"n": 1167, "split": "test", "scorer": "official", "execution_errors": [],
                  "scores": {"RS0": 73.5218508997, "RS5": -58.8688946015,
                             "RS10": -191.2596401028, "RSN": -30826.4781491}}
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as tmp:
            run = Path(tmp)
            row = run / "test_row"
            row.mkdir()
            (row / "scores.json").write_text(json.dumps(scores))
            (row / "prediction.metadata.json").write_text("{}")
            with patch("reproduce.registry", return_value=[experiment]), patch("reproduce.provenance", return_value={}):
                report = summarize(run, "official")
                self.assertTrue(report["paper_comparison_mode"])
                self.assertFalse(report["all_published_scores_match_at_2_decimals"])
                self.assertTrue(report["all_published_scores_within_0_01_points"])
                self.assertEqual(report["experiments"][0]["comparison"]["RSN"]["published"], -30826.47)
                with self.assertRaisesRegex(ValueError, "mix"):
                    summarize(run, "author")


if __name__ == "__main__":
    unittest.main()
