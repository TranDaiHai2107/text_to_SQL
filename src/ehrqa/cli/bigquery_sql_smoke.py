"""Five guarded BigQuery dry runs. Never executes SQL or persists patient rows."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from sqlglot import exp, parse_one

from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.bigquery_client import BigQueryClient
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.metadata import schema_records_from_manifest, verify_schema_manifest

MIB = 1_048_576
USD_PER_TIB = 6.25  # Budget estimate only; billing/free tier may differ.


def smoke_cases(config: BigQueryConfig, official_root: Path) -> list[dict]:
    hosp, icu = config.allowed_datasets
    source = (official_root / 'data/splits/validation/Patient_Demographics_and_Admissions'
              / 'easy_level_queries/043/sql_043.sql')
    gold_original = source.read_text(encoding='utf-8')
    gold_adapted = gold_original.replace('`physionet-data.mimiciv_3_1_hosp.', f'`{hosp}.')
    if gold_original.count('`physionet-data.mimiciv_3_1_hosp.') != 2:
        raise ValueError('Unexpected official validation gold table references')
    return [
        {'id': 'constant', 'sql': 'SELECT 1 AS smoke_constant', 'expected': 'smoke_constant=1'},
        {'id': 'hosp_patients_count', 'sql': f'SELECT COUNT(*) AS n FROM `{hosp}.patients`',
         'expected': 'Metadata num_rows=364627; actual COUNT may differ'},
        {'id': 'icu_icustays_count', 'sql': f'SELECT COUNT(*) AS n FROM `{icu}.icustays`',
         'expected': 'Metadata num_rows=94458; actual COUNT may differ'},
        {'id': 'icu_hosp_join', 'sql': (f'SELECT COUNT(*) AS n FROM `{icu}.icustays` i '
                                        f'JOIN `{hosp}.admissions` a ON i.hadm_id = a.hadm_id'),
         'expected': 'One scalar count; no verified reference value'},
        {'id': 'clinsql_validation_043', 'sql': gold_adapted,
         'expected': 'Official validation result iqr_in_hospital_mortality=0',
         'source': str(source),
         'adaptation': 'Only project prefix changed in memory; source gold SQL unchanged'},
    ]


def prepare(config: BigQueryConfig, manifest: dict, official_root: Path, client) -> list[dict]:
    verify_schema_manifest(manifest)
    if (manifest['project_id'] != config.project_id or
        manifest['datasets'] != {'hosp': config.hosp_dataset, 'icu': config.icu_dataset} or
        manifest['location'].upper() != config.location.upper()):
        raise ValueError('Manifest does not match BigQuery configuration')
    records = schema_records_from_manifest(manifest)
    adapter = BigQueryAdapter(client, records, Limits(1 << 50, allow_data_execution=False),
                              allowed_datasets=config.allowed_datasets)
    output = []
    for case in smoke_cases(config, official_root):
        row = dict(case)
        row['tables'] = sorted({f'{t.catalog}.{t.db}.{t.name}' for t in
                                parse_one(case['sql'], read='bigquery').find_all(exp.Table)})
        try:
            estimate = adapter.dry_run(case['sql']).estimated_bytes
            billable_floor = (max(estimate, 10 * MIB * len(row['tables']))
                              if estimate else 0)
            row.update(dry_run='PASS', estimated_bytes_processed=estimate,
                       estimated_cost_usd=round(billable_floor / (1 << 40) * USD_PER_TIB, 8),
                       proposed_maximum_bytes_billed=max(10 * MIB,
                           math.ceil(max(estimate * 1.2, billable_floor) / MIB) * MIB),
                       execution='BLOCKED_PENDING_READ_ONLY_IAM_AND_APPROVAL' if row['tables'] else
                                 'BLOCKED_PENDING_READ_ONLY_IAM')
        except Exception as exc:
            row.update(dry_run='FAIL', error_type=type(exc).__name__,
                       error='BigQuery dry run rejected; details withheld', execution='BLOCKED')
        output.append(row)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--official-root', type=Path, default=Path('external/clinsql_official'))
    args = parser.parse_args(argv)
    config = BigQueryConfig.from_env()
    manifest = json.loads(args.manifest.read_text(encoding='utf-8'))
    rows = prepare(config, manifest, args.official_root,
                   BigQueryClient(config, schema_manifest=manifest))
    print(json.dumps({'manifest_sha256': manifest['sha256'], 'smoke_cases': rows,
                      'patient_sql_executed': 0, 'constant_sql_executed': 0},
                     indent=2, ensure_ascii=False))
    return 0 if all(row['dry_run'] == 'PASS' for row in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
