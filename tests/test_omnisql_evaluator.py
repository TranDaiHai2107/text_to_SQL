"""Integration smoke test for the pinned, unmodified OmniSQL EX evaluator."""
from __future__ import annotations

import json
from contextlib import closing
import importlib.util
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks" / "omnisql" / "official" / "train_and_evaluate"))
sys.path.insert(0, str(ROOT / "benchmarks" / "omnisql"))

from run_gpt4o_reference import parse_sql, request_spec  # noqa: E402


class OmniSQLEvaluatorSmoke(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("func_timeout"), "OmniSQL scorer dependencies are not installed")
    def test_author_ex_evaluator_scores_execution_results(self) -> None:
        import evaluate_bird
        with tempfile.TemporaryDirectory(prefix="bird_metric_") as tmp:
            root = Path(tmp)
            database_dir = root / "databases" / "toy"
            database_dir.mkdir(parents=True)
            with closing(sqlite3.connect(database_dir / "toy.sqlite")) as connection:
                connection.execute("CREATE TABLE t(x INTEGER)")
                connection.executemany("INSERT INTO t(x) VALUES (?)", [(1,), (2,)])
                connection.commit()
            gold = [
                {"db_id": "toy", "question": "Which values?", "SQL": "SELECT x FROM t"},
                {"db_id": "toy", "question": "How many?", "SQL": "SELECT COUNT(*) FROM t"},
            ]
            predictions = [
                {"pred_sqls": ["SELECT x FROM t ORDER BY x DESC"]},
                {"pred_sqls": ["SELECT 0"]},
            ]
            gold_file = root / "bird_gold.json"
            pred_file = root / "pred.json"
            gold_file.write_text(json.dumps(gold), encoding="utf-8")
            pred_file.write_text(json.dumps(predictions), encoding="utf-8")
            score, sqls = evaluate_bird.run_eval(
                str(gold_file), str(pred_file), str(root / "databases"),
                "greedy_search", False, num_cpus=1, timeout=3)
            self.assertEqual(score, 0.5)
            self.assertEqual(sqls, [row["pred_sqls"][0] for row in predictions])

    def test_sql_extraction_matches_author_rule(self) -> None:
        response = "```sql\nSELECT 1\n```\nchanged\n```sql\nSELECT 2\n```"
        self.assertEqual(parse_sql(response), "SELECT 2")
        self.assertEqual(parse_sql("SELECT 1"), "")

    def test_mini_request_uses_only_public_prompt_and_published_sampling(self) -> None:
        input_seq = "Schema: CREATE TABLE t(x INT). Question: count rows?"
        gold_sql = "SELECT COUNT(*) FROM t"
        greedy = request_spec(input_seq, "gpt-4o-mini-2024-07-18", "greedy_search")
        majority = request_spec(input_seq, "gpt-4o-mini-2024-07-18", "major_voting")
        self.assertEqual((greedy["temperature"], greedy["n"]), (0.0, 1))
        self.assertEqual((majority["temperature"], majority["n"]), (0.8, 8))
        self.assertEqual(greedy["messages"], [{"role": "user", "content": input_seq}])
        self.assertNotIn(gold_sql, json.dumps(greedy))
        self.assertNotIn(gold_sql, json.dumps(majority))


if __name__ == "__main__":
    unittest.main()
