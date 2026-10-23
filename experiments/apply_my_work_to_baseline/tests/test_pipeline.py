from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import preserve_rewrite, run_question
from sql_runtime import clean_sql, execute, validate
from model_client import duration_seconds, RunBlocked


class FakeRAG:
    schema = {"patients":"CREATE TABLE patients(subject_id INTEGER)"}
    def retrieve(self, question, mode):
        return {"tables":["patients"], "medical":[], "examples":[]}


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.stages = []
    def call(self, messages, stage, question_id, max_tokens):
        self.stages.append(stage)
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        return {"content":reply, "finish_reason":"stop", "request_hash":str(len(self.stages))}


class PipelineTests(unittest.TestCase):
    def test_sql_runtime_checks_actual_schema_and_is_readonly(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as tmp:
            db = Path(tmp)/"tiny.sqlite"
            with closing(sqlite3.connect(db)) as con:
                con.execute("CREATE TABLE patients(subject_id INTEGER)")
                con.execute("INSERT INTO patients VALUES(1)")
                con.commit()
            self.assertIsNone(validate("WITH x AS (SELECT subject_id FROM patients) SELECT * FROM x", db))
            self.assertIsNotNone(validate("SELECT anchor_age FROM patients", db))
            self.assertIsNotNone(validate("DELETE FROM patients", db))
            self.assertIsNotNone(validate("SELECT 1; SELECT 2", db))
            with self.assertRaises(ValueError):
                execute("DELETE FROM patients", db)
            self.assertEqual(execute("SELECT * FROM patients", db), [(1,)])

    def test_rewrite_cannot_drop_ids_dates_or_temporal_constraints(self):
        q = "Show first 'glucose' value for patient 10021118 in 2100."
        self.assertEqual(preserve_rewrite(q, "Show glucose for patient 10021119.")[0], q)
        self.assertEqual(preserve_rewrite(q, "Show 'glucose' value for patient 10021118 in 2100.")[0], q)
        self.assertEqual(preserve_rewrite(q, q)[1], "identity")

    def test_stage_reuse_and_native_rewrite_identity(self):
        client = FakeClient(["SELECT subject_id FROM patients", "How many patients?"])
        good = {"valid":True, "abstained":False, "empty":False, "error":None}
        modes = ["three_rag", "three_rag_agentic", "three_rag_native_rewrite_agentic",
                 "three_rag_standalone_rewrite_agentic", "three_rag_agentic_gef"]
        with patch("pipeline.outcome", return_value=good):
            row = run_question({"id":"a", "question":"How many patients?"}, modes, FakeRAG(), client)
        self.assertEqual(client.stages, ["sql_full", "standalone_rewrite"])
        self.assertEqual(len({v["sql"] for v in row["variants"].values()}), 1)
        self.assertFalse(row["variants"]["three_rag_native_rewrite_agentic"]["rewrite"]["changed"])

    def test_agentic_correction_uses_errors_not_gold(self):
        client = FakeClient(["SELECT missing FROM patients", "SELECT subject_id FROM patients"])
        bad = {"valid":False, "abstained":False, "empty":None, "error":"no such column: missing"}
        good = {"valid":True, "abstained":False, "empty":False, "error":None}
        with patch("pipeline.outcome", side_effect=[bad, good]):
            row = run_question({"id":"a", "question":"Patients?"}, ["three_rag", "three_rag_agentic"], FakeRAG(), client)
        self.assertEqual(row["variants"]["three_rag"]["sql"], "SELECT missing FROM patients")
        self.assertEqual(row["variants"]["three_rag_agentic"]["attempts"], 2)

    def test_quota_failure_never_turns_into_a_null_prediction(self):
        client = FakeClient([RunBlocked("quota")])
        with self.assertRaises(RunBlocked):
            run_question({"id":"a", "question":"Patients?"}, ["base"], FakeRAG(), client)

    def test_clock_and_rate_duration(self):
        self.assertIn("2100-12-31 23:59:00", clean_sql("SELECT datetime(current_time)"))
        self.assertAlmostEqual(duration_seconds("975ms"), .975)
        self.assertAlmostEqual(duration_seconds("1m26.4s"), 86.4)


if __name__ == "__main__":
    unittest.main()

