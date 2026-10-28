"""Reuse only accounting, SQL execution and scoring, never the proposed RAG."""
import importlib
from pathlib import Path
import sys
from benchmark import OUR_SYSTEM


def shared(name):
    if name not in {'model_client', 'sql_runtime', 'evaluate'}:
        raise ValueError('Unsupported shared infrastructure module')
    if str(OUR_SYSTEM) not in sys.path:
        sys.path.insert(0, str(OUR_SYSTEM))
    module = importlib.import_module(name)
    if Path(module.__file__).resolve() != (OUR_SYSTEM/(name+'.py')).resolve():
        raise RuntimeError('Module collision: run this benchmark in a separate Python process')
    return module
