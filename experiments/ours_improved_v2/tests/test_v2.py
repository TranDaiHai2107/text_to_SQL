import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hybrid_retrieval import BM25,HybridRAG,enriched_catalog
from grounded_pipeline import static_issues,parse_review,confidence,apply_threshold,build_messages,run_question
from calibration import calibration_plan,choose_threshold
from run import freeze
from common import RunBlocked


def response(text,key='a',prob=-.02):
    return {'content':text,'finish_reason':'stop','request_hash':key,
            'logprobs':[{'token':'clinical_name','logprob':prob}]}


class V2Tests(unittest.TestCase):
    def test_lexical_ranking_ignores_patient_identifier(self):
        bm=BM25(['height of patient 10000001','blood ebv test patient 10000002','weight patient 10000003'])
        self.assertEqual(bm.search('blood ebv patient 10000001',1),[1])

    def test_catalog_contains_real_microbiology_and_linksto(self):
        records,known=enriched_catalog()
        self.assertIn('blood (ebv)',known[('microbiologyevents','spec_type_desc')])
        self.assertTrue(any(r.get('linksto')=='chartevents' for r in records.values()))
        self.assertFalse(any('unit' in r for r in records.values()))

    def test_static_guard_for_unrequested_limit_and_patient(self):
        issues=static_issues('List prescribed drugs for patient 10000001',
            'SELECT drug FROM prescriptions WHERE subject_id=10000002 LIMIT 1',{})
        self.assertEqual(len(issues),2)
        self.assertFalse(static_issues('What is the last drug for patient 10000001?',
            'SELECT drug FROM prescriptions WHERE subject_id=10000001 ORDER BY starttime DESC LIMIT 1',{}))

    def test_catalog_exact_value_guard_resolves_aliases(self):
        known={('d_items','label'):{'height (cm)'}}
        self.assertTrue(static_issues('height',"SELECT x.itemid FROM d_items x WHERE x.label='invented height'",known))
        self.assertFalse(static_issues('height',"SELECT x.itemid FROM d_items x WHERE x.label='height (cm)'",known))

    def test_self_and_duplicate_exclusion_applies_to_all_example_pools(self):
        rag=HybridRAG.__new__(HybridRAG)
        rag.lock=threading.Lock()
        rag.examples=[{'id':'self','question':'Height?','sql':'SECRET','source':'dev'},
                      {'id':'duplicate','question':'height','sql':'SECRET2','source':'train'},
                      {'id':'other','question':'height last visit','sql':'null','source':'train'}]
        rag.by_id={r['id']:r for r in rag.examples}
        rag.lexical=BM25([r['question'] for r in rag.examples])
        rag.catalog={}; rag.medical=[]; rag.medical_lexical=BM25([]); rag.schema={'patients':'DDL'}
        collection=SimpleNamespace(query=lambda **kw:{'ids':[['self','duplicate','other']]})
        rag.base=SimpleNamespace(retrieve=lambda *a:{'medical':[]},collections={'examples':collection},
                                 examples_collection='examples',query_cache={'Height?':[[1]]})
        ctx=rag.retrieve('Height?',exclude_id='self')
        self.assertEqual(ctx['self_exclusion_count'],2)
        self.assertEqual([r['id'] for r in ctx['examples']],['other'])
        self.assertEqual([r['id'] for r in ctx['null_neighbors']],['other'])

    def test_review_requires_boolean_fields_and_complete_response(self):
        self.assertTrue(parse_review(response('{"answerable":"true","sql_matches_question":true,"issues":[]}'))['review_error'])
        self.assertTrue(parse_review({**response('null'),'finish_reason':'length'})['review_error'])
        self.assertTrue(parse_review(response('{"answerable":true,"sql_matches_question":true,"issues":[]}'))['answerable'])

    def test_confidence_uses_current_sql_hash_and_real_logprob(self):
        score=confidence(response('SELECT 1','new',-.3),{'request_hash':'review','logprobs':[{'token':'true','logprob':-.1},{'token':' true','logprob':-.2}]})
        self.assertEqual(score['score'],-.3)
        self.assertEqual(score['sql_call_hash'],'new')
        self.assertIsNone(confidence({**response('x'),'logprobs':None})['score'])

    def test_semantic_repair_updates_confidence_provenance(self):
        ctx={'tables':['patients'],'medical':[],'examples':[],'null_neighbors':[]}
        rag=SimpleNamespace(retrieve=lambda *a,**kw:ctx,schema={'patients':'CREATE TABLE patients (subject_id INT)'},known_values={})
        replies=iter([response('SELECT 1','first',-.01),
            response('{"answerable":true,"sql_matches_question":false,"issues":["wrong output"]}','r1'),
            response('SELECT 2','repaired',-.7),
            response('{"answerable":true,"sql_matches_question":true,"issues":[]}','r2')])
        client=SimpleNamespace(call=lambda *a,**kw:next(replies))
        good={'valid':True,'abstained':False,'empty':False,'error':None}
        with patch('grounded_pipeline.completion_sql',side_effect=lambda r:(r['content'],good)):
            row=run_question({'id':'x','question':'How many patients?'},rag,client,threshold=-.5)
        self.assertEqual(row['variants']['v2_grounded']['sql'],'SELECT 1')
        self.assertEqual(row['variants']['v2_verified']['confidence']['sql_call_hash'],'repaired')
        self.assertEqual(row['variants']['v2_calibrated']['sql'],'null')

    def test_quota_failure_is_not_a_null_prediction(self):
        rag=SimpleNamespace(retrieve=lambda *a,**kw:{'tables':[],'medical':[],'examples':[],'null_neighbors':[]},schema={})
        def blocked(*a,**kw): raise RunBlocked('402')
        with self.assertRaises(RunBlocked):
            run_question({'id':'x','question':'q'},rag,SimpleNamespace(call=blocked))

    def test_threshold_selection_uses_tune_only(self):
        ids=['t1','t2','a1','a2']
        rows=[{'id':key,'variants':{'v2_verified':{'sql':'SELECT 1','confidence':{'score':-.01 if key in {'t1','a1'} else -1.}}}} for key in ids]
        plan={'tune':ids[:2],'audit':ids[2:]}
        predictions={key:[[1]] for key in ids}
        gold={'t1':[[1]],'t2':'null','a1':'null','a2':[[1]]}
        selected=choose_threshold(rows,predictions,gold,plan)
        self.assertEqual(selected['selected_threshold'],-1.)
        self.assertEqual(selected['tune_selected']['scores']['RS10'],100)
        self.assertLess(selected['audit_selected']['scores']['RS10'],0)
        with self.assertRaises(ValueError):
            choose_threshold(rows,predictions,{**gold,'test':'null'},plan)

    def test_calibration_plan_is_disjoint_and_complete(self):
        plan=calibration_plan()
        self.assertEqual(len(plan['tune']),200)
        self.assertEqual(len(plan['audit']),100)
        self.assertFalse(set(plan['tune'])&set(plan['audit']))

    def test_constant_logprobs_disable_gate_instead_of_claiming_all_null_improvement(self):
        ids=['t1','t2','a1','a2']
        rows=[{'id':key,'variants':{'v2_verified':{'sql':'SELECT 1','confidence':{'score':0.}}}} for key in ids]
        plan={'tune':ids[:2],'audit':ids[2:]}
        result=choose_threshold(rows,{key:[[1]] for key in ids},{'t1':[[1]],'t2':'null','a1':[[1]],'a2':'null'},plan)
        self.assertEqual(result['unconstrained_grid_optimum'],0.)
        self.assertIsNone(result['selected_threshold'])
        self.assertFalse(result['confidence_quality']['usable'])

    def test_frozen_protocol_cannot_silently_change(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1],prefix='.test-') as temp:
            path=Path(temp)/'protocol.json'
            freeze(path,{'threshold':-.5})
            freeze(path,{'threshold':-.5})
            with self.assertRaises(ValueError):
                freeze(path,{'threshold':-.1})


if __name__=='__main__':
    unittest.main()
