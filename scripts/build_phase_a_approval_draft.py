"""Create a non-executable Phase A approval draft; no BigQuery connection."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.cli.bigquery_sql_smoke import MIB, smoke_cases  # noqa: E402
from ehrqa.clinsql.config import BigQueryConfig  # noqa: E402
from ehrqa.clinsql.metadata import verify_schema_manifest  # noqa: E402


def main() -> None:
    manifest_path = ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    verify_schema_manifest(manifest)
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp',
                            'mimiciv_3_1_icu', 'US', 'kltn-text-to-sql')
    caps = {'hosp_patients_count': 10 * MIB, 'icu_icustays_count': 10 * MIB,
            'icu_hosp_join': 20 * MIB, 'clinsql_validation_043': 23 * MIB}
    cases = {case['id']: case['sql'] for case in smoke_cases(config, ROOT / 'external/clinsql_official')
             if case['id'] in caps}
    if set(cases) != set(caps):
        raise ValueError('Phase A smoke inventory changed')
    draft = {
        'approval_id': '', 'approver': '', 'authority': '',
        'organization_policy_clearance_reference': '',
        'iam_status': 'READ_ONLY_LIKELY_WITH_APPROVED_RISK',
        'risk_acknowledged': False,
        'valid_from_utc': '', 'valid_until_utc': '',
        'principal': 'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com',
        'project_id': config.project_id, 'datasets': list(config.allowed_datasets),
        'location': config.location, 'manifest_sha256': manifest['sha256'],
        'phase': 'phase_a_smoke',
        'sql_sha256_by_case': {case_id: hashlib.sha256(sql.encode('utf-8')).hexdigest()
                               for case_id, sql in cases.items()},
        'max_bytes_billed_by_case': caps,
        'timeout_seconds': 30, 'max_rows': 2,
        'result_storage_policy_reference': '',
        'artifact_retention_days': 7,
    }
    destination = ROOT / 'docs/PHASE_A_APPROVAL_DRAFT.json'
    destination.write_text(json.dumps(draft, indent=2) + '\n', encoding='utf-8')
    print(f'Wrote inactive approval draft: {destination}')


if __name__ == '__main__':
    main()
