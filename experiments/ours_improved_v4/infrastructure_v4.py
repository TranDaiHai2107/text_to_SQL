"""V4 reuses frozen v3 generation; only validation/selection changes."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parent
V3=ROOT.parent/'ours_improved_v3'
sys.path.insert(1,str(V3))
from infrastructure import BASELINE,DB,WORKSPACE,load,dump,sha,freeze,question_rows,api_balance,RunBlocked,score_answers
from client_v3 import V3Client
from retrieval_v3 import StructuredRAG
from pipeline_v3 import run_question as generate_question
from semantics_v3 import RULE_EVIDENCE


def run_directory(name):
    import re
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}',name):
        raise ValueError('Invalid run name')
    return ROOT/'runs'/name
