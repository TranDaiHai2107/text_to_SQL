import json
from pathlib import Path
import sys
import tempfile
import unittest

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from openai_client import OpenAIReasoningClient, APIBlocked

TEST_TEMP = Path(__file__).resolve().parents[1]/'runs'
TEST_TEMP.mkdir(parents=True,exist_ok=True)


def body(status='completed',content='SELECT 1',reasoning=12):
    return {'id':'resp_test','model':'gpt-6.1-terra','status':status,'reasoning':{'effort':'high'},
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
            self.assertEqual(requests[0]['model'],'gpt-6.1-terra')
            self.assertEqual(requests[0]['reasoning'],{'effort':'high'})
            self.assertEqual(requests[0]['max_output_tokens'],32768)
            self.assertFalse(requests[0]['store'])
            self.assertNotIn('temperature',requests[0])
            self.assertEqual(result['content'],'SELECT 1')
            self.assertEqual(result['usage']['completion_tokens'],20)
            self.assertEqual(result['usage']['completion_tokens_details']['reasoning_tokens'],12)
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


if __name__=='__main__':
    unittest.main()
