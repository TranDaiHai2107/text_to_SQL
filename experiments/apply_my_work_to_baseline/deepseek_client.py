"""DeepSeek REST transport with cache, accounting and safe concurrent calls."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import httpx
from model_client import RunBlocked


class DeepSeekClient:
    provider = 'deepseek'
    def __init__(self, run_dir, model='deepseek-flash', sql_tokens=2048, rewrite_tokens=256,
                 logprobs=True, http_client=None):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.model, self.sql_tokens, self.rewrite_tokens = model, sql_tokens, rewrite_tokens
        self.logprobs = logprobs
        self.headers = {}
        self._secret = os.getenv('DEEPSEEK_API_KEY', '')
        if not self._secret and http_client is None:
            raise RunBlocked('DEEPSEEK_API_KEY is not configured')
        self.http = http_client or httpx.Client(
            base_url='https://api.deepseek.com',
            headers={'Authorization':'Bearer '+self._secret},
            timeout=httpx.Timeout(180, connect=30), follow_redirects=False)
        self.cache = self.run_dir/'model_calls.sqlite'
        with closing(sqlite3.connect(self.cache, timeout=30)) as con:
            con.execute('CREATE TABLE IF NOT EXISTS calls (key TEXT PRIMARY KEY, response TEXT NOT NULL)')
            con.commit()
        self._event_lock = threading.Lock()
        self._keys_lock = threading.Lock()
        self._key_locks = {}
        self.blocked = threading.Event()
        self.blocked_reason = None

    def _event(self, value):
        value['timestamp'] = time.time()
        with self._event_lock, (self.run_dir/'api_events.jsonl').open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(value)+'\n')

    def _block(self, message):
        if self._secret:
            message = message.replace(self._secret, '[REDACTED]')
        self.blocked_reason = message
        self.blocked.set()
        raise RunBlocked(message)

    def call(self, messages, stage, question_id, max_tokens=2048):
        params = {'model':self.model, 'messages':messages, 'temperature':0,
                  'max_tokens':max_tokens, 'thinking':{'type':'disabled'},
                  'stream':False, 'logprobs':self.logprobs}
        # No Groq-specific reasoning_format/seed/max_completion_tokens.
        key = hashlib.sha256(json.dumps({'provider':self.provider, **params}, sort_keys=True).encode()).hexdigest()
        with self._keys_lock:
            lock = self._key_locks.setdefault(key, threading.Lock())
        with lock:
            with closing(sqlite3.connect(self.cache, timeout=30)) as con:
                cached = con.execute('SELECT response FROM calls WHERE key=?', (key,)).fetchone()
            if cached:
                return json.loads(cached[0])
            if self.blocked.is_set():
                raise RunBlocked(self.blocked_reason or 'DeepSeek account is blocked')
            for attempt in range(4):
                if self.blocked.is_set():
                    raise RunBlocked(self.blocked_reason or 'DeepSeek account is blocked')
                try:
                    response = self.http.post('/chat/completions', json=params)
                except (httpx.TimeoutException, httpx.TransportError) as error:
                    self._event({'kind':'network_error','stage':stage,'question_id':question_id,
                                 'attempt':attempt+1,'error_type':type(error).__name__})
                    if attempt == 3:
                        self._block('DeepSeek network/timeout retry budget exhausted; checkpoints retained')
                    time.sleep(min(2**attempt, 8))
                    continue
                if response.status_code != 200:
                    try:
                        body = response.json().get('error', {})
                        message = str(body.get('message', body))[:1000]
                    except (ValueError, AttributeError):
                        message = 'Non-JSON API error'
                    if self._secret:
                        message = message.replace(self._secret, '[REDACTED]')
                    self._event({'kind':'api_error', 'stage':stage, 'question_id':question_id,
                                 'status':response.status_code, 'message':message})
                    if response.status_code == 402:
                        self._block('DeepSeek balance exhausted (HTTP 402); checkpoints retained. '+message)
                    if response.status_code in {401,403}:
                        self._block('DeepSeek authentication/authorization failed; checkpoints retained')
                    if (response.status_code == 429 or response.status_code >= 500) and attempt < 3:
                        try:
                            delay = float(response.headers.get('retry-after', 2**(attempt+1)))
                        except ValueError:
                            delay = 2**(attempt+1)
                        if delay > 60:
                            self._block('DeepSeek retry-after exceeds retry budget; checkpoints retained')
                        time.sleep(max(1, delay))
                        continue
                    self._block(f'DeepSeek API error {response.status_code}: '+message)
                try:
                    data = response.json()
                    choice = data['choices'][0]
                    result = {'content':choice['message'].get('content') or '',
                              'finish_reason':choice['finish_reason'], 'usage':data['usage'],
                              'request_hash':key, 'model':data.get('model', self.model),
                              'provider':self.provider, 'system_fingerprint':data.get('system_fingerprint'),
                              'logprobs':(choice.get('logprobs') or {}).get('content'),
                              'rate_limit_headers':{k:v for k,v in response.headers.items() if k.startswith('x-ratelimit')}}
                except (KeyError, IndexError, ValueError, TypeError):
                    self._block('Malformed DeepSeek response; not converted to a SQL abstention')
                # Do not persist reasoning_content. It is not a SQL prediction.
                with closing(sqlite3.connect(self.cache, timeout=30)) as con:
                    con.execute('INSERT OR IGNORE INTO calls VALUES (?,?)', (key, json.dumps(result)))
                    con.commit()
                self._event({'kind':'success', 'stage':stage, 'question_id':question_id,
                             'usage':result['usage'], 'request_hash':key, 'model':result['model'],
                             'system_fingerprint':result['system_fingerprint'],
                             'logprobs_available':result['logprobs'] is not None})
                return result
            self._block('DeepSeek retry budget exhausted')
