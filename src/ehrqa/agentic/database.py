"""Query result representation shared by the MIMIC-IV PostgreSQL pipeline."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import json



@dataclass
class QueryResult:
    columns: list
    rows: list
    complete: bool=True
    column_types: tuple=()
    job_id: str | None=None

    def summary(self):
        return {'rows':len(self.rows),'columns':self.columns,'complete':self.complete,
                'fingerprint':self.fingerprint() if self.complete else None}

    def fingerprint(self):
        def cell(v):
            if v is None:return ['null',None]
            if isinstance(v,bytes):return ['bytes',v.hex()]
            if isinstance(v,(int,float,Decimal)) and not isinstance(v,bool):return ['number',str(Decimal(str(v)).normalize())]
            return [type(v).__name__,str(v)]
        rows=sorted(json.dumps([cell(v) for v in row],ensure_ascii=False) for row in self.rows)
        return hashlib.sha256(json.dumps(rows,ensure_ascii=False).encode()).hexdigest()




