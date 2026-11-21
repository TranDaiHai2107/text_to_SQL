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
    def __init__(self, greedy, samples, repair='', select='Answer: 1', merge=''):
        self.greedy, self.samples, self.repair, self.select, self.merge = greedy, samples, repair, select, merge
        self.prompts = []

    def _select(self, prompt):
        return self.select(prompt) if callable(self.select) else self.select

    def complete_text(self, stage, messages, tokens):
        prompt = messages[0]['content']
        self.prompts.append((stage, prompt))
        text = {'generate': self.greedy, 'repair': self.repair, 'merge': self.merge}.get(stage)
        text = self._select(prompt) if text is None else text
        return {'content': text, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1}, 'usd': 0}

    def sample_text(self, stage, messages, tokens, *, n, temperature):
        prompt = messages[0]['content']
        self.prompts.append((stage, prompt))
        if stage.startswith('select'):
            return {'contents': [self._select(prompt)] * n, 'usage': {'prompt_tokens': 1, 'completion_tokens': 1},
                    'usd': 0}
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


class OursV10Test(OursV8Test):
    COUNT_WRONG = "SELECT COUNT(*) FROM frpm WHERE `County Name` = 'alameda'"
    COUNT_GOOD = "SELECT COUNT(*) FROM frpm WHERE `County Name` = 'Alameda'"
    A = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"
    B = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alpine' LIMIT 1"
    C = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Amador' LIMIT 1"

    def run_v10(self, model, **flags):
        from ehrqa.bird.ours_v10 import OursV10, V10Config
        examples = lambda q: {'items': [{'question': 'Q?', 'external_knowledge': '', 'sql': 'SELECT 1'}]}
        output = OursV10(self.db, model, examples=examples, config=V10Config(**flags)).run(
            self.gold['question'], self.gold['evidence'], self.prompts[0]['input_seq'])
        self.assertTrue(all(self.gold['SQL'] not in p for _, p in model.prompts))
        return output

    def test_literal_mismatches(self):
        from ehrqa.bird.ours_v10 import literal_mismatches
        index = self.db.values
        found = literal_mismatches(self.COUNT_WRONG, index)
        self.assertEqual([(m['literal'], m['op']) for m in found], [('alameda', '=')])
        self.assertEqual(found[0]['similar'][0], 'Alameda')
        self.assertEqual(literal_mismatches(self.COUNT_GOOD, index), [])
        self.assertEqual(literal_mismatches("SELECT 1 FROM frpm T1 WHERE T1.`County Name` LIKE '%Alam%'", index), [])
        self.assertEqual([m['literal'] for m in literal_mismatches(
            "SELECT 1 FROM frpm WHERE `County Name` IN ('Alameda', 'Nowhere')", index)], ['Nowhere'])
        self.assertEqual(literal_mismatches("SELECT 1 FROM frpm WHERE `County Name` NOT LIKE 'zz%'", index), [])
        self.assertEqual(literal_mismatches("SELECT 1 FROM frpm WHERE `County Code` = 1", index), [])

    def test_value_mismatch_triggers_repair_of_an_aggregate(self):
        model = TextModel(fence(self.COUNT_WRONG), [], repair=fence(self.COUNT_GOOD))
        output = self.run_v10(model, base_samples=0, plan_samples=0)
        repair = [p for s, p in model.prompts if s == 'repair'][0]
        self.assertIn('is not stored in that column', repair)
        self.assertIn("'Alameda'", repair.split('Execution feedback:', 1)[1])
        self.assertEqual(output['sql'], self.COUNT_GOOD)  # the unstored-literal greedy is dropped by the filter

    def test_value_filter_drops_unstored_literal_candidates(self):
        model = TextModel(fence(self.COUNT_WRONG), [fence(self.COUNT_WRONG), fence(self.COUNT_GOOD)])
        output = self.run_v10(model, base_samples=2, plan_samples=0, repair=False)
        self.assertEqual((output['sql'], output['reason']), (self.COUNT_GOOD, 'vote_1_of_1'))
        model = TextModel(fence(self.COUNT_WRONG), [fence(self.COUNT_WRONG), fence(self.COUNT_GOOD)])
        output = self.run_v10(model, base_samples=2, plan_samples=0, repair=False, value_filter=False,
                              select=False)
        self.assertEqual(output['sql'], self.COUNT_WRONG)

    def test_pairwise_judges_both_orders_and_weights_by_share(self):
        def pick_alpine(prompt):
            second = prompt.split('Candidate 2:', 1)[1].split('Result:', 1)[0]
            return 'Answer: 2' if 'Alpine' in second else 'Answer: 1'
        model = TextModel(fence(self.A), [fence(self.B), fence(self.C)], select=pick_alpine)
        output = self.run_v10(model, base_samples=2, plan_samples=0)
        self.assertEqual(output['sql'], self.B)
        self.assertEqual(output['reason'], 'vote_1_of_3_pair_b')
        pairs = [p for s, p in model.prompts if s == 'select_pair']
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all('Amador' not in p.split('Candidate SQL queries', 1)[1] for p in pairs))  # top-2 only
        first = lambda p: p.split('Candidate 1:', 1)[1].split('Candidate 2:', 1)[0]
        self.assertEqual({'Alameda' in first(p) for p in pairs}, {True, False})  # both orders

    def test_merge_resolver(self):
        new = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Butte' LIMIT 1"
        model = TextModel(fence(self.A), [fence(self.B)], merge=fence(new))
        output = self.run_v10(model, base_samples=1, plan_samples=0, resolve='merge')
        self.assertEqual((output['sql'], output['reason']), (new, 'vote_1_of_2_merge_new'))
        merge = [p for s, p in model.prompts if s == 'merge'][0]
        self.assertIn('corrected combination', merge)
        self.assertIn('Alpine', merge)
        model = TextModel(fence(self.A), [fence(self.B)], merge=fence(self.B.replace('LIMIT 1', 'LIMIT 1;')))
        output = self.run_v10(model, base_samples=1, plan_samples=0, resolve='merge')
        self.assertEqual((output['sql'], output['reason']), (self.B, 'vote_1_of_2_merge_agrees_s1'))

    def test_divide_and_conquer_generator_and_early_stop(self):
        model = TextModel(fence(self.A), [fence(self.A)] * 4)
        self.run_v10(model, base_samples=2, plan_samples=2, dc_samples=2)
        stages = [s for s, _ in model.prompts]
        self.assertEqual(stages.count('generate_dc_samples'), 1)
        dc = [p for s, p in model.prompts if s == 'generate_dc_samples'][0]
        self.assertIn('divide and conquer', dc)
        self.assertNotIn('Take a deep breath', dc)
        model = TextModel(fence(self.A), [fence(self.A)] * 4)
        output = self.run_v10(model, base_samples=2, plan_samples=2, dc_samples=2, early_stop_share=0.9)
        stages = [s for s, _ in model.prompts]
        self.assertNotIn('generate_plan_samples', stages)
        self.assertNotIn('generate_dc_samples', stages)
        self.assertEqual((output['reason'], output['model_calls']), ('vote_3_of_3', 2))
        model = TextModel(fence(self.A), [fence(self.B), fence(self.A)])
        self.run_v10(model, base_samples=1, plan_samples=1, early_stop_share=0.9)
        self.assertIn('generate_plan_samples', [s for s, _ in model.prompts])

    def test_config_rejects_unknown_resolver(self):
        from ehrqa.bird.ours_v10 import V10Config
        with self.assertRaises(ValueError):
            V10Config(resolve='vote')


class UpdateBaselineTest(OursV8Test):
    EMPTY = "SELECT `County Name` FROM frpm WHERE `County Name` = 'nowhere'"
    A = "SELECT `County Name` FROM frpm WHERE `County Name` = 'Alameda' LIMIT 1"

    def run_rung(self, model, rung):
        from ehrqa.bird.update_baseline import UpdateBaseline
        examples = lambda q: {'items': [{'question': 'Q?', 'external_knowledge': '', 'sql': 'SELECT 1'}]}
        output = UpdateBaseline(self.db, model, rung=rung, examples=examples).run(
            self.gold['question'], self.gold['evidence'], self.prompts[0]['input_seq'])
        self.assertTrue(all(self.gold['SQL'] not in p for _, p in model.prompts))
        return output

    def test_rung0_is_the_omnisql_protocol(self):
        # 2 empty samples and 1 valued sample: the author rule lets empty results win; greedy does not vote
        model = TextModel(fence(self.A), [fence(self.EMPTY)] * 2 + [fence(self.A)] + [fence(self.EMPTY)] * 5)
        output = self.run_rung(model, 'ub0_baseline')
        self.assertEqual((output['sql'], output['reason']), (self.EMPTY, 'vote_7_of_8'))
        prompts = dict(model.prompts)
        self.assertEqual(prompts['generate_samples'], self.prompts[0]['input_seq'])  # unchanged baseline prompt
        self.assertEqual({s for s, _ in model.prompts}, {'generate', 'generate_samples'})

    def test_rung1_changes_only_the_vote(self):
        model = TextModel(fence(self.A), [fence(self.EMPTY)] * 2 + [fence(self.A)] + [fence(self.EMPTY)] * 5)
        output = self.run_rung(model, 'ub1_vote')
        self.assertEqual((output['sql'], output['reason']), (self.A, 'vote_1_of_1'))
        self.assertEqual(dict(model.prompts)['generate_samples'], self.prompts[0]['input_seq'])

    def test_ladder_is_cumulative_and_ends_at_v10(self):
        from ehrqa.bird.ours_v10 import V10Config
        from ehrqa.bird.update_baseline import NAMES, ladder_config
        self.assertEqual(ladder_config('ub2_context').values, True)
        self.assertEqual(ladder_config('ub2_context').vote_greedy, False)
        self.assertEqual(ladder_config('ub3_repair').fewshot, True)
        v9_like = ladder_config('ub5_select')
        self.assertEqual((v9_like.plan_samples, v9_like.select, v9_like.resolve, v9_like.value_check),
                         (8, True, 'listwise', False))
        self.assertEqual(ladder_config(NAMES[-1]), V10Config())
        with self.assertRaises(ValueError):
            ladder_config('ub9')
