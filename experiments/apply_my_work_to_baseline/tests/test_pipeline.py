from contextlib import closing
from pathlib import Path
import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import preserve_rewrite, run_question, DEFAULT_MODES
from sql_runtime import clean_sql, execute, validate
from model_client import duration_seconds, RunBlocked
from evaluate import evaluate, scoring_sql
from retrieval import ThreeRAG
from settings import BASELINE


class FakeRAG:
    schema = {"patients":"CREATE TABLE patients(subject_id INTEGER)"}
    def retrieve(self, question, mode):
        return {"tables":["patients"], "medical":[], "examples":[]}


class FakeClient:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.stages = []
        self.messages = []
    def call(self, messages, stage, question_id, max_tokens):
        self.stages.append(stage)
        self.messages.append(copy.deepcopy(messages))
        reply = next(self.replies)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, dict):
            return {"request_hash":str(len(self.stages)), **reply}
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

    def test_rewrite_cannot_add_numbers_negate_or_swap_comparison(self):
        for question, changed in [
            ("Show glucose for patient 123.", "Show glucose for patient 123 in 2100."),
            ("Show glucose for patient 123.", "Show no glucose for patient 123."),
            ("Show first glucose for patient 123.", "Show last glucose for patient 123."),
            ("Show values above 5.", "Show values below 5."),
            ("Show values > 5.", "Show values < 5."),
            ("Values between 5 and 10.", "Values between 10 and 5."),
        ]:
            with self.subTest(question=question):
                self.assertEqual(preserve_rewrite(question, changed)[0], question)

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

    def test_missing_schema_is_restored_on_error_without_changing_initial_branch(self):
        rag = FakeRAG()
        rag.schema = {**rag.schema, "cost":"CREATE TABLE cost(subject_id INTEGER, cost REAL)"}
        client = FakeClient(["SELECT amount FROM cost", "SELECT cost FROM cost"])
        bad = {"valid":False, "abstained":False, "empty":None, "error":"no such column: amount"}
        good = {"valid":True, "abstained":False, "empty":False, "error":None}
        with patch("pipeline.outcome", side_effect=[bad, good]):
            row = run_question({"id":"a", "question":"Costs?"}, ["three_rag", "three_rag_agentic"], rag, client)
        self.assertNotIn("CREATE TABLE cost", client.messages[0][1]["content"])
        self.assertIn("CREATE TABLE cost", client.messages[1][1]["content"])
        self.assertEqual(row["variants"]["three_rag"]["retrieval"]["tables"], ["patients"])
        self.assertTrue(row["variants"]["three_rag_agentic"]["schema_restored_for_repair"])

    def test_default_ablation_shares_generations_and_has_matched_gef_controls(self):
        client = FakeClient(["SELECT subject_id FROM patients"]*3)
        good = {"valid":True, "abstained":False, "empty":False, "error":None}
        with patch("pipeline.outcome", return_value=good):
            row = run_question({"id":"a", "question":"Patients?"}, DEFAULT_MODES, FakeRAG(), client)
        self.assertEqual(client.stages, ["sql_base", "sql_examples", "sql_full_schema"])
        self.assertEqual(set(row["variants"]), set(DEFAULT_MODES))
        self.assertEqual(row["variants"]["base"]["call_hashes"], row["variants"]["base_gef"]["call_hashes"])

    def test_truncated_null_is_a_failure_until_explicit_gef(self):
        client = FakeClient([{"content":"null", "finish_reason":"length"}])
        row = run_question({"id":"a", "question":"Patients?"}, ["base", "base_gef"], FakeRAG(), client)
        self.assertEqual(row["variants"]["base"]["sql"], "")
        self.assertFalse(row["variants"]["base"]["execution"]["abstained"])
        self.assertEqual(row["variants"]["base_gef"]["sql"], "null")
        self.assertTrue(row["variants"]["base_gef"]["gef_filtered"])
        self.assertEqual(scoring_sql({"sql":"null", "execution":{"valid":False, "abstained":False}}), "")
        self.assertEqual(scoring_sql({"sql":"SELECT 1", "execution":{"valid":False, "abstained":False}}), "")

    def test_full_schema_retrieval_keeps_all_tables_and_retrieves_examples(self):
        class Collection:
            def __init__(self, name):
                self.name = name
            def query(self, **kwargs):
                return {"ids":[[self.name]], "metadatas":[[{"source":self.name}]], "distances":[[0.1]]}
        rag = ThreeRAG.__new__(ThreeRAG)
        rag.schema = {name:name for name in ["patients", "admissions", "cost", "transfers"]}
        rag.query_cache = {"Costs?": [[0.1]]}
        # No schema collection: accessing it would fail this test.
        rag.collections = {name:Collection(name) for name in ["medical_dictionary", "sql_examples_train"]}
        context = rag.retrieve("Costs?", "full_schema")
        self.assertEqual(context["tables"], sorted(rag.schema))
        self.assertEqual(len(context["medical"]), 1)
        self.assertEqual(len(context["examples"]), 1)

    def test_scoring_keeps_failures_and_separates_false_answers_from_refusals(self):
        with tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT) as tmp:
            root = Path(tmp)
            gold_dir = root/"baseline/data/gold/dev"
            gold_dir.mkdir(parents=True)
            (root/"baseline/baseline_core.py").write_bytes((BASELINE/"baseline_core.py").read_bytes())
            gold = {"a":[[1]], "b":[[2]], "c":"null", "d":[[4]]}
            (gold_dir/"answer.json").write_text(json.dumps(gold))
            run = root/"run"
            run.mkdir()
            (run/"config.json").write_text(json.dumps({"split":"dev", "modes":["base", "base_gef"], "primary_variant":"base_gef"}))
            good = {"valid":True, "abstained":False, "empty":False, "error":None}
            abstained = {"valid":False, "abstained":True, "empty":None, "error":None}
            failed = {"valid":False, "abstained":False, "empty":None, "error":"truncated"}
            records = []
            for key in gold:
                sql = "null" if key=="b" else "" if key=="d" else "SELECT 1"
                record = {"sql":sql, "execution":abstained if key=="b" else failed if key=="d" else good}
                filtered = {**record, "sql":"null", "gef_filtered":True} if key=="d" else record
                records.append({"id":key, "variants":{"base":record, "base_gef":filtered}})
            (run/"records.jsonl").write_text("\n".join(json.dumps(r) for r in records))
            with patch("evaluate.BASELINE", root/"baseline"), patch("evaluate.execute_readonly", return_value=[(1,)]):
                report = evaluate(run)
            base = report["variants"]["base"]
            self.assertEqual(base["answerable_ex_denominator"], 3)
            self.assertEqual(base["wrong"], 2)
            self.assertEqual(base["reliability"]["false_answers_on_unanswerable"], 1)
            self.assertEqual(base["reliability"]["false_abstentions_on_answerable"], 1)
            self.assertEqual(report["variants"]["base_gef"]["wrong"], 1)
            self.assertFalse(report["full_benchmark_complete"])
            self.assertEqual(report["paired_deltas_vs_matched_gef_base"], {})

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

