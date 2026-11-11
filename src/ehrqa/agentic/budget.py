"""Optional run-wide conservative budget; ambiguous requests retain reservation."""
from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import threading


class Budget:
    def __init__(self,path,limit,input_rate,output_rate):
        if any(not math.isfinite(v) or v<=0 for v in (limit,input_rate,output_rate)):raise ValueError('Positive finite explicit budget/rates required')
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.limit,self.input_rate,self.output_rate=limit,input_rate,output_rate
        self.lock=threading.Lock()
        with closing(sqlite3.connect(self.path)) as c:
            c.execute('CREATE TABLE IF NOT EXISTS charges(id INTEGER PRIMARY KEY,usd REAL,status TEXT)');c.commit()

    def cost(self,input_tokens,output_tokens):return (input_tokens*self.input_rate+output_tokens*self.output_rate)/1e6

    def reserve(self,messages,max_tokens):
        reserve=self.cost(len(json.dumps(messages,ensure_ascii=False).encode())+2048,max_tokens)
        with self.lock,closing(sqlite3.connect(self.path,timeout=30)) as c:
            c.execute('BEGIN IMMEDIATE')
            spent=c.execute('SELECT COALESCE(SUM(usd),0) FROM charges').fetchone()[0]
            if spent+reserve>self.limit:raise RuntimeError('Run USD budget reached; no further API request sent')
            row=c.execute('INSERT INTO charges(usd,status) VALUES (?,?)',(reserve,'reserved_unknown')).lastrowid;c.commit()
        return row

    def finish(self,charge,usage=None,status='success'):
        with closing(sqlite3.connect(self.path,timeout=30)) as c:
            if usage and 'prompt_tokens' in usage and 'completion_tokens' in usage:
                cost=self.cost(usage['prompt_tokens'],usage['completion_tokens'])
                c.execute('UPDATE charges SET usd=?,status=? WHERE id=?',(cost,status,charge))
            elif status in {'http_400','http_401','http_402','http_403','http_404','http_429'}:
                c.execute('UPDATE charges SET usd=0,status=? WHERE id=?',(status,charge))
            c.commit()

    def summary(self):
        with closing(sqlite3.connect(self.path,timeout=30)) as c:
            return {'upper_or_reserved_USD':c.execute('SELECT COALESCE(SUM(usd),0) FROM charges').fetchone()[0],
                    'limit_USD':self.limit,'states':c.execute('SELECT status,COUNT(*) FROM charges GROUP BY status').fetchall(),
                    'pricing_input_per_million':self.input_rate,'pricing_output_per_million':self.output_rate,
                    'provider_invoice_verified':False}
