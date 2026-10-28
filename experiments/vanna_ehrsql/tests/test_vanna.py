from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from argparse import Namespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark import corpus, run_path
from compare import validate_report
from run import add_gef, RunState
from run_both import infer_interleaved
from vanna_adapter import make_vanna, training_documents, generate
from chromadb.api.types import EmbeddingFunction


class LocalTestEmbedding(EmbeddingFunction):
    def __init__(self):
        pass
    def __call__(self, input):
        return [[(b+1)/256 for b in hashlib.sha256(text.encode()).digest()[:8]] for text in input]
    @staticmethod
    def name():
        return 'vanna-unit-test-only'
    def get_config(self):
        return {}
    @staticmethod
    def build_from_config(config):
        return LocalTestEmbedding()


class FakeClient:
    sql_tokens = 900
    def __init__(self, text='SELECT 1;', finish='stop', error=None):
        self.text, self.finish, self.error = text, finish, error
        self.calls = []
    def call(self, messages, stage, question_id, max_tokens):
        self.calls.append({'messages':messages, 'stage':stage, 'question_id':question_id})
        if self.error:
            raise self.error
        return {'content':self.text, 'finish_reason':self.finish, 'request_hash':'test-only'}


class VannaTests(unittest.TestCase):
    def instance(self, directory, client=None):
        import chromadb
        from chromadb.config import Settings
        memory = chromadb.EphemeralClient(settings=Settings(allow_reset=True, anonymized_telemetry=False))
        memory.reset()
        vn = make_vanna(directory, client=client, examples=1, embedding_function=LocalTestEmbedding(), vector_client=memory)
        # Native train method stores retrieval documents, not model weights.
        with redirect_stdout(io.StringIO()):
            for i in range(17):
                vn.train(ddl=f'CREATE TABLE t{i}(id INTEGER)')
            vn.train(question='A training question', sql='SELECT 1;')
            vn.train(documentation='The benchmark requires SQL or exactly null.')
        return vn

    def test_runs_actual_native_vanna_pipeline_without_auto_training(self):
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            client = FakeClient()
            vn = self.instance(tmp, client)
            before = vn.sql_collection.count()
            row = generate(vn, {'id':'heldout', 'question':'One?'})
            self.assertEqual(vn.generate_sql.__func__.__module__, 'vanna.legacy.base.base')
            self.assertEqual(len(client.calls), 1)
            self.assertEqual(vn.sql_collection.count(), before)
            self.assertTrue(row['variants']['vanna']['execution']['valid'])
            self.assertIn('EHRSQL output contract', client.calls[0]['messages'][0]['content'])
            self.assertIn('CREATE TABLE t16', client.calls[0]['messages'][0]['content'])

    def test_bulk_documents_match_native_train_ids_and_serialization(self):
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            vn = self.instance(tmp)
            expected = training_documents([{'question':'A training question', 'sql':'SELECT 1;'}], {})
            stored = vn.sql_collection.get(include=['documents'])
            self.assertEqual(dict(zip(stored['ids'], stored['documents'])), expected['sql'])
            # null examples can be indexed using Vanna's native API as well.
            vn.train(question='No matching schema', sql='null')
            self.assertEqual(vn.sql_collection.count(), 2)

    def test_explicit_null_and_truncated_output_are_distinct(self):
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            client = FakeClient('null')
            vn = self.instance(tmp, client)
            row = generate(vn, {'id':'a', 'question':'Unavailable information?'})
            self.assertTrue(row['variants']['vanna']['execution']['abstained'])
            client.finish = 'length'
            failed = generate(vn, {'id':'b', 'question':'Other?'})
            self.assertEqual(failed['variants']['vanna']['sql'], '')
            self.assertFalse(failed['variants']['vanna']['execution']['abstained'])
            filtered = add_gef(failed)
            self.assertEqual(filtered['variants']['vanna_gef']['sql'], 'null')
            self.assertEqual(filtered['variants']['vanna']['sql'], '')
            self.assertEqual(len(client.calls), 2)

    def test_preparation_cannot_call_llm_without_transport(self):
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            vn = self.instance(tmp)
            with self.assertRaisesRegex(RuntimeError, 'No LLM transport'):
                generate(vn, {'id':'a', 'question':'One?'})

    def test_api_failure_is_not_a_prediction_or_null(self):
        from bridge import shared
        blocked = shared('model_client').RunBlocked('quota')
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            vn = self.instance(tmp, FakeClient(error=blocked))
            with self.assertRaises(type(blocked)):
                generate(vn, {'id':'a', 'question':'One?'})

    def test_corpus_reads_only_train_labels_and_rejects_overlap(self):
        split = {'train':[{'id':'a', 'question':'Q'}], 'dev':[{'id':'b'}], 'test':[{'id':'c'}]}
        with patch('benchmark.questions', side_effect=lambda s:split[s]), patch('benchmark.load', return_value={'a':'null'}) as reader:
            self.assertEqual(corpus()[0]['sql'], 'null')
            self.assertTrue(str(reader.call_args.args[0]).replace('\\','/').endswith('/data/gold/train/label.json'))
            split['test'] = [{'id':'a'}]
            with self.assertRaisesRegex(ValueError, 'overlap'):
                corpus()

    def test_final_comparison_rejects_partial_or_mismatched_ids(self):
        with self.assertRaises(ValueError):
            validate_report({'split':'test', 'full_benchmark_complete':False}, {'a'})
        with self.assertRaises(ValueError):
            validate_report({'split':'test', 'full_benchmark_complete':True, 'official_normalization':True,
                             'variants':{'vanna':{'per_question':{'b':'correct'}}}}, {'a'})

    def test_run_name_cannot_escape_runs_directory(self):
        with self.assertRaises(ValueError):
            run_path('../other')

    def test_train_state_is_resumable_and_keeps_in_sample_scope(self):
        with tempfile.TemporaryDirectory(prefix='.test-', dir=ROOT) as tmp:
            args = Namespace(run_name='unit_only', split='train', model='fake', primary_variant='vanna',
                             examples=4, limit=0, sql_tokens=900, reasoning_effort='none')
            with patch('run.run_path', return_value=Path(tmp)), patch('run.questions', return_value=[{'id':'a','question':'Q'}]):
                state = RunState(args, {})
                self.assertEqual(state.config['evaluation_scope'], 'in_sample_train_with_self_retrieval')
                with redirect_stdout(io.StringIO()):
                    state.append({'id':'a','question':'Q','variants':{}})
                resumed = RunState(args, {})
                self.assertEqual(list(resumed.pending()), [])
                args.examples = 5
                with self.assertRaisesRegex(ValueError, 'Code/config changed'):
                    RunState(args, {})

    def test_round_robin_shares_pacing_and_stops_both_splits_on_quota(self):
        class Blocked(RuntimeError):
            pass
        class State:
            def __init__(self, split):
                self.args = Namespace(split=split)
                self.rows = []
            def pending(self):
                return iter([{'id':self.args.split+'1'}, {'id':self.args.split+'2'}])
            def append(self, row):
                self.rows.append(row)
        states = [State('test'), State('train')]
        clients = {split:Namespace(headers={}) for split in ['test','train']}
        vn = Namespace(transport=None)
        seen = []
        def generate_fake(instance, item):
            seen.append(item['id'])
            if len(seen)==2:
                self.assertEqual(instance.transport.headers, {'x-ratelimit-remaining-tokens':'123'})
            if len(seen)==3:
                raise Blocked('daily quota')
            instance.transport.headers = {'x-ratelimit-remaining-tokens':'123'}
            return {'id':item['id'], 'variants':{'vanna':{'sql':'null', 'execution':{'valid':False, 'abstained':True, 'empty':None}}}}
        with redirect_stdout(io.StringIO()):
            reason = infer_interleaved(states, clients, vn, generate_fake, Blocked)
        self.assertEqual(reason, 'daily quota')
        self.assertEqual(seen, ['test1', 'train1', 'test2'])
        self.assertEqual([len(s.rows) for s in states], [1,1])


if __name__ == '__main__':
    unittest.main()
