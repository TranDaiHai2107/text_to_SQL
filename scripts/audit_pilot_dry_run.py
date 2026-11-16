"""Recheck the last saved pilot SQL by BigQuery dry run only; never execute it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
from ehrqa.clinsql.bigquery_client import BigQueryClient
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.execution_control import verify_reader_adc
from ehrqa.clinsql.metadata import verify_schema_manifest


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-log', type=Path, required=True)
    parser.add_argument('--approval', type=Path, required=True)
    args = parser.parse_args(argv)
    log_path = args.run_log.resolve()
    if not log_path.is_relative_to((ROOT / 'results').resolve()):
        raise PermissionError('Only saved pilot run logs may be audited')
    log = json.loads(log_path.read_text(encoding='utf-8'))
    dry_runs = [event for event in log['events'] if event.get('stage') == 'dry_run'
                and isinstance(event.get('sql'), str)]
    if not dry_runs:
        raise ValueError('No saved SQL for dry-run audit')
    sql = dry_runs[-1]['sql']
    manifest = json.loads((ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json')
                          .read_text(encoding='utf-8'))
    verify_schema_manifest(manifest)
    approval = BenchmarkExecutionApproval.from_file(args.approval)
    approval.verify_active()
    config = BigQueryConfig(manifest['project_id'],
                            manifest['datasets']['hosp'],
                            manifest['datasets']['icu'],
                            manifest['location'], approval.project_id)
    if approval.manifest_sha256 != manifest['sha256']:
        raise PermissionError('Approval differs from schema manifest')
    verify_reader_adc()
    client = BigQueryClient(config, allow_data_execution=False,
                            schema_manifest=manifest,
                            execution_approval=approval)
    estimate = client.dry_run(sql, timeout_seconds=approval.timeout_seconds)
    print(json.dumps({'mode': 'DRY_RUN_ONLY', 'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(),
                      'bytes_processed_estimate': estimate,
                      'mib_processed_estimate': round(estimate / 2**20, 3),
                      'approved_max_bytes_billed': approval.max_bytes_billed_per_sql,
                      'exceeds_approved_cap': estimate > approval.max_bytes_billed_per_sql,
                      'patient_rows_read': 0}))


if __name__ == '__main__':
    main()
