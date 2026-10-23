"""Small behavioral checks, never running the real benchmark or any model."""
import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from baseline_core import (apply_classifier, apply_entropy, apply_gef, apply_probgate,
                           bottom_logprob, execute_readonly, process_answer, score_answers)


class BaselineTests(unittest.TestCase):
    def test_invalid_logprobs_timeout_and_scorer_fail_explicitly(self):
        with self.assertRaises(ValueError):
            bottom_logprob([{"token": "x", "logprob": float("nan")}], [])
        with self.assertRaises(ValueError):
            bottom_logprob([{"token": "x", "logprob": -1}], [], 0)
        with self.assertRaises(ValueError):
            execute_readonly("SELECT 1", "missing.sqlite", 0)
        with self.assertRaises(ValueError):
            score_answers({"a": [[1]]}, {"a": [[1]]}, scorer="typo")

    def test_probgate_inclusive_rank_and_reserved_tokens(self):
        raw = {k: ["SELECT 1", [{"token": "SELECT", "logprob": -99}, {"token": " x", "logprob": value}]]
               for k, value in [("a", -3), ("b", -2), ("c", -2), ("d", -1)]}
        result, meta = apply_probgate(raw, ["SELECT"], 1)
        self.assertEqual(meta["abstained"], 3)
        self.assertEqual(result["d"], "SELECT 1")

    def test_entropy_strict_greater_than(self):
        self.assertEqual(apply_entropy({"a": "SELECT 1", "b": "SELECT 2"}, {"a": [0.5], "b": [0.6]}, 0.5),
                         {"a": "SELECT 1", "b": "null"})

    def test_classifier_cannot_reverse_labels_or_drop_ids(self):
        with self.assertRaises(ValueError):
            apply_classifier({"a": "SELECT 1"}, {"a": 1})
        with self.assertRaises(ValueError):
            apply_classifier({"a": "SELECT 1"}, {})
        self.assertEqual(apply_classifier({"a": "SELECT 1"}, {"a": "null"}), {"a": "null"})

    def test_scores_include_abstention_and_wrong_query_penalty(self):
        gold = {"a": [[1]], "b": [[2]], "c": "null", "d": [[4]]}
        pred = {"a": [[1]], "b": [[3]], "c": "null", "d": "null"}
        result = score_answers(gold, pred)
        self.assertEqual(result["n"], 4)
        self.assertEqual(result["scores"], {"RS0": 50, "RS5": -75, "RS10": -200, "RSN": -50})

    def test_normalization_preserves_columns_and_duplicates(self):
        self.assertNotEqual(process_answer([[1, 2]]), process_answer([[2, 1]]))
        self.assertNotEqual(process_answer([[1], [1]]), process_answer([[1]]))
        self.assertEqual(process_answer([[2.00001], [1]]), process_answer([[1.0], [2]]))

    def test_gef_empty_result_and_readonly_guard(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as tmp:
            self.assertEqual(Path(tmp).resolve().parent, ROOT.resolve())
            db = Path(tmp) / "tiny.sqlite"
            with closing(sqlite3.connect(db)) as con:
                con.execute("CREATE TABLE sample (value INTEGER)")
                con.execute("INSERT INTO sample VALUES (1)")
                con.commit()
            with self.assertRaises(sqlite3.OperationalError):
                execute_readonly("DELETE FROM sample", db)
            self.assertEqual(execute_readonly("SELECT * FROM sample", db), [(1,)])
            result, errors = apply_gef({"a": "SELECT * FROM sample WHERE value=2", "b": "SELECT * FROM missing", "c": "SELECT * FROM sample", "d": "SELECT 'error message'"}, db)
            self.assertEqual(result, {"a": "null", "b": "null", "c": "SELECT * FROM sample", "d": "SELECT 'error message'"})
            self.assertEqual(len(errors), 1)

    def test_gef_matches_author_on_unsortable_results(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as tmp:
            db = Path(tmp) / "tiny.sqlite"
            with closing(sqlite3.connect(db)) as con:
                con.execute("CREATE TABLE sample (value INTEGER)")
                con.commit()
            sql = "SELECT NULL UNION ALL SELECT 1"
            result, errors = apply_gef({"a": sql}, db)
            self.assertEqual(result["a"], "null")
            self.assertEqual(len(errors), 1)

    def test_author_and_official_scorers_are_not_silently_mixed(self):
        gold, predicted = {"a": [[1.0001]]}, {"a": [[1.0002]]}
        self.assertEqual(score_answers(gold, predicted, scorer="author")["scores"]["RS0"], 0)
        self.assertEqual(score_answers(gold, predicted, scorer="official")["scores"]["RS0"], 100)

    def test_author_scorer_matches_released_pure_functions(self):
        import ast
        tree = ast.parse((ROOT / "upstream/src/scoring_program/scoring_utils.py").read_text())
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {"process_answer", "reliability_score"}]
        env = {}
        exec(compile(ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[])), "original_scoring_functions", "exec"), env)
        gold = {"a": [[1.0001]], "b": "null", "c": [[2]], "d": [[3]]}
        pred = {"a": [[1.0002]], "b": "null", "c": "null", "d": [[3]]}
        normal = lambda d: {k: env["process_answer"](v) if not isinstance(v, str) else v for k, v in d.items()}
        outcomes = env["reliability_score"](normal(gold), normal(pred))
        adapted = score_answers(gold, pred, scorer="author")
        for name, penalty in [("RS0", 0), ("RS5", 5), ("RS10", 10), ("RSN", 4)]:
            expected = 100*sum(penalty*x if x == -1 else x for x in outcomes)/len(outcomes)
            self.assertEqual(adapted["scores"][name], expected)

    def test_adapter_matches_original_notebook_probgate_function(self):
        # Extract one pure function only, never execute a notebook or load pickle.
        import ast
        notebook = json.loads((ROOT / "upstream/src/filter_log_probability.ipynb").read_text())
        function = None
        for cell in notebook["cells"]:
            if cell["cell_type"] != "code":
                continue
            try:
                tree = ast.parse("".join(cell["source"]))
            except SyntaxError:
                continue
            function = next((x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "calculate_log_bottom_k"), function)
        self.assertIsNotNone(function)
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        env = {"reserved": ["SELECT"]}
        exec(compile(module, "original_pure_function", "exec"), env)
        from baseline_core import bottom_logprob
        tokens = [{"token": "SELECT", "logprob": -50}, {"token": " age", "logprob": -2}, {"token": " 10", "logprob": -1}]
        self.assertEqual(bottom_logprob(tokens, env["reserved"], 10), env["calculate_log_bottom_k"](tokens, 10))


if __name__ == "__main__":
    unittest.main()
