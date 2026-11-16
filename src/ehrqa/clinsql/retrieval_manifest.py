"""Freeze only permitted validation-development few-shot examples."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .dataset import load_official_questions
from .experiment_state import verify_pre_freeze_manifest
from .retrieval import FewShotIndex, _normal


FROZEN_CORPUS_SHA256 = '5533495dbc6547409aaa4138c96d532f6377c5f98447e6c766a3aab51262c93a'


def _digest(payload: dict) -> str:
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def build_development_fewshot_manifest(benchmark_root: Path, master: dict) -> dict:
    verify_pre_freeze_manifest(master)
    questions, tree_hash = load_official_questions(benchmark_root)
    if tree_hash != master['validation_question_tree_sha256']:
        raise ValueError('Validation question tree differs from master manifest')
    by_id = {q.query_id: q for q in questions}
    allowed = set(master['development_case_ids']) - set(master['pilot_case_ids'])
    reference_root = Path(benchmark_root) / 'data/splits/validation'
    examples = []
    excluded_unsupported = []
    for case_id in sorted(allowed):
        question = by_id[case_id]
        sql_path = reference_root / case_id / f"sql_{case_id.rsplit('/', 1)[1]}.sql"
        source_bytes = sql_path.read_bytes()
        sql = source_bytes.decode('utf-8').strip()
        if not sql:
            raise ValueError('Empty permitted development SQL')
        if 'physionet-data.mimiciv_3_1_derived' in sql:
            excluded_unsupported.append(case_id)
            continue  # derived dataset is outside the verified 31-table scope
        # Same dataset-project binding as the CLINSQL source prompt adaptation.
        adapted = sql.replace('physionet-data.mimiciv_3_1_hosp',
                              'kltn-text-to-sql.mimiciv_3_1_hosp').replace(
                                  'physionet-data.mimiciv_3_1_icu',
                                  'kltn-text-to-sql.mimiciv_3_1_icu')
        if 'physionet-data.' in adapted:
            raise ValueError('Unadapted source project in development example')
        examples.append({'query_id': case_id, 'split': 'validation',
                         'partition': 'development', 'question': question.text,
                         'question_normalized_sha256': hashlib.sha256(
                             _normal(question.text).encode()).hexdigest(),
                         'sql': adapted,
                         'source_sql_sha256': hashlib.sha256(source_bytes).hexdigest()})
    if (len(examples) != 145 or len(excluded_unsupported) != 2 or
        set(row['query_id'] for row in examples) != allowed - set(excluded_unsupported)):
        raise ValueError('Few-shot corpus differs from pinned development scope')
    FewShotIndex(examples)  # enforce corpus constraints before saving
    payload = {'version': 1, 'kind': 'clinsql_validation_development_fewshot',
               'master_manifest_sha256': master['sha256'],
               'schema_sha256': master['schema_sha256'],
               'excluded_pilot_case_ids': sorted(master['pilot_case_ids']),
               'excluded_unsupported_derived_case_ids': sorted(excluded_unsupported),
               'example_count': len(examples), 'examples': examples,
               'project_binding': 'physionet-data -> kltn-text-to-sql for HOSP/ICU only',
               'test_and_internal_check_gold_access': 'NONE'}
    return {**payload, 'sha256': _digest(payload)}


def verify_development_fewshot_manifest(manifest: dict, master: dict) -> None:
    verify_pre_freeze_manifest(master)
    content = {key: value for key, value in manifest.items() if key != 'sha256'}
    unsupported = set(manifest.get('excluded_unsupported_derived_case_ids', []))
    expected_ids = (set(master['development_case_ids']) -
                    set(master['pilot_case_ids']) - unsupported)
    if (manifest.get('sha256') != _digest(content) or
        manifest.get('master_manifest_sha256') != master['sha256'] or
        manifest.get('schema_sha256') != master['schema_sha256'] or
        manifest.get('example_count') != 145 or len(unsupported) != 2 or
        {row['query_id'] for row in manifest.get('examples', [])} != expected_ids or
        any(row.get('split') != 'validation' or row.get('partition') != 'development'
            for row in manifest.get('examples', []))):
        raise ValueError('Few-shot manifest scope or hash differs from master')


def load_frozen_fewshot_index(path: Path, master: dict) -> FewShotIndex:
    manifest = json.loads(Path(path).read_text(encoding='utf-8'))
    verify_development_fewshot_manifest(manifest, master)
    if manifest['sha256'] != FROZEN_CORPUS_SHA256:
        raise ValueError('Development few-shot corpus differs from pinned experiment version')
    return FewShotIndex(manifest['examples'])
