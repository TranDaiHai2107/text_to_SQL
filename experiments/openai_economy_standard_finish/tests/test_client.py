import json
import hashlib
import sqlite3
from pathlib import Path
import sys
import tempfile
import unittest

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openai_client import OpenAIReasoningClient, APIBlocked, BudgetGuard

TEST_TEMP = Path(__file__).resolve().parents[1]/'runs'
TEST_TEMP.mkdir(parents=True,exist_ok=True)


def body(status='completed',content='SELECT 1',reasoning=0):
    return {'id':'resp_test','model':'gpt-6-luna','status':status,'reasoning':{'effort':'none'},
            'output':[{'type':'reasoning','summary':[{'text':'SECRET_REASONING'}]},
                      {'type':'message','content':[{'type':'output_text','text':content}]}],
            'incomplete_details':{'reason':'max_output_tokens'} if status!='completed' else None,
            'usage':{'input_tokens':20,'output_tokens':20,'total_tokens':40,
                     'input_tokens_details':{'cached_tokens':5},'output_tokens_details':{'reasoning_tokens':reasoning}},
            'service_tier':'default'}


class ClientTests(unittest.TestCase):
    def test_exact_model_reasoning_and_store_false_sent(self):
        requests=[]
        def handle(request):
            requests.append(json.loads(request.content))
            return httpx.Response(200,json=body())
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            http=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(handle))
            client=OpenAIReasoningClient(directory,http_client=http,api_key='not-a-real-key')
            result=client.call([{'role':'user','content':'q'}],'test','q',max_tokens=2048)
            self.assertEqual(requests[0]['model'],'gpt-6-luna')
            self.assertEqual(requests[0]['reasoning'],{'effort':'none'})
            self.assertEqual(requests[0]['max_output_tokens'],4096)
            self.assertEqual(requests[0]['service_tier'],'default')
            self.assertFalse(requests[0]['store'])
            self.assertNotIn('temperature',requests[0])
            self.assertEqual(result['content'],'SELECT 1')
            self.assertEqual(result['usage']['completion_tokens'],20)
            self.assertEqual(result['usage']['completion_tokens_details']['reasoning_tokens'],0)
            self.assertNotIn('SECRET_REASONING',json.dumps(result))

    def test_cached_request_does_not_call_or_double_count(self):
        calls=[]
        def handle(request):
            calls.append(1)
            return httpx.Response(200,json=body())
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(handle)))
            messages=[{'role':'user','content':'q'}]
            first=client.call(messages,'a','q')
            second=client.call(messages,'b','q')
            self.assertEqual(first,second)
            self.assertEqual(len(calls),1)
            self.assertEqual(len((Path(directory)/'api_events.jsonl').read_text().splitlines()),1)

    def test_incomplete_response_not_converted_to_null(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body('incomplete','')))))
            with self.assertRaises(APIBlocked):
                client.call([{'role':'user','content':'q'}],'a','q')
            self.assertTrue(client.blocked.is_set())
            event=json.loads((Path(directory)/'api_events.jsonl').read_text())
            self.assertEqual(event['kind'],'incomplete')
            self.assertEqual(event['usage']['total_tokens'],40)

    def test_quota_failure_is_terminal_and_key_redacted(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,api_key='sk-test_secret',http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(lambda r:httpx.Response(429,json={'error':{'code':'insufficient_quota','message':'bad sk-test_secret'}}))))
            with self.assertRaises(APIBlocked) as error:
                client.call([{'role':'user','content':'q'}],'a','q')
            self.assertNotIn('sk-test_secret',str(error.exception))
            self.assertNotIn('sk-test_secret',(Path(directory)/'api_events.jsonl').read_text())

    def test_model_mismatch_not_silently_accepted(self):
        wrong=body(); wrong['model']='other-model'
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=wrong))))
            with self.assertRaisesRegex(APIBlocked,'model differs'):
                client.call([{'role':'user','content':'q'}],'a','q')

    def test_reasoning_tokens_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=body(reasoning=12)))))
            with self.assertRaisesRegex(APIBlocked,'Unexpected reasoning tokens'):
                client.call([{'role':'user','content':'q'}],'a','q')

    def test_budget_stops_before_a_paid_request(self):
        def unexpected(request):
            self.fail('Budget guard should block before calling API')
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,budget=BudgetGuard(.000001),http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(unexpected)))
            with self.assertRaisesRegex(APIBlocked,'budget guard'):
                client.call([{'role':'user','content':'q'}],'a','q')

    def test_original_flex_cache_is_reused_without_a_standard_call(self):
        def unexpected(request):
            self.fail('Already paid Flex request must not be called again')
        with tempfile.TemporaryDirectory(dir=TEST_TEMP) as directory:
            client=OpenAIReasoningClient(directory,http_client=httpx.Client(base_url='https://api.openai.com/v1',transport=httpx.MockTransport(unexpected)))
            messages=[{'role':'user','content':'cached question'}]
            params={'provider':'openai','model':'gpt-6-luna','input':messages,'reasoning':{'effort':'none'},'max_output_tokens':4096,'store':False,'service_tier':'flex'}
            key=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
            response=body(); response['service_tier']='flex'
            normalized=client.normalize_response(response,key)
            with sqlite3.connect(client.cache) as con:
                con.execute('INSERT INTO calls VALUES (?,?)',(key,json.dumps(normalized)))
                con.commit()
            con.close()
            result=client.call(messages,'a','q')
            self.assertEqual(result['service_tier'],'flex')
            self.assertFalse((Path(directory)/'api_events.jsonl').exists())


if __name__=='__main__':
    unittest.main()
