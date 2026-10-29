"""Isolated v3 infrastructure; historical implementations are imported unchanged."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parents[1]
OURS=ROOT.parent/'apply_my_work_to_baseline'
V2=ROOT.parent/'ours_improved_v2'
BASELINE=WORKSPACE/'baselines/probgate_ehrsql_2024'
for folder in (OURS,V2,BASELINE):
    if str(folder) not in sys.path:
        sys.path.insert(1,str(folder))
from settings import DB
from deepseek_client import DeepSeekClient
from model_client import RunBlocked
from pipeline import SYSTEM as V2_SYSTEM,completion_sql
from hybrid_retrieval import HybridRAG
from sql_runtime import clean_sql,outcome,execute,validate
from baseline_core import score_answers,execute_readonly,post_process_sql,process_answer


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+f'.{os.getpid()}.{threading.get_ident()}.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    for attempt in range(8):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt==7:
                raise
            time.sleep(.15*(attempt+1))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def freeze(path,value):
    if Path(path).exists() and load(path)!=value:
        raise ValueError('Frozen configuration changed; use a new run name: '+str(path))
    if not Path(path).exists():
        dump(path,value)


def question_rows(split):
    if split not in {'train','dev','test'}:
        raise ValueError('Unsupported split')
    return load(BASELINE/'data/inputs'/(split+'.json'))['data']


def normalized_question(text):
    return re.sub(r'\W+',' ',text.casefold()).strip()


def run_directory(name):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}',name):
        raise ValueError('Invalid run name')
    return ROOT/'runs'/name


def api_balance():
    import httpx
    response=httpx.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']},timeout=30)
    if response.status_code!=200:
        raise RunBlocked(f'Balance check failed: HTTP {response.status_code}')
    return response.json()
