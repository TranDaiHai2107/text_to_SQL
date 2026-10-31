from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from register_dataset import validate_inputs, validate_provenance
from statistics_tools import holm, paired_clusters
from score_confirmatory import metrics
from validation_common import BASELINE, activate_methods

activate_methods()
from baseline_core import score_answers


class IntakeTests(unittest.TestCase):
    def test_renaming_old_question_does_not_make_new_holdout(self):
        old = [{'id':'old', 'question':'How many visits for patient 123?'}]
        with self.assertRaisesRegex(ValueError, 'normalized question'):
            validate_inputs([{'id':'new', 'question':'HOW MANY visits for patient 123!', 'cluster_id':'count'}], old, minimum_clusters=1)

    def test_single_entity_substitution_blocks_near_duplicate(self):
        old = [{'id':'old', 'question':'What were the last five hospital admissions of patient 123 on record?'}]
        with self.assertRaisesRegex(ValueError, 'Near-duplicate'):
            validate_inputs([{'id':'new', 'question':'What were the last five hospital admissions of patient 456 on record?', 'cluster_id':'visit'}], old, minimum_clusters=1)

    def test_gold_fields_are_removed_from_inference(self):
        row = {'id':'new', 'question':'Calculate the median cumulative expense?', 'cluster_id':'cost',
               'sql':'SECRET', 'answer':123, 'is_impossible':False}
        clean = validate_inputs([row], [], minimum_clusters=1)
        self.assertEqual(set(clean[0]), {'id', 'question', 'cluster_id'})

    def test_duplicate_within_new_dataset_rejected(self):
        rows = [{'id':str(i), 'question':'Calculate median expense?', 'cluster_id':'cost'} for i in (1,2)]
        with self.assertRaisesRegex(ValueError, 'normalized question'):
            validate_inputs(rows, [], minimum_clusters=1)

    def test_exposed_id_rejected_even_when_question_changes(self):
        with self.assertRaisesRegex(ValueError, 'question ID'):
            validate_inputs([{'id':'old', 'question':'Completely different query?', 'cluster_id':'new'}],
                            [{'id':'old', 'question':'Prior query'}], minimum_clusters=1)

    def test_missing_cluster_not_assumed_independent(self):
        with self.assertRaisesRegex(ValueError, 'cluster_id'):
            validate_inputs([{'id':'new', 'question':'Calculate median expense?'}], [], minimum_clusters=1)

    def test_question_id_cannot_escape_checkpoint_directory(self):
        with self.assertRaisesRegex(ValueError, 'safe filename'):
            validate_inputs([{'id':'../outside', 'question':'Calculate median expense?', 'cluster_id':'cost'}], [], minimum_clusters=1)

    def test_number_of_clusters_not_number_of_questions(self):
        rows = [{'id':str(i), 'question':f'Unique question {i}', 'cluster_id':'one_template'} for i in range(40)]
        with self.assertRaisesRegex(ValueError, '30 reviewed clusters'):
            validate_inputs(rows, [], minimum_clusters=30)

    def test_unreviewed_provenance_rejected(self):
        with self.assertRaises(ValueError):
            validate_provenance({'source':'synthetic', 'not_used_for_method_design':True})


class StatisticsTests(unittest.TestCase):
    def test_replicates_do_not_triple_sample_size(self):
        a = {'q1':'correct', 'q2':'correct'}
        b = {'q1':'wrong', 'q2':'abstained_answerable'}
        result = paired_clusters([a]*3, [b]*3, {'q1':'same', 'q2':'same'}, samples=100)
        self.assertEqual(result['questions'], 2)
        self.assertEqual(result['clusters'], 1)
        self.assertAlmostEqual(result['delta_RS10'], 600)
        # One cluster cannot establish significance, however many API repeats.
        self.assertEqual(result['p_two_sided'], 1)

    def test_identical_predictions_are_not_significant(self):
        a = {'q':'correct'}
        result = paired_clusters([a], [a], {'q':'c'}, samples=100)
        self.assertEqual(result['delta_RS10'], 0)
        self.assertEqual(result['CI95'], [0,0])
        self.assertEqual(result['p_two_sided'], 1)

    def test_missing_question_rejected(self):
        with self.assertRaises(ValueError):
            paired_clusters([{'q':'correct'}], [{}], {'q':'c'}, samples=100)

    def test_holm_known_values(self):
        actual = holm({'a':.01, 'b':.03, 'c':.04})
        self.assertEqual(actual, {'a':.03, 'b':.06, 'c':.06})


class ScorerTests(unittest.TestCase):
    def test_execution_failure_is_wrong_not_correct_abstention(self):
        def fail(sql):
            raise ValueError('SQL invalid')
        result = metrics({'answerable':[[1]], 'impossible':'null'},
                         {'answerable':'bad SQL', 'impossible':'bad SQL'}, fail, score_answers)
        self.assertEqual(result['wrong'], 2)
        self.assertEqual(result['scores']['RS10'], -1000)
        self.assertEqual(result['VSR'], 0)

    def test_all_abstain_cannot_pass_as_execution_accuracy(self):
        result = metrics({'a':[[1]], 'u':'null'}, {'a':'null', 'u':'null'},
                         lambda sql:self.fail('No SQL should execute'), score_answers)
        self.assertEqual(result['EX'], 0)
        self.assertEqual(result['coverage'], 0)
        self.assertIsNone(result['answer_precision'])

    def test_missing_prediction_not_padded(self):
        with self.assertRaises(ValueError):
            metrics({'a':[[1]], 'u':'null'}, {'a':'SELECT 1'}, lambda sql:[], score_answers)


class MethodEnvelopeTests(unittest.TestCase):
    def test_vanna_native_reference_and_matched_route_caps(self):
        from methods import vanna_candidates
        class FakeVanna:
            config = {}
            def get_similar_question_sql(self, question): return []
            def get_related_ddl(self, question): return []
            def get_related_documentation(self, question): return []
            def get_sql_prompt(self, **kw): return [{'role':'system','content':'native Vanna prompt'}, {'role':'user','content':kw['question']}]
            def extract_sql(self, text): return text
        calls = []
        class Client:
            def __init__(self, thinking): self.thinking=thinking
            def call(self, messages, stage, question_id, max_tokens):
                calls.append((self.thinking, max_tokens, stage, messages))
                return {'content':'SELECT 1', 'finish_reason':'stop', 'request_hash':stage, 'thinking':self.thinking}
        result = vanna_candidates(FakeVanna(), {'id':'new', 'question':'Return one'},
                                  {'normal':Client(False), 'reasoning':Client(True)})
        self.assertEqual([(c[0], c[1]) for c in calls], [(False,2048),(False,2048),(True,4096)])
        self.assertEqual(calls[0][3][0]['content'], 'native Vanna prompt')
        self.assertEqual(len({c['call_hashes'][0] for c in result['candidates']}), 3)
        self.assertEqual(result['native_single']['sql'].casefold(), 'select 1')
        self.assertTrue(all(c['execution']['valid'] for c in result['candidates']))


if __name__ == '__main__':
    unittest.main()
