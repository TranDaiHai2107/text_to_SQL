"""OpenAI Responses transport. Final text/usage only; never log key or reasoning."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time

import httpx


class APIBlocked(RuntimeError):
    pass


class BudgetGuard:
    """Shared conservative token-cost guard; not a provider billing cap."""
    def __init__(self, maximum_usd=3.0, already_spent_upper=0.0):
        self.maximum_usd=maximum_usd
        self.spent=already_spent_upper
        self.reserved=0.0
        self.lock=threading.Lock()

    @staticmethod
    def upper_cost(input_tokens,output_tokens):
        # Flex: use the MORE expensive cache-write rate for all input, and
        # full output rate. Cached reads would make actual token cost lower.
        return (input_tokens*.0625+output_tokens*.25)/1000000

    def reserve(self,messages,cap):
        input_upper=sum(len(json.dumps(m,ensure_ascii=False).encode()) for m in messages)+512
        amount=self.upper_cost(input_upper,cap)
        with self.lock:
            if self.spent+self.reserved+amount>self.maximum_usd:
                raise APIBlocked('Conservative USD budget guard reached; retain checkpoints, no automatic top-up')
            self.reserved+=amount
        return amount

    def settle(self,reservation,usage=None):
        with self.lock:
            self.reserved-=reservation
            if usage:
                self.spent+=self.upper_cost(usage['prompt_tokens'],usage['completion_tokens'])


class OpenAIReasoningClient:
    provider = 'openai'

    def __init__(self, directory, *, model='gpt-6-luna', effort='none', max_output_tokens=4096,
                 stop_event=None, http_client=None, api_key=None, budget=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.model, self.effort = model, effort
        self.budget=budget if budget is not None else BudgetGuard()
        self.sql_tokens = self.max_output_tokens = max_output_tokens
        self._secret = api_key if api_key is not None else os.getenv('OPENAI_API_KEY','')
        if not self._secret and http_client is None:
            raise APIBlocked('OPENAI_API_KEY is not configured')
        self.http = http_client or httpx.Client(base_url='https://api.openai.com/v1',
            headers={'Authorization':'Bearer '+self._secret},
            timeout=httpx.Timeout(300, connect=30), follow_redirects=False)
        self.cache = self.directory/'model_calls.sqlite'
        with closing(sqlite3.connect(self.cache, timeout=60)) as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.execute('CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, response TEXT NOT NULL)')
            con.commit()
        self._events_lock, self._keys_lock = threading.Lock(), threading.Lock()
        self._key_locks = {}
        self.blocked = stop_event if stop_event is not None else threading.Event()
        self.blocked_reason = None

    def redact(self, message):
        message = str(message)
        if self._secret:
            message = message.replace(self._secret, '[REDACTED]')
        return re.sub(r'sk-[A-Za-z0-9_-]+', '[REDACTED]', message)[:1000]

    def event(self, value):
        value['timestamp'] = time.time()
        with self._events_lock, (self.directory/'api_events.jsonl').open('a',encoding='utf-8') as handle:
            handle.write(json.dumps(value)+'\n')

    def block(self, message):
        self.blocked_reason = self.redact(message)
        self.blocked.set()
        raise APIBlocked(self.blocked_reason)

    @staticmethod
    def normalize_response(body, key):
        usage = body.get('usage')
        if not isinstance(usage,dict) or any(type(usage.get(k)) is not int for k in ('input_tokens','output_tokens','total_tokens')):
            raise ValueError('Missing/malformed token usage')
        text = ''.join(c.get('text','') for item in body.get('output',[]) if item.get('type')=='message'
                       for c in item.get('content',[]) if c.get('type')=='output_text')
        status = body.get('status')
        return {'content':text, 'finish_reason':'stop' if status=='completed' else 'length',
                'response_status':status, 'incomplete_reason':(body.get('incomplete_details') or {}).get('reason'),
                'usage':{'prompt_tokens':usage['input_tokens'], 'completion_tokens':usage['output_tokens'],
                         'total_tokens':usage['total_tokens'],
                         'prompt_cache_hit_tokens':(usage.get('input_tokens_details') or {}).get('cached_tokens',0),
                         'completion_tokens_details':{'reasoning_tokens':(usage.get('output_tokens_details') or {}).get('reasoning_tokens')}},
                'request_hash':key, 'model':body.get('model'), 'provider':'openai',
                'response_id':body.get('id'), 'thinking':'disabled', 'logprobs':None,
                'reasoning_effort':(body.get('reasoning') or {}).get('effort'),
                'service_tier':body.get('service_tier'), 'system_fingerprint':body.get('system_fingerprint')}

    def require_completed(self, result):
        if result['response_status']!='completed' or not result['content'].strip():
            self.block('Response incomplete/empty; no null padding. reason='+str(result.get('incomplete_reason')))
        if result.get('reasoning_effort') != self.effort:
            self.block('Returned reasoning effort differs from frozen request')
        if result.get('model') != self.model:
            self.block('Returned model differs from user-selected model; no fallback')
        if result.get('service_tier')!='flex':
            self.block('Response was not billed as Flex; no automatic switch to a dearer tier')
        if (result['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens')!=0:
            self.block('Unexpected reasoning tokens in the none-effort run')
        return result

    def call(self, messages, stage, question_id, max_tokens=2048):
        # Legacy max_tokens is a V3/Vanna hint. OpenAI's shared explicit cap
        # covers BOTH invisible reasoning and the final answer for every route.
        params = {'model':self.model, 'input':messages, 'reasoning':{'effort':self.effort},
                  'max_output_tokens':self.max_output_tokens, 'store':False, 'service_tier':'flex'}
        key = hashlib.sha256(json.dumps({'provider':self.provider,**params},sort_keys=True).encode()).hexdigest()
        with self._keys_lock:
            lock = self._key_locks.setdefault(key,threading.Lock())
        with lock:
            with closing(sqlite3.connect(self.cache,timeout=60)) as con:
                cached = con.execute('SELECT response FROM calls WHERE key=?',(key,)).fetchone()
            if cached:
                return self.require_completed(json.loads(cached[0]))
            for attempt in range(6):
                if self.blocked.is_set():
                    raise APIBlocked(self.blocked_reason or 'Run stopped; checkpoints retained')
                begin = time.monotonic()
                try:
                    reservation=self.budget.reserve(messages,self.max_output_tokens)
                except APIBlocked as error:
                    self.block(str(error))
                try:
                    response = self.http.post('/responses',json=params)
                except (httpx.TimeoutException,httpx.TransportError) as error:
                    self.event({'kind':'network_error','stage':stage,'question_id':question_id,
                                'error_type':type(error).__name__,'request_hash':key})
                    self.block('Network outcome unknown; retained checkpoints, no automatic duplicate paid request')
                if response.status_code!=200:
                    self.budget.settle(reservation)
                    try:
                        error = response.json().get('error',{})
                    except (ValueError,AttributeError):
                        error = {}
                    code, kind = error.get('code'), error.get('type')
                    message = self.redact(error.get('message','API error'))
                    self.event({'kind':'api_error','stage':stage,'question_id':question_id,
                                'http_status':response.status_code,'code':code,'type':kind,'message':message})
                    if response.status_code==429 and code!='insufficient_quota' and attempt<5:
                        try:
                            delay = float(response.headers.get('retry-after',min(2**(attempt+1),32)))
                        except ValueError:
                            delay = min(2**(attempt+1),32)
                        if not 0<=delay<=60:
                            self.block('Retry delay exceeds bounded wait; checkpoint retained')
                        self.blocked.wait(max(1,delay))
                        continue
                    self.block(f'OpenAI HTTP {response.status_code}; code={code}; '+message)
                try:
                    result = self.normalize_response(response.json(),key)
                except (ValueError,KeyError,TypeError):
                    self.block('Malformed OpenAI response; no scored abstention')
                self.budget.settle(reservation,result['usage'])
                with closing(sqlite3.connect(self.cache,timeout=60)) as con:
                    con.execute('INSERT OR IGNORE INTO calls VALUES (?,?)',(key,json.dumps(result)))
                    con.commit()
                self.event({'kind':'success' if result['response_status']=='completed' else 'incomplete',
                            'stage':stage,'question_id':question_id,'request_hash':key,
                            'model':result['model'],'reasoning_effort':result['reasoning_effort'],
                            'usage':result['usage'],'service_tier':result['service_tier'],
                            'request_id':response.headers.get('x-request-id'),
                            'response_id':result['response_id'],'wall_seconds':time.monotonic()-begin,
                            'rate_limit_requests':response.headers.get('x-ratelimit-limit-requests'),
                            'rate_limit_tokens':response.headers.get('x-ratelimit-limit-tokens')})
                return self.require_completed(result)
            self.block('Retry budget exhausted')
