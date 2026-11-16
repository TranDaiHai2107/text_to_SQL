"""Dataset-scoped BigQuery schema manifests; no MIMIC Mini dependency."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ICU_TABLES = frozenset('caregiver chartevents d_items datetimeevents icustays ingredientevents inputevents outputevents procedureevents'.split())
HOSP_TABLES = frozenset('admissions d_hcpcs d_icd_diagnoses d_icd_procedures d_labitems diagnoses_icd drgcodes emar emar_detail hcpcsevents labevents microbiologyevents omr patients pharmacy poe poe_detail prescriptions procedures_icd provider services transfers'.split())
MANIFEST_VERSION = 1


def information_schema_sql(project: str, dataset: str, view: str) -> str:
    if view not in {'TABLES', 'COLUMNS'} or not all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in (project, dataset)):
        raise ValueError('Invalid BigQuery INFORMATION_SCHEMA scope')
    fields = ('table_name, table_type' if view == 'TABLES' else
              'table_name, column_name, data_type, is_nullable, ordinal_position')
    order = 'table_name' if view == 'TABLES' else 'table_name, ordinal_position'
    return f'SELECT {fields} FROM `{project}.{dataset}.INFORMATION_SCHEMA.{view}` ORDER BY {order}'


def _digest(content: dict) -> str:
    return hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode('utf-8')).hexdigest()


def build_schema_manifest(config, tables_by_role: dict, columns_by_role: dict) -> dict:
    entries = []
    for role, dataset, expected in (('hosp', config.hosp_dataset, HOSP_TABLES),
                                    ('icu', config.icu_dataset, ICU_TABLES)):
        table_rows = tables_by_role[role]
        names = {row['table_name'] for row in table_rows if row['table_type'] == 'BASE TABLE'}
        if names != expected or len(table_rows) != len(names):
            raise ValueError(f'{role} inventory differs from expected 31-table MIMIC-IV 3.1 inventory')
        grouped = {name: [] for name in names}
        for row in columns_by_role[role]:
            if row['table_name'] not in grouped or not row['column_name'] or not row['data_type']:
                raise ValueError('Unexpected or incomplete INFORMATION_SCHEMA column')
            grouped[row['table_name']].append({'name': row['column_name'], 'type': row['data_type'],
                                               'nullable': row['is_nullable'] == 'YES',
                                               'ordinal': int(row['ordinal_position'])})
        for name in sorted(names):
            cols = sorted(grouped[name], key=lambda col: col['ordinal'])
            if not cols or [col['ordinal'] for col in cols] != list(range(1, len(cols) + 1)):
                raise ValueError(f'Incomplete column positions for {role}.{name}')
            if len({col['name'] for col in cols}) != len(cols):
                raise ValueError(f'Duplicate columns for {role}.{name}')
            entries.append({'role': role, 'dataset': dataset, 'table': name, 'columns': cols})
    content = {'manifest_version': MANIFEST_VERSION,
               'captured_at_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'source': 'bigquery_information_schema',
               'project_id': config.project_id, 'location': config.location,
               'datasets': {'hosp': config.hosp_dataset, 'icu': config.icu_dataset},
               'tables': entries}
    return {**content, 'sha256': _digest(content)}


def verify_schema_manifest(manifest: dict) -> None:
    content = {key: value for key, value in manifest.items() if key != 'sha256'}
    if manifest.get('source') != 'bigquery_information_schema' or manifest.get('manifest_version') != MANIFEST_VERSION or manifest.get('sha256') != _digest(content):
        raise ValueError('Unverified or corrupted BigQuery schema manifest')
    if len(manifest.get('tables', [])) != 31:
        raise ValueError('Incomplete BigQuery schema manifest')
    for role, expected in (('hosp', HOSP_TABLES), ('icu', ICU_TABLES)):
        entries = [e for e in manifest['tables'] if e['role'] == role]
        if {e['table'] for e in entries} != expected or len(entries) != len(expected):
            raise ValueError('Incorrect table inventory in BigQuery schema manifest')
        if any(e['dataset'] != manifest['datasets'][role] or not e['columns'] for e in entries):
            raise ValueError('Incorrect dataset or empty columns in schema manifest')


def schema_records_from_manifest(manifest: dict) -> list[dict]:
    """Stable Schema RAG input rebuilt only from a verified live metadata snapshot."""
    verify_schema_manifest(manifest)
    output = []
    for entry in manifest['tables']:
        table, dataset, project = entry['table'], entry['dataset'], manifest['project_id']
        if not all(re.fullmatch(r'[A-Za-z0-9_-]+', x) for x in (project, dataset, table)):
            raise ValueError('Unsafe table identifier')
        cols = entry['columns']
        if any(not re.fullmatch(r'[A-Za-z0-9_]+', col['name']) for col in cols):
            raise ValueError('Unsafe column identifier')
        ddl = f'CREATE TABLE `{project}.{dataset}.{table}` (\n' + ',\n'.join(
            f"  `{col['name']}` {col['type']}" for col in cols) + '\n)'
        output.append({'table': table, 'dataset': dataset, 'ddl': ddl,
                       'description_en': table.replace('_', ' '),
                       'type_source': 'bigquery_information_schema',
                       'schema_sha256': manifest['sha256']})
    return output


def validate_manifest_compatibility(manifest: dict) -> dict:
    """Check CLINSQL join keys and SQLGlot parsing without reading table rows."""
    records = schema_records_from_manifest(manifest)
    required = {
        'patients': {'subject_id'},
        'admissions': {'subject_id', 'hadm_id'},
        'icustays': {'subject_id', 'hadm_id', 'stay_id'},
        'diagnoses_icd': {'subject_id', 'hadm_id', 'icd_code', 'icd_version'},
        'd_icd_diagnoses': {'icd_code', 'icd_version'},
        'procedures_icd': {'subject_id', 'hadm_id', 'icd_code', 'icd_version'},
        'd_icd_procedures': {'icd_code', 'icd_version'},
        'labevents': {'subject_id', 'hadm_id', 'itemid'},
        'chartevents': {'subject_id', 'hadm_id', 'stay_id', 'itemid'},
        'datetimeevents': {'subject_id', 'hadm_id', 'stay_id', 'itemid'},
    }
    columns = {entry['table']: {col['name'] for col in entry['columns']}
               for entry in manifest['tables']}
    missing = {name: sorted(names - columns[name]) for name, names in required.items()
               if names - columns[name]}
    sqlglot_error = None
    try:
        from ehrqa.agentic.schema import Schema
        parsed = Schema.from_records(records, dialect='bigquery')
        if len(parsed.tables) != 31:
            sqlglot_error = 'SQLGlot parsed fewer than 31 tables'
    except Exception as exc:
        sqlglot_error = f'{type(exc).__name__}: {str(exc).splitlines()[0][:200]}'
    return {'pass': not missing and sqlglot_error is None,
            'table_count': len(columns), 'datetimeevents_present': 'datetimeevents' in columns,
            'missing_critical_columns': missing, 'sqlglot_error': sqlglot_error}


def save_schema_manifest(path: Path, manifest: dict) -> Path:
    verify_schema_manifest(manifest)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Schema manifest exists; use a new versioned path')
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return path


def mock_schema_records(project: str, hosp_dataset: str, icu_dataset: str) -> list[dict]:
    """Synthetic schema for offline unit tests, never authoritative for CLINSQL."""
    output = []
    for dataset, names in ((hosp_dataset, HOSP_TABLES), (icu_dataset, ICU_TABLES)):
        for table in sorted(names):
            output.append({'table': table, 'dataset': dataset,
                           'ddl': f'CREATE TABLE `{project}.{dataset}.{table}` (`subject_id` INT64, `hadm_id` INT64)',
                           'description_en': table, 'type_source': 'synthetic_mock_only'})
    return output
