"""Offline plan by default; live metadata only with an explicit flag."""
from __future__ import annotations

import argparse
import json
import os

from ehrqa.clinsql.bigquery_client import BigQueryClient, discover_dataset_location
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.metadata import (HOSP_TABLES, ICU_TABLES, save_schema_manifest,
                                   validate_manifest_compatibility)


def plan() -> dict:
    return {'mode': 'offline_plan', 'hosp_tables': sorted(HOSP_TABLES),
            'icu_tables': sorted(ICU_TABLES), 'queries_executed': 0,
            'required_environment': ['BQ_PROJECT_ID', 'BQ_HOSP_DATASET', 'BQ_ICU_DATASET',
                                     'BQ_BILLING_PROJECT'],
            'location': 'discover with --discover-location, then set BQ_LOCATION'}


def inspect_remote(config: BigQueryConfig, *, client=None, manifest_path=None) -> dict:
    """Only INFORMATION_SCHEMA metadata and table metadata API; no patient SELECT."""
    transport = BigQueryClient(config, client=client)
    actual_location = discover_dataset_location(config.project_id, config.hosp_dataset,
                                                config.icu_dataset, config.billing_project,
                                                client=transport.client)
    if actual_location.upper() != config.location.upper():
        raise ValueError('Configured BQ_LOCATION differs from dataset location')
    manifest = transport.load_schema_manifest()
    schema_validation = validate_manifest_compatibility(manifest)
    if manifest_path:
        save_schema_manifest(manifest_path, manifest)
    row_counts = {}
    for entry in manifest['tables']:
        table_id = f"{config.project_id}.{entry['dataset']}.{entry['table']}"
        row_counts[table_id] = transport.client.get_table(table_id).num_rows
    return {'mode': 'metadata_check', 'location': actual_location,
            'table_count': len(manifest['tables']),
            'manifest_path': str(manifest_path) if manifest_path else None,
            'schema_sha256': manifest['sha256'], 'row_count_metadata': row_counts,
            'schema_validation': schema_validation,
            'metadata_queries_executed': 4, 'patient_queries_executed': 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover-location', action='store_true',
                        help='Read only the two dataset metadata objects; no query job')
    parser.add_argument('--execute-metadata', action='store_true',
                        help='Explicitly read INFORMATION_SCHEMA and table metadata')
    parser.add_argument('--manifest-path', help='Versioned output path for verified schema manifest')
    args = parser.parse_args(argv)
    if args.discover_location and args.execute_metadata:
        parser.error('Choose location discovery or metadata execution')
    if args.manifest_path and not args.execute_metadata:
        parser.error('--manifest-path requires --execute-metadata')
    if args.discover_location:
        names = ('BQ_PROJECT_ID', 'BQ_HOSP_DATASET', 'BQ_ICU_DATASET', 'BQ_BILLING_PROJECT')
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            parser.error('Missing BigQuery configuration: ' + ', '.join(missing))
        location = discover_dataset_location(*(os.environ[name] for name in names))
        result = {'mode': 'location_discovery', 'location': location,
                  'dataset_metadata_reads': 2, 'query_jobs_created': 0}
    else:
        result = (inspect_remote(BigQueryConfig.from_env(), manifest_path=args.manifest_path)
                  if args.execute_metadata else plan())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
