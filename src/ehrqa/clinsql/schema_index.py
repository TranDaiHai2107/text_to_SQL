"""Deterministic schema-only retrieval over a pinned BigQuery metadata snapshot."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .metadata import schema_records_from_manifest, verify_schema_manifest

INDEX_VERSION = 1


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':')).encode('utf-8')


def build_schema_index(manifest: dict) -> dict:
    verify_schema_manifest(manifest)
    records = schema_records_from_manifest(manifest)
    entries = []
    for record in records:
        entries.append({'table': record['table'], 'dataset': record['dataset'],
                        'ddl': record['ddl'], 'description_en': record['description_en']})
    payload = {'index_version': INDEX_VERSION, 'schema_sha256': manifest['sha256'],
               'project_id': manifest['project_id'], 'entries': sorted(entries, key=lambda e: (e['dataset'], e['table']))}
    return {**payload, 'sha256': hashlib.sha256(_canonical(payload)).hexdigest()}


def verify_schema_index(index: dict, manifest: dict) -> None:
    expected = build_schema_index(manifest)
    if index != expected:
        raise ValueError('Schema index differs from pinned BigQuery manifest')


def save_schema_index(path: Path, index: dict, manifest: dict) -> Path:
    verify_schema_index(index, manifest)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as stream:
        json.dump(index, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return path


class SchemaIndex:
    def __init__(self, index: dict, manifest: dict):
        verify_schema_index(index, manifest)
        self.index = index

    @classmethod
    def load(cls, path: Path, manifest: dict) -> 'SchemaIndex':
        return cls(json.loads(Path(path).read_text(encoding='utf-8')), manifest)

    def retrieve(self, question: str, *, limit: int = 8) -> list[dict]:
        if not 1 <= limit <= 31:
            raise ValueError('Schema retrieval limit must be between 1 and 31')
        terms = set(re.findall(r'[a-z0-9]+', question.casefold()))
        ranked = []
        for entry in self.index['entries']:
            table_terms = set(entry['table'].split('_')) | {entry['table']}
            column_terms = set(re.findall(r'`([a-z0-9_]+)`', entry['ddl'].casefold()))
            score = 3 * len(terms & table_terms) + len(terms & column_terms)
            ranked.append((-score, entry['dataset'], entry['table'], entry))
        return [item[3] for item in sorted(ranked)[:limit]]

    def schema_records(self) -> list[dict]:
        return [{**entry, 'schema_sha256': self.index['schema_sha256'],
                 'type_source': 'bigquery_information_schema'} for entry in self.index['entries']]
