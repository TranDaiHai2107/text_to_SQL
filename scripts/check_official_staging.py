"""Verify native scorer CSV loading from five saved artifacts without API calls.

Raw result CSVs exist only inside a temporary restricted-ACL directory and are
deleted before this command returns. Output contains counts and hashes only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from audit_phase_c1_pilot import audit
from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.evaluator import prepare_saved_run_sample
from ehrqa.clinsql.official_scorer_source import load_verified_native_scorer
from ehrqa.clinsql.result_artifacts import ResultArtifactStore


def check(run_roots: list[Path]) -> dict:
    checked = audit(run_roots)
    benchmark = ROOT / 'external/clinsql_official'
    questions, _ = load_official_questions(benchmark)
    by_id = {question.query_id: question for question in questions}
    store = ResultArtifactStore(ROOT / 'results/restricted')
    scorer_type = load_verified_native_scorer(benchmark, ROOT / 'PAPER_SOURCE_LOCK.json')
    native = object.__new__(scorer_type)  # only _load_sample_files, never Azure
    cases = {}
    with tempfile.TemporaryDirectory(prefix='clinsql_stage_', dir=store.root) as temp:
        stage_root = Path(temp)
        if not store.verify_private_acl(store.root):
            raise PermissionError('Restricted ACL failed before scorer staging')
        for case_id, record in checked['cases'].items():
            saved = json.loads(Path(record['run_log']).read_text(encoding='utf-8'))
            artifact = next(e for e in saved['events'] if e['stage'] == 'result_artifact')
            target = prepare_saved_run_sample(
                Path(record['run_log']), stage_root, benchmark, by_id[case_id],
                result_store=store, artifact_id=artifact['artifact_id'],
                artifact_sha256=artifact['sha256'])
            loaded = native._load_sample_files(target)
            if not loaded.get('test_sql') or 'test_results' not in loaded:
                raise ValueError('Native scorer did not load staged SQL and CSV')
            if len(loaded['test_results']) != record['row_count']:
                raise ValueError('Native CSV parser changed result row count')
            csv_path = target / f"result_{case_id.rsplit('/', 1)[1]}.csv"
            cases[case_id] = {
                'native_parser_row_count': len(loaded['test_results']),
                'native_parser_column_count': len(loaded['test_results'][0])
                if loaded['test_results'] else 0,
                'staged_csv_sha256': hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                'gold_reference_files_in_stage': any(
                    (target / name).exists() for name in ('gold_sql.sql', 'gold_results.csv')),
            }
        temporary_path = str(stage_root)
    if Path(temporary_path).exists():
        raise RuntimeError('Temporary clinical CSV staging directory was not removed')
    return {'status': 'NATIVE_SCORER_STAGING_PASS_NO_API', 'case_count': len(cases),
            'temporary_stage_deleted': True, 'cases': cases,
            'official_score_status': 'NOT_RUN'}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check(args.run_root)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'results').resolve()):
        raise PermissionError('Report output must remain inside project results')
    content = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != content:
        raise FileExistsError('Existing scorer staging report differs')
    if not output.exists():
        output.write_text(content, encoding='utf-8')
    print(json.dumps({'status': result['status'], 'case_count': result['case_count'],
                      'temporary_stage_deleted': result['temporary_stage_deleted']}))


if __name__ == '__main__':
    main()
