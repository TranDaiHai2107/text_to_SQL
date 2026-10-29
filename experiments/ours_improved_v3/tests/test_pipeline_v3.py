from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from infrastructure import ROOT,load,dump,question_rows,V2,RunBlocked
from client_v3 import V3Client
from pipeline_v3 import fingerprint_rows,messages_for,completion,guarded
from semantics_v3 import BENCHMARK_CONVENTIONS,RULE_EVIDENCE
from run_v3 import calibration_plan


class PipelineTests(unittest.TestCase):
    def test_atomic_write_retries_transient_windows_lock(self):
        original=Path.replace
        calls=[]
        def transient(source,target):
            calls.append(target)
            if len(calls)<3:
                raise PermissionError('transient file lock')
            return original(source,target)
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-') as temp:
            target=Path(temp)/'metadata.json'
            with patch.object(Path,'replace',transient),patch('infrastructure.time.sleep'):
                dump(target,{'complete':True})
            self.assertEqual(load(target),{'complete':True})
            self.assertEqual(len(calls),3)

    def test_fingerprint_uses_all_rows_columns_null_and_duplicates(self):
        rows=[(i,) for i in range(120)]
        a,_=fingerprint_rows(rows)
        b,_=fingerprint_rows(rows[:100]+[(999,)]*20)
        self.assertNotEqual(a,b)
        self.assertNotEqual(fingerprint_rows([(1,)])[0],fingerprint_rows([(1,1)])[0])
        self.assertNotEqual(fingerprint_rows([(None,)])[0],fingerprint_rows([('None',)])[0])
        self.assertNotEqual(fingerprint_rows([(1,)])[0],fingerprint_rows([(1,),(1,)])[0])
        self.assertEqual(a,fingerprint_rows(list(reversed(rows)))[0])
        self.assertIsNone(fingerprint_rows([])[0])

    def test_every_route_has_shared_benchmark_contract(self):
        ctx={'tables':[],'medical':[],'examples':[],'null_neighbors':[]}
        for route in ['direct','structural','plan']:
            messages=messages_for('Original question',ctx,{},route)
            self.assertIn(BENCHMARK_CONVENTIONS,messages[0]['content'])
            self.assertEqual(messages[-1]['content'],'Original question')
            self.assertFalse(any(x['role']=='assistant' for x in messages))

    def test_incomplete_generation_remains_failure_until_explicit_guard(self):
        record=completion({'finish_reason':'length','content':'null'},'q',{})
        self.assertEqual(record['sql'],'')
        self.assertFalse(record['execution']['abstained'])
        result=guarded(record)
        self.assertEqual(result['sql'],'null')
        self.assertTrue(result['guard_rejected'])
        self.assertEqual(result['pre_guard_execution']['error'],'generation_incomplete:length')

    def test_thinking_configuration_is_in_actual_body_and_cache_key(self):
        bodies=[]
        def handler(request):
            import json
            body=json.loads(request.content)
            bodies.append(body)
            return httpx.Response(200,json={'choices':[{'message':{'content':'SELECT 1','reasoning_content':'PRIVATE_REASONING'},'finish_reason':'stop'}],
                                           'usage':{'prompt_tokens':4,'completion_tokens':2,'total_tokens':6},'model':'deepseek-flash'})
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-') as tmp:
            http=httpx.Client(base_url='https://api.deepseek.com',transport=httpx.MockTransport(handler))
            a=V3Client(Path(tmp),thinking=False,http_client=http)
            b=V3Client(Path(tmp),thinking=True,http_client=http)
            normal=a.call([{'role':'user','content':'x'}],'test','id')
            reasoning=b.call([{'role':'user','content':'x'}],'test','id',max_tokens=4096)
            again=b.call([{'role':'user','content':'x'}],'test','id',max_tokens=4096)
            self.assertNotEqual(normal['request_hash'],reasoning['request_hash'])
            self.assertEqual(again,reasoning)
            self.assertEqual(len(bodies),2)
            self.assertEqual(bodies[1]['thinking'],{'type':'enabled'})
            self.assertFalse(bodies[0]['logprobs'])
            self.assertNotIn('reasoning_content',reasoning)
            self.assertNotIn('PRIVATE_REASONING',(Path(tmp)/'model_calls.sqlite').read_bytes().decode(errors='ignore'))
            http.close()

    def test_provider_balance_failure_never_becomes_prediction(self):
        http=httpx.Client(base_url='https://api.deepseek.com',transport=httpx.MockTransport(lambda request:httpx.Response(402,json={'error':{'message':'No balance'}})))
        with tempfile.TemporaryDirectory(dir=ROOT,prefix='.test-') as tmp:
            client=V3Client(tmp,http_client=http)
            with self.assertRaises(RunBlocked):
                client.call([{'role':'user','content':'x'}],'test','id')
            self.assertTrue(client.blocked.is_set())
        http.close()

    def test_new_tune_audit_are_disjoint_from_old_and_rule_examples(self):
        plan=calibration_plan()
        old=load(V2/'runs/deepseek_flash_v2b_20261028/threshold.json')['plan']
        current=set(plan['tune']+plan['audit'])
        evidence={r['id'] for refs in RULE_EVIDENCE.values() for r in refs if r['split']=='dev'}
        self.assertEqual(len(plan['tune']),300)
        self.assertEqual(len(plan['audit']),100)
        self.assertEqual(len(current),400)
        self.assertFalse(current&set(old['tune']+old['audit']))
        self.assertFalse(current&evidence)
        self.assertTrue(current<={r['id'] for r in question_rows('dev')})


if __name__=='__main__':
    unittest.main()
