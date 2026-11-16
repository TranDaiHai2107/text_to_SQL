"""Run one exact Phase A MIMIC aggregate only with a completed approval file.

Without --execute-approved, this command is offline and does not load ADC.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from ehrqa.cli.bigquery_sql_smoke import smoke_cases
from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter
from ehrqa.clinsql.bigquery_client import BigQueryClient
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.execution_control import ExecutionApproval, PHASE_A_MAX_BYTES
from ehrqa.clinsql.execution_modes import SmokeExecutionConfig
from ehrqa.clinsql.execution_errors import classify_execution_failure
from ehrqa.clinsql.metadata import schema_records_from_manifest, verify_schema_manifest
from ehrqa.clinsql.result_artifacts import ResultArtifactStore, verify_windows_private_acl


CAPS = PHASE_A_MAX_BYTES
RESULT_ROOT = Path(__file__).resolve().parents[3] / 'results/restricted'


def claim_case_marker(root: Path, *, case_id: str, approval_id: str,
                      approval_sha256: str, sql_sha256: str) -> Path:
    """Claim each Phase A case once, even if a later approval ID changes."""
    if case_id not in CAPS:
        raise ValueError('Unknown Phase A case')
    marker = root / f'phase_a_{case_id}.started'
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump({'approval_id': approval_id, 'case_id': case_id,
                   'approval_sha256': approval_sha256,
                   'sql_sha256': sql_sha256, 'status': 'STARTED'}, stream)
    return marker


def require_scalar_result(result) -> None:
    if not result.complete or len(result.rows) != 1 or len(result.columns) != 1:
        raise ValueError('Phase A expected exactly one scalar result; review job before retry')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-id', choices=tuple(CAPS), required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--approval', type=Path)
    parser.add_argument('--execute-approved', action='store_true')
    args = parser.parse_args(argv)
    config = BigQueryConfig.from_env()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    verify_schema_manifest(manifest)
    cases = {case['id']: case for case in smoke_cases(config, Path('external/clinsql_official'))}
    case = cases[args.case_id]
    if not args.execute_approved:
        print(json.dumps({'status': 'PLAN_ONLY', 'case_id': args.case_id,
                          'sql': case['sql'], 'max_bytes_billed': CAPS[args.case_id],
                          'timeout_seconds': 30, 'patient_sql_executed': 0}, indent=2))
        return 0
    if args.approval is None:
        raise PermissionError('Completed approval file is required for Phase A execution')
    if args.approval.resolve().parent != RESULT_ROOT.resolve():
        raise PermissionError('Completed approval must reside in results/restricted')
    if not verify_windows_private_acl(RESULT_ROOT):
        raise PermissionError('Restricted result directory ACL is not verified')
    approval_bytes = args.approval.read_bytes()
    approval_sha256 = hashlib.sha256(approval_bytes).hexdigest()
    approval = ExecutionApproval.from_json_bytes(approval_bytes)
    approval.authorize(case_id=args.case_id, sql=case['sql'], config=config,
                       manifest=manifest, max_bytes_billed=CAPS[args.case_id],
                       timeout_seconds=30, max_rows=2)
    client = BigQueryClient(config, allow_data_execution=True, schema_manifest=manifest,
                            execution_approval=approval)
    adapter = BigQueryAdapter(client, schema_records_from_manifest(manifest),
                              SmokeExecutionConfig(args.case_id).limits(),
                              allowed_datasets=config.allowed_datasets)
    estimate = adapter.dry_run(case['sql']).estimated_bytes
    if estimate > CAPS[args.case_id]:
        raise ValueError('Dry run exceeds the approved bytes cap')
    artifact_id = f'{approval.approval_id}_{args.case_id}'
    if not artifact_id.replace('_', '').replace('-', '').isalnum():
        raise ValueError('Unsafe approval ID')
    claim_case_marker(RESULT_ROOT, case_id=args.case_id,
                      approval_id=approval.approval_id,
                      approval_sha256=approval_sha256,
                      sql_sha256=approval.sql_sha256_by_case[args.case_id])
    # A started marker remains after any failure. Never automatically repeat a job.
    summary_path = RESULT_ROOT / f'{artifact_id}.summary.json'
    started = time.monotonic()
    try:
        result = adapter.execute(case['sql'])
        require_scalar_result(result)
        artifact = ResultArtifactStore(RESULT_ROOT).save(artifact_id, result)
    except Exception as exc:
        status = ('TRUNCATED_RESULT' if isinstance(exc, ValueError) and
                  str(exc).startswith('Phase A expected exactly one scalar') else
                  classify_execution_failure(exc, stage='execute'))
        failure = {'status': status, 'phase': 'phase_a_smoke',
                   'approval_id': approval.approval_id, 'approval_sha256': approval_sha256,
                   'case_id': args.case_id, 'sql': case['sql'],
                   'error_type': type(exc).__name__, 'error': 'Details withheld',
                   'job_id': getattr(locals().get('result'), 'job_id', None),
                   'latency_seconds': time.monotonic() - started}
        with summary_path.open('x', encoding='utf-8') as stream:
            json.dump(failure, stream, indent=2)
        raise
    completed_at = datetime.now(timezone.utc)
    summary = {'status': 'COMPLETE', 'approval_id': approval.approval_id,
               'phase': 'phase_a_smoke',
               'approval_sha256': approval_sha256,
               'case_id': args.case_id, 'sql': case['sql'],
               'job_id': result.job_id, 'bytes_processed': result.bytes_processed,
               'bytes_billed': result.bytes_billed,
               'latency_seconds': result.latency_seconds or time.monotonic() - started,
               'column_names': list(result.columns), 'row_count': len(result.rows),
               'artifact_id': artifact_id, 'artifact_sha256': artifact['sha256'],
               'completed_at_utc': completed_at.isoformat(),
               'artifact_expires_at_utc': (completed_at + timedelta(
                   days=approval.artifact_retention_days)).isoformat()}
    with summary_path.open('x', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
