"""Audit five saved pilot predictions without printing or exporting patient rows."""
from __future__ import annotations

import argparse
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.clinsql.pilot_cases import verify_pilot_cases
from ehrqa.clinsql.result_artifacts import ResultArtifactStore


def audit(run_roots: list[Path]) -> dict:
    pilot = verify_pilot_cases(
        ROOT / 'data/clinsql/pilot_5_validation_development_v1.json',
        ROOT / 'external/clinsql_official')
    expected = {row['case_id'] for row in pilot['cases']}
    store = ResultArtifactStore(ROOT / 'results/restricted')
    if not store.verify_private_acl(store.root):
        raise PermissionError('Restricted artifact ACL failed')
    cases = {}
    contexts = []
    excluded_calibration = []
    for run_root in run_roots:
        run_root = run_root.resolve()
        if not run_root.is_relative_to((ROOT / 'results').resolve()):
            raise PermissionError('Run root outside project results')
        for path in run_root.glob('*.json'):
            saved = json.loads(path.read_text(encoding='utf-8'))
            summary = saved['summary']
            case_id = summary['query_id']
            if case_id not in expected:
                raise ValueError('Saved case outside pinned pilot')
            if any(e.get('rows') is not None for e in saved['events']):
                raise ValueError('Raw patient rows found in application log')
            predictions = [e for e in saved['events'] if e['stage'] == 'prediction']
            if len(predictions) != 1 or predictions[0]['status'] != 'executed':
                if (len(predictions) != 1 or
                    predictions[0]['status'] != 'BUDGET_EXCEEDED' or
                    any(e['stage'] in {'execute', 'result_artifact'} for e in saved['events'])):
                    raise ValueError('Unexpected incomplete pilot prediction')
                excluded_calibration.append({
                    'run_log': str(path), 'case_id': case_id,
                    'status': predictions[0]['status'],
                })
                continue
            if case_id in cases:
                raise ValueError('Duplicate executed pilot case across run roots')
            context = [e for e in saved['events'] if e['stage'] == 'run_context']
            execution = [e for e in saved['events'] if e['stage'] == 'execute']
            artifact = [e for e in saved['events'] if e['stage'] == 'result_artifact']
            if len(context) != 1 or len(execution) != 1 or len(artifact) != 1:
                raise ValueError('Pilot case lacks one execution and one artifact')
            if not execution[0]['complete'] or execution[0]['job_id'] != artifact[0]['job_id']:
                raise ValueError('Incomplete or mismatched execution')
            result = store.load(artifact[0]['artifact_id'],
                                expected_sha256=artifact[0]['sha256'])
            if len(result.rows) != artifact[0]['row_count']:
                raise ValueError('Artifact row count mismatch')
            contexts.append(context[0])
            cases[case_id] = {
                'run_log': str(path), 'job_id': execution[0]['job_id'],
                'row_count': len(result.rows),
                'bytes_billed': execution[0]['bytes_billed'],
                'bytes_processed': execution[0]['bytes_processed'],
                'api_calls': summary['api_calls'],
                'input_tokens': summary['input_tokens'],
                'output_tokens': summary['output_tokens'],
                'reasoning_tokens': summary.get('reasoning_tokens', 0),
                'estimated_api_cost_usd': summary['estimated_inference_cost_usd'],
                'end_to_end_latency_seconds': summary['total_latency_seconds'],
                'artifact_sha256': artifact[0]['sha256'],
                'artifact_expires_at_utc': artifact[0]['artifact_expires_at_utc']}
    if set(cases) != expected:
        raise ValueError('Pilot does not have five complete predictions')
    for field in ('model_id', 'schema_sha256', 'schema_index_sha256',
                  'runtime_code_sha256', 'api_budget_sha256',
                  'reasoning_effort', 'max_output_tokens'):
        if len({context.get(field) for context in contexts}) != 1:
            raise ValueError(f'Pilot configuration drift: {field}')
    total_bytes = sum(row['bytes_billed'] for row in cases.values())
    api_cost = sum((Decimal(str(row['estimated_api_cost_usd']))
                    for row in cases.values()), Decimal(0))
    sql_cost = Decimal(total_bytes) * Decimal('6.25') / Decimal(2**40)
    return {'status': 'PILOT_5_TECHNICAL_EXECUTION_PASS',
            'pilot_manifest_sha256': pilot['sha256'],
            'case_count': len(cases), 'cases': cases,
            'aggregate': {'api_calls': sum(row['api_calls'] for row in cases.values()),
                          'input_tokens': sum(row['input_tokens'] for row in cases.values()),
                          'output_tokens': sum(row['output_tokens'] for row in cases.values()),
                          'reasoning_tokens': sum(row['reasoning_tokens'] for row in cases.values()),
                          'bytes_billed': total_bytes,
                          'estimated_api_cost_usd': str(api_cost),
                          'estimated_sql_cost_usd': str(sql_cost),
                          'end_to_end_latency_seconds': sum(
                              row['end_to_end_latency_seconds'] for row in cases.values())},
            'model_id': contexts[0]['model_id'],
            'schema_sha256': contexts[0]['schema_sha256'],
            'schema_index_sha256': contexts[0]['schema_index_sha256'],
            'runtime_code_sha256': contexts[0]['runtime_code_sha256'],
            'api_budget_sha256': contexts[0]['api_budget_sha256'],
            'sql_budget_sha256_by_case': {case_id: next(
                c['sql_budget_sha256'] for c in contexts if c['case_id'] == case_id)
                for case_id in cases},
            'excluded_calibration': excluded_calibration,
            'official_score_status': 'NOT_RUN'}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True, action='append')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    report = audit(args.run_root)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'results').resolve()):
        raise PermissionError('Audit output must stay in project results')
    content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != content:
        raise FileExistsError('Existing pilot audit differs; inspect before overwrite')
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_text(content, encoding='utf-8')
    print(json.dumps({k: report[k] for k in ('status', 'case_count', 'aggregate',
                                            'official_score_status')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
