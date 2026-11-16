"""Read-only BigQuery table permission spot check for the reader ADC.

testIamPermissions can fail open; a negative write result does not certify
read-only IAM. No query jobs, table rows, or credential contents are read.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from ehrqa.clinsql.execution_control import verify_reader_adc  # noqa: E402
from ehrqa.clinsql.metadata import verify_schema_manifest  # noqa: E402


PERMISSIONS = ('bigquery.tables.get', 'bigquery.tables.getData',
               'bigquery.tables.update', 'bigquery.tables.updateData',
               'bigquery.tables.delete')


def main() -> int:
    from google.auth.transport.requests import AuthorizedSession

    manifest = json.loads((ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json')
                          .read_text(encoding='utf-8'))
    verify_schema_manifest(manifest)
    session = AuthorizedSession(verify_reader_adc(
        scopes=['https://www.googleapis.com/auth/cloud-platform']))
    read_count, write_count, errors = 0, 0, []
    for entry in manifest['tables']:
        resource = (f"projects/{manifest['project_id']}/datasets/{entry['dataset']}"
                    f"/tables/{entry['table']}")
        url = f'https://bigquery.googleapis.com/bigquery/v2/{resource}:testIamPermissions'
        response = session.post(url, json={'permissions': PERMISSIONS}, timeout=20)
        if response.status_code != 200:
            errors.append({'table': f"{entry['dataset']}.{entry['table']}",
                           'http_status': response.status_code})
            continue
        granted = set(response.json().get('permissions', ()))
        read_count += int({'bigquery.tables.get', 'bigquery.tables.getData'} <= granted)
        write_count += int(bool(granted & {'bigquery.tables.update',
                                           'bigquery.tables.updateData',
                                           'bigquery.tables.delete'}))
    print(json.dumps({'tables_checked': len(manifest['tables']),
                      'read_get_and_getData': read_count,
                      'tables_with_write_detected': write_count,
                      'errors': errors, 'iam_status': 'READ_ONLY_LIKELY',
                      'not_proof_of_read_only': True}, indent=2))
    return 0 if read_count == 31 and write_count == 0 and not errors else 1


if __name__ == '__main__':
    raise SystemExit(main())
