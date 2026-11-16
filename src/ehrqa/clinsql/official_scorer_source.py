"""Load the locked CLINSQL scorer source without changing its grading logic.

Importing the module does not instantiate AzureOpenAI or send a judge request.
The real scorer factory remains an explicit, separately approved evaluation
dependency in ``OfficialClinSQLEvaluator``.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys


SCORER_RELATIVE_PATH = 'evaluation/clinical_rubric_scorer.py'


def load_verified_native_scorer(source_root: Path, lock_path: Path):
    source_root, lock_path = Path(source_root), Path(lock_path)
    lock = json.loads(lock_path.read_text(encoding='utf-8'))['clinsql']
    expected = lock['key_files'][SCORER_RELATIVE_PATH]
    path = source_root / SCORER_RELATIVE_PATH
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError('Official CLINSQL scorer source differs from source lock')
    module_name = '_ehrqa_locked_clinsql_official_scorer'
    module = sys.modules.get(module_name)
    if module is None or Path(module.__file__).resolve() != path.resolve():
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError('Cannot load locked official CLINSQL scorer')
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            sys.modules.pop(module_name, None)
            raise
    if module.SUPPORTED_MODELS != {'gpt-5-chat': {'client': 'azure', 'model_name': 'gpt-5-chat'}}:
        raise ValueError('Official judge model configuration differs from reviewed source')
    return module.ClinicalRubricScorer


def count_judge_leaf_calls(benchmark_root: Path, case_ids: list[str]) -> dict:
    """Count native leaf evaluations without loading clinical rows or prompts."""
    root = Path(benchmark_root) / 'data/splits/validation'

    def leaves(node: dict) -> int:
        children = node.get('sub_tasks', [])
        return sum(leaves(child) for child in children) if children else 1

    cases = {}
    for case_id in case_ids:
        path = (root / case_id).resolve()
        if not path.is_relative_to(root.resolve()) or len(Path(case_id).parts) != 3:
            raise ValueError('Case ID outside validation scope')
        sql = json.loads((path / 'sql_rubric_tree.json').read_text(encoding='utf-8'))
        results = json.loads((path / 'results_rubric_tree.json').read_text(encoding='utf-8'))
        cases[case_id] = {'sql_leaf_calls': leaves(sql),
                          'results_leaf_calls': leaves(results)}
    return {'cases': cases,
            'sql_leaf_calls': sum(row['sql_leaf_calls'] for row in cases.values()),
            'results_leaf_calls': sum(row['results_leaf_calls'] for row in cases.values())}
