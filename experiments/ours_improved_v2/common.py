"""Shared infrastructure only; preserve the original benchmark implementation."""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parent
OURS=ROOT.parent/'apply_my_work_to_baseline'
WORKSPACE=ROOT.parents[1]
BASELINE=WORKSPACE/'baselines/probgate_ehrsql_2024'
OLD_RUN='deepseek_flash_train_dev_20261028_v1'
sys.path.insert(1,str(OURS))
from settings import DB
from deepseek_client import DeepSeekClient
from model_client import RunBlocked
from baseline_core import score_answers,execute_readonly,post_process_sql,bottom_logprob


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def dump(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    temp.replace(path)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_directory(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}',name):
        raise ValueError('Invalid run name')
    return ROOT/'runs'/name


def question_rows(split):
    if split not in {'train','dev','test'}:
        raise ValueError('Unknown split')
    return load(BASELINE/'data/inputs'/(split+'.json'))['data']


def normalized_question(text):
    return re.sub(r'\W+',' ',text.casefold()).strip()
