from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from deepseek_client import DeepSeekClient
from model_client import RunBlocked
from retrieval import signature


class DeepSeekTests(unittest.TestCase):
    def test_payload_cache_and_parallel_deduplication(self):
        seen = []
        def reply(request):
            seen.append(json.loads(request.content))
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'SELECT 1;','reasoning_content':'not-to-be-saved'},
                'logprobs':{'content':[{'token':'SELECT','logprob':-0.1}]}}],
                'usage':{'prompt_tokens':10,'completion_tokens':4,'total_tokens':14},'model':'deepseek-flash'})
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT) as tmp:
            http = httpx.Client(transport=httpx.MockTransport(reply),base_url='https://api.deepseek.com')
            client = DeepSeekClient(tmp,http_client=http)
            messages=[{'role':'user','content':'SQL please'}]
            with ThreadPoolExecutor(max_workers=4) as executor:
                results=list(executor.map(lambda i:client.call(messages,'sql',str(i)),range(8)))
            self.assertEqual(len(seen),1)
            self.assertEqual(seen[0]['thinking'],{'type':'disabled'})
            self.assertEqual(seen[0]['max_tokens'],2048)
            self.assertNotIn('seed',seen[0])
            self.assertNotIn('reasoning_format',seen[0])
            self.assertNotIn('max_completion_tokens',seen[0])
            self.assertTrue(all(r['content']=='SELECT 1;' for r in results))
            self.assertNotIn('reasoning_content',results[0])
            self.assertEqual(len((Path(tmp)/'api_events.jsonl').read_text().splitlines()),1)

    def test_balance_failure_stops_without_fabricating_null_and_redacts_key(self):
        calls=[]
        def reply(request):
            calls.append(1)
            return httpx.Response(402,json={'error':{'message':'invalid dummy-secret'}})
        with tempfile.TemporaryDirectory(prefix='.test-',dir=ROOT) as tmp, patch.dict('os.environ',{'DEEPSEEK_API_KEY':'dummy-secret'}):
            http=httpx.Client(transport=httpx.MockTransport(reply),base_url='https://api.deepseek.com')
            client=DeepSeekClient(tmp,http_client=http)
            with self.assertRaisesRegex(RunBlocked,'402'):
                client.call([{'role':'user','content':'Q'}],'sql','a')
            with self.assertRaises(RunBlocked):
                client.call([{'role':'user','content':'Other'}],'sql','b')
            self.assertEqual(len(calls),1)
            self.assertNotIn('dummy-secret',(Path(tmp)/'api_events.jsonl').read_text())

    def test_test_labels_cannot_enter_signature(self):
        with self.assertRaises(ValueError):
            signature(('train','test'))


if __name__=='__main__':
    unittest.main()
