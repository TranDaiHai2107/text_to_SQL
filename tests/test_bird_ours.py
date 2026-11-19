"""Offline checks for the Ours BIRD port (no API, needs the BIRD dev data locally)."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
DATA = ROOT / 'data' / 'benchmarks' / 'bird'
DEV = DATA / 'dev_20240627'


class ScriptedModel:
    """Returns a fixed JSON object per stage; records every request payload."""

    def __init__(self, sqls, samples=()):
        self.sqls, self.requests, self.samples = list(sqls), [], list(samples)

    def sample(self, stage, messages, tokens, *, n, temperature):
        self.requests.append((stage + '_samples', json.loads(messages[1]['content'])))
        return {'contents': [json.dumps({'sql': q, 'unresolved': []}) for q in self.samples[:n]],
                'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}

    def complete(self, stage, messages, tokens):
        payload = json.loads(messages[1]['content'])
        self.requests.append((stage, payload))
        q = payload['original_question']
        if stage == 'link':
            obj = {'requirements': [{'id': 'r1', 'kind': 'output', 'span': q, 'description': 'answer'}],
                   'links': [{'requirement_id': 'r1', 'span': q, 'table': 'FRPM', 'column': 'county name',
                              'role': 'filter'}], 'joins': [], 'ambiguities': []}
        elif stage == 'decompose':
            obj = {'steps': [{'id': 's1', 'operation': 'project', 'depends_on': [], 'requirement_ids': ['r1'],
                              'tables': ['frpm'], 'description': 'project'}], 'output_step': 's1'}
        elif stage in ('generate', 'repair'):
            obj = {'sql': self.sqls.pop(0) if self.sqls else 'SELECT 1 FROM frpm', 'unresolved': []}
        elif stage == 'select':
            obj = {'selected_id': payload['candidates'][0]['id'], 'reason': 'first', 'assessments': []}
        else:
            obj = {'checks': [], 'verdict': 'unknown'}
        return {'content': json.dumps(obj), 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}


@unittest.skipUnless((DEV / 'dev.json').exists(), 'BIRD dev data not downloaded')
class BirdOursTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ehrqa.bird.database import BirdDatabase
        gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
        prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
        cls.gold = gold[0]
        cls.db = BirdDatabase(DEV / 'dev_databases' / 'california_schools' / 'california_schools.sqlite',
                              prompts[0]['input_seq'])

    def run_pipeline(self, sqls, **flags):
        from ehrqa.agentic.pipeline import Config, FullAgentic
        from ehrqa.agentic.retrieval import SequentialRAG
        model = ScriptedModel(sqls, flags.pop('_samples', ()))
        rag = SequentialRAG(self.db, lambda q: {'items': []})
        pipeline = FullAgentic(self.db, rag, model, Config(profile='bird', parallel_branches=True, **flags))
        return pipeline.run(self.gold['question'], evidence=self.gold['evidence']), model

    def test_schema_is_case_insensitive(self):
        s = self.db.schema
        self.assertTrue(s.has_ref('FRPM.county name'))
        self.assertEqual(s.canonical_ref('FRPM.county name'), 'frpm.County Name')
        self.assertTrue(s.inspect('SELECT `County Name` FROM FRPM')['valid'])

    def test_v6_flow_votes_and_never_sends_gold(self):
        good = "SELECT MAX(`Free Meal Count (K-12)` / `Enrollment (K-12)`) FROM frpm WHERE `County Name` = 'Alameda'"
        output, model = self.run_pipeline([good, good, 'SELECT nosuch FROM frpm', good], fingerprint_selection=True)
        self.assertEqual(output['status'], 'answered')
        self.assertEqual(output['sql'], good)
        self.assertIn('fingerprint_majority', output['reason'])
        sent = json.dumps([p for _, p in model.requests])
        self.assertNotIn(self.gold['SQL'], sent)
        self.assertTrue(all(p.get('external_knowledge') == self.gold['evidence'] for _, p in model.requests))

    def test_v7_samples_vote_only_on_values(self):
        good = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"
        empty = "SELECT `County Name` FROM frpm WHERE `County Name` = 'nowhere'"
        other = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alpine' LIMIT 1"
        samples = [good, good, other, empty, empty, empty]
        output, model = self.run_pipeline([empty, empty, empty], fingerprint_selection=True,
                                          extra_samples=6, value_vote=True, _samples=samples)
        # Six empty results do not outvote two agreeing results with values.
        self.assertEqual(output['sql'], good)
        self.assertEqual(sum(stage == 'generate_samples' for stage, _ in model.requests), 1)
        self.assertTrue(output['reason'].startswith('v6 selection: value_vote_'))

    def test_sqlite_error_feeds_repair(self):
        good = "SELECT `County Name` FROM frpm LIMIT 1"
        output, model = self.run_pipeline(['SELECT nosuch FROM frpm', good], adaptive_single=True)
        self.assertEqual(output['status'], 'answered')
        repair = [p for stage, p in model.requests if stage == 'repair']
        self.assertTrue(repair and 'nosuch' in repair[0]['technical_errors'][0])

    def test_linker_interface_normalization(self):
        from ehrqa.agentic import contracts
        q = 'What is the highest eligible free rate for K-12 students in the schools in Alameda County?'
        obj = {'requirements': [{'id': 'r1', 'kind': 'entity', 'span': 'schools in Alameda County',
                                 'description': 'county filter'}],
               'links': [{'requirement_id': 'r1', 'span': 'Alameda', 'table': 'frpm',
                          'column': 'County Name, County Code', 'role': 'filter'},
                         {'requirement_id': 'r1', 'span': 'not in question', 'table': 'frpm',
                          'column': 'no_such_column', 'role': 'x'}], 'joins': [], 'ambiguities': []}
        obj, warnings = contracts.normalize_linking_generic(q, obj, self.db.schema)
        contracts.linking(q, obj, self.db.schema, [])  # valid after repair
        self.assertEqual([l['column'] for l in obj['links']], ['County Name', 'County Code'])
        self.assertTrue(any(r['kind'] == 'output' and r['span'] == q for r in obj['requirements']))
        self.assertTrue(any('12' in r['span'] for r in obj['requirements']))
        plan = {'steps': [{'id': 's1', 'operation': 'filter|join', 'depends_on': [], 'requirement_ids': ['r1'],
                           'tables': ['FRPM'], 'description': 'filter'}], 'output_step': 's1'}
        plan, _ = contracts.normalize_decomposition_generic(plan, obj['requirements'])
        contracts.decomposition(plan, obj['requirements'], self.db.schema)
        self.assertEqual(plan['steps'][0]['operation'], 'filter')

    def test_value_retrieval_finds_stored_value(self):
        records = self.db.catalog_search(self.gold['question'] + ' ' + self.gold['evidence'], [])
        self.assertIn(('frpm', 'County Name', 'Alameda'), {(r['table'], r['column'], r['code']) for r in records})


if __name__ == '__main__':
    unittest.main()


class TextModel:
    def __init__(self, greedy, samples, repair='', select='Answer: 1'):
        self.greedy, self.samples, self.repair, self.select = greedy, samples, repair, select
        self.prompts = []

    def complete_text(self, stage, messages, tokens):
        self.prompts.append((stage, messages[0]['content']))
        text = {'generate': self.greedy, 'repair': self.repair, 'select': self.select}[stage]
        return {'content': text, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}

    def sample_text(self, stage, messages, tokens, *, n, temperature):
        self.prompts.append((stage, messages[0]['content']))
        if stage == 'select':
            return {'contents': [self.select] * n, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}
        return {'contents': self.samples[:n], 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}


def fence(sql):
    return 'reasoning...\n```sql\n' + sql + '\n```'


@unittest.skipUnless((DEV / 'dev.json').exists(), 'BIRD dev data not downloaded')
class OursV8Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ehrqa.bird.database import BirdDatabase
        gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
        cls.prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
        cls.gold = gold[0]
        cls.db = BirdDatabase(DEV / 'dev_databases' / 'california_schools' / 'california_schools.sqlite',
                              cls.prompts[0]['input_seq'])

    def run_v8(self, model, **flags):
        from ehrqa.bird.ours_v8 import OursV8, V8Config
        examples = lambda q: {'items': [{'question': 'Q?', 'external_knowledge': '', 'sql': 'SELECT 1'}]}
        return OursV8(self.db, model, examples=examples, config=V8Config(**flags)).run(
            self.gold['question'], self.gold['evidence'], self.prompts[0]['input_seq'])

    def test_repair_and_value_vote(self):
        good = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"
        empty = "SELECT `County Name` FROM frpm WHERE `County Name` = 'nowhere'"
        model = TextModel(fence('SELECT nosuch FROM frpm'), [fence(empty)] * 5 + [fence(good)] * 2,
                          repair=fence(good))
        output = self.run_v8(model, samples=7)
        self.assertEqual(output['sql'], good)
        self.assertTrue(output['reason'].startswith('vote_3_of_3'))
        stage, repair = [p for p in model.prompts if p[0] == 'repair'][0]
        self.assertIn('no such column', repair)
        prompt = model.prompts[0][1]
        self.assertIn("frpm.`County Name` = 'Alameda'", prompt)
        self.assertLess(prompt.index('Examples from other databases'), prompt.index('\nInstructions:\n'))
        self.assertTrue(all(self.gold['SQL'] not in p for _, p in model.prompts))

    def test_tie_goes_to_selector(self):
        a = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"
        b = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alpine' LIMIT 1"
        model = TextModel(fence(a), [fence(b)], select='... Answer: 2')
        output = self.run_v8(model, samples=1)
        self.assertEqual(output['sql'], b)
        self.assertEqual(output['reason'], 'tie_selected_2')


class OursV9Test(OursV8Test):
    def run_v9(self, model, **flags):
        from ehrqa.bird.ours_v9 import OursV9, V9Config
        examples = lambda q: {'items': [{'question': 'Q?', 'external_knowledge': '', 'sql': 'SELECT 1'}]}
        return OursV9(self.db, model, examples=examples, config=V9Config(**flags)).run(
            self.gold['question'], self.gold['evidence'], self.prompts[0]['input_seq'])

    def test_plan_samples_set_vote_and_majority_skips_selector(self):
        good = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda'"
        good_distinct = "SELECT DISTINCT `County Name` FROM frpm WHERE `County Name` = 'Alameda'"
        other = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alpine' LIMIT 1"
        # set-based vote merges the DISTINCT and non-DISTINCT variants: 3 of 4 -> no selector
        model = TextModel(fence(good), [fence(good_distinct), fence(other)], select='Answer: 2')
        output = self.run_v9(model, base_samples=1, plan_samples=1)
        self.assertEqual(output['reason'], 'vote_3_of_3')
        stages = [s for s, _ in model.prompts]
        self.assertEqual(stages.count('generate_samples') + stages.count('generate_plan_samples'), 2)
        plan = [p for s, p in model.prompts if s == 'generate_plan_samples'][0]
        self.assertIn('Write the query by following this plan', plan)
        self.assertNotIn('Take a deep breath', plan)
        self.assertNotIn('select', stages)
        self.assertTrue(all(self.gold['SQL'] not in p for _, p in model.prompts))

    def test_no_majority_calls_sampled_selector(self):
        a = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"
        b = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alpine' LIMIT 1"
        c = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Amador' LIMIT 1"
        model = TextModel(fence(a), [fence(b), fence(c)], select='... Answer: 2')
        output = self.run_v9(model, base_samples=2, plan_samples=0, select_samples=3)
        self.assertEqual(output['sql'], b)
        self.assertEqual(output['reason'], 'vote_1_of_3_selected_3')
