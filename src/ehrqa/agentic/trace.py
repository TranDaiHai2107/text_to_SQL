"""Local JSONL stage traces; no API keys or provider private reasoning content."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import uuid


def safe(value):
    if isinstance(value, dict):
        return {k:safe(v) for k,v in value.items()
                if not any(s in k.lower() for s in ('api_key','authorization','reasoning_content'))}
    if isinstance(value,(list,tuple)): return [safe(v) for v in value]
    if isinstance(value,str): return re.sub(r'\bsk-[A-Za-z0-9_-]{12,}', '[REDACTED]', value)
    return value


class Trace:
    def __init__(self, directory=None, *, query_id=None):
        self.id=uuid.uuid4().hex
        self.query_id=query_id
        self.events=[]
        self.path=Path(directory)/(self.id+'.jsonl') if directory else None
        self.started=time.monotonic()

    def emit(self, stage, **data):
        row=safe({'run_id':self.id,'query_id':self.query_id,'utc':datetime.now(timezone.utc).isoformat(),
                  'elapsed_s':round(time.monotonic()-self.started,4),'stage':stage,**data})
        # JSON roundtrip yields the same safe, serializable in-memory/file trace.
        row=json.loads(json.dumps(row,ensure_ascii=False,default=str,allow_nan=False))
        self.events.append(row)
        if self.path:
            self.path.parent.mkdir(parents=True,exist_ok=True)
            with self.path.open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
        return row


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()
