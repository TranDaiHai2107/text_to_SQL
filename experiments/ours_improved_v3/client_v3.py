"""Audited transport variant with explicit thinking settings in the cache key.

No credentials, reasoning content, or patient results are logged.
"""
from contextlib import closing
import hashlib
import json
import sqlite3
import time
import httpx
from infrastructure import DeepSeekClient,RunBlocked


class V3Client(DeepSeekClient):
    def __init__(self,*args,thinking=False,**kwargs):
        super().__init__(*args,logprobs=False,**kwargs)
        self.thinking=thinking

    def call(self,messages,stage,question_id,max_tokens=2048):
        params={'model':self.model,'messages':messages,'temperature':0,'max_tokens':max_tokens,
                'thinking':{'type':'enabled' if self.thinking else 'disabled'},'stream':False,'logprobs':False}
        key=hashlib.sha256(json.dumps({'provider':self.provider,**params},sort_keys=True).encode()).hexdigest()
        with self._keys_lock:
            lock=self._key_locks.setdefault(key,__import__('threading').Lock())
        with lock:
            with closing(sqlite3.connect(self.cache,timeout=30)) as con:
                cached=con.execute('SELECT response FROM calls WHERE key=?',(key,)).fetchone()
            if cached:
                return json.loads(cached[0])
            for attempt in range(4):
                if self.blocked.is_set():
                    raise RunBlocked(self.blocked_reason or 'Account blocked; checkpoints retained')
                try:
                    response=self.http.post('/chat/completions',json=params)
                except (httpx.TimeoutException,httpx.TransportError) as error:
                    self._event({'kind':'network_error','stage':stage,'question_id':question_id,'attempt':attempt+1,'error_type':type(error).__name__})
                    if attempt==3:
                        self._block('DeepSeek network retry budget exhausted; checkpoints retained')
                    time.sleep(min(2**attempt,8))
                    continue
                if response.status_code!=200:
                    try:
                        body=response.json().get('error',{})
                        message=str(body.get('message',body))[:1000]
                    except (ValueError,AttributeError):
                        message='Non-JSON API error'
                    if self._secret:
                        message=message.replace(self._secret,'[REDACTED]')
                    self._event({'kind':'api_error','stage':stage,'question_id':question_id,'status':response.status_code,'message':message})
                    if response.status_code in {401,402,403}:
                        self._block(f'DeepSeek API stopped HTTP {response.status_code}; checkpoints retained. '+message)
                    if (response.status_code==429 or response.status_code>=500) and attempt<3:
                        try:
                            delay=float(response.headers.get('retry-after',2**(attempt+1)))
                        except ValueError:
                            delay=2**(attempt+1)
                        if delay>60:
                            self._block('Provider retry exceeds bounded wait; checkpoint retained')
                        time.sleep(max(1,delay))
                        continue
                    self._block(f'DeepSeek API error {response.status_code}: '+message)
                try:
                    data=response.json()
                    choice=data['choices'][0]
                    result={'content':choice['message'].get('content') or '', 'finish_reason':choice['finish_reason'],
                            'usage':data['usage'],'request_hash':key,'model':data.get('model',self.model),
                            'provider':self.provider,'system_fingerprint':data.get('system_fingerprint'),
                            'thinking':'enabled' if self.thinking else 'disabled','logprobs':None}
                except (ValueError,KeyError,IndexError,TypeError):
                    self._block('Malformed DeepSeek response; not converted to abstention')
                with closing(sqlite3.connect(self.cache,timeout=30)) as con:
                    con.execute('INSERT OR IGNORE INTO calls VALUES (?,?)',(key,json.dumps(result)))
                    con.commit()
                self._event({'kind':'success','stage':stage,'question_id':question_id,'usage':result['usage'],
                             'request_hash':key,'model':result['model'],'system_fingerprint':result['system_fingerprint'],
                             'thinking':result['thinking'],'logprobs_available':False})
                return result
            self._block('DeepSeek retry budget exhausted')
