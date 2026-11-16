"""Export only the approved MIMIC dictionary columns through the SQL guard."""
import hashlib
import json
from pathlib import Path

from .clinical_catalog import ClinicalCatalog
from .execution_errors import IncompleteResultError
from .metadata import schema_records_from_manifest


FIELDS = {
    'd_icd_diagnoses': ('icd_code', 'icd_version', 'long_title'),
    'd_icd_procedures': ('icd_code', 'icd_version', 'long_title'),
    'd_labitems': ('itemid', 'label', 'fluid', 'category'),
    'd_items': ('itemid', 'label', 'abbreviation', 'linksto', 'unitname', 'category'),
}


def catalog_queries(manifest):
    records = {row['table']: row for row in schema_records_from_manifest(manifest)}
    return {
        table: (f"SELECT {', '.join(fields)} FROM "
                f"`{manifest['project_id']}.{records[table]['dataset']}.{table}` "
                f"ORDER BY {', '.join(fields[:2] if table.startswith('d_icd_') else fields[:1])}")
        for table, fields in FIELDS.items()
    }


def export_catalog(database, manifest, path, *, source, authorization):
    """The supplied database must carry the separate dictionary export scope."""
    if not authorization or not source:
        raise PermissionError('Dictionary export requires approved provenance and scope')
    if Path(path).exists():
        raise FileExistsError(path)
    records = []
    counts = {}
    usage = []
    for table, sql in catalog_queries(manifest).items():
        if not database.dry_run(sql).valid:
            raise ValueError(f'Dictionary dry run failed for {table}')
        result = database.execute(sql)
        if not result.complete:
            raise IncompleteResultError(f'Incomplete dictionary export for {table}')
        if result.columns != FIELDS[table] or not result.rows:
            raise ValueError(f'Dictionary export shape differs for {table}')
        counts[table] = len(result.rows)
        usage.append({'table': table, 'job_id': result.job_id, 'bytes_billed': result.bytes_billed,
                      'latency_seconds': result.latency_seconds})
        for values in result.rows:
            if len(values) != len(result.columns):
                raise ValueError('Dictionary row has an invalid shape')
            records.append({'table': table, **dict(zip(result.columns, values))})
    payload = {'format_version': 1, 'mimic_version': '3.1', 'source': source,
               'schema_sha256': manifest['sha256'], 'authorization_reference': authorization,
               'records': records}
    ClinicalCatalog(records, source=source)
    data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()
    with Path(path).open('xb') as stream:
        stream.write(data)
    return {'sha256': hashlib.sha256(data).hexdigest(), 'records': len(records),
            'row_counts': counts, 'jobs': usage, 'complete': True,
            'schema_sha256': manifest['sha256']}
