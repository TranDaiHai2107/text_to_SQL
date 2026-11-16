"""Pinned MIMIC-IV dictionary metadata for CLINSQL inference."""
import hashlib
import json
import re
from pathlib import Path

from ehrqa.agentic.retrieval import terms


DICTIONARIES = {
    'd_icd_diagnoses': ('icd_code', 'long_title'),
    'd_icd_procedures': ('icd_code', 'long_title'),
    'd_labitems': ('itemid', 'label'),
    'd_items': ('itemid', 'label'),
}


class ClinicalCatalog:
    def __init__(self, rows, *, source, sha256=None):
        self.source, self.sha256 = source, sha256
        self.records = {}
        for row in rows:
            table = row['table']
            if table not in DICTIONARIES:
                raise ValueError('Only MIMIC dictionary tables may supply clinical evidence')
            code_column, column = DICTIONARIES[table]
            code, label = row[code_column], row[column]
            if label is not None and not isinstance(label, str):
                raise ValueError('Clinical dictionary label must be text or NULL')
            extras = {'fluid', 'category'} if table == 'd_labitems' else {
                'linksto', 'abbreviation', 'unitname', 'category'} if table == 'd_items' else {'icd_version'}
            if set(row) - ({'table', code_column, column, 'aliases'} | extras):
                raise ValueError('Unexpected clinical dictionary fields')
            if code_column == 'icd_code':
                if type(row.get('icd_version')) is not int or row['icd_version'] not in (9, 10):
                    raise ValueError('ICD version must be 9 or 10')
                if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9.]+', code):
                    raise ValueError('ICD code must be a string from the dictionary')
            elif type(code) is not int or code <= 0:
                raise ValueError('Itemid must be a positive integer')
            aliases = row.get('aliases', [])
            if not isinstance(aliases, list) or any(not isinstance(x, str) or not x.strip() for x in aliases):
                raise ValueError('Invalid sourced concept aliases')
            record_id = f"{table}:{row.get('icd_version', '')}:{code}"
            if record_id in self.records:
                raise ValueError('Duplicate dictionary identity')
            self.records[record_id] = {
                'id': record_id, 'table': table, 'column': column, 'code_column': code_column,
                'code': code, 'label': label, 'aliases': tuple(aliases), 'source': source,
                **{key: row[key] for key in extras if key in row},
            }

    @classmethod
    def load(cls, path, *, expected_sha256, schema_sha256):
        data = Path(path).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError('Clinical dictionary SHA-256 mismatch')
        payload = json.loads(data)
        if (payload.get('mimic_version') != '3.1' or payload.get('schema_sha256') != schema_sha256
            or not isinstance(payload.get('source'), str) or not payload['source'].strip()
            or not payload.get('records')):
            raise ValueError('Clinical dictionary provenance or schema mismatch')
        return cls(payload['records'], source=payload['source'], sha256=expected_sha256)

    def search(self, question, schema_context, *, table=None, icd_version=None,
               limit=24, supplemental_aliases=None):
        words = terms(question)
        text = question.casefold()
        if supplemental_aliases is not None:
            text = ' '.join(re.findall(r'\w+', text))
        ranked = []
        for record in self.records.values():
            if table is not None and record['table'] != table:
                continue
            if icd_version is not None and record.get('icd_version') != icd_version:
                continue
            names = tuple(name for name in (record['label'], *record['aliases'],
                                            record.get('abbreviation'),
                                            *(supplemental_aliases or {}).get(record['id'], ()))
                          if name and name.strip())
            if not names:
                continue
            if supplemental_aliases is not None:
                names = tuple(' '.join(re.findall(r'\w+', name.casefold())) for name in names)
            exact = any(name and re.search(r'(?<!\w)' + re.escape(name.casefold()) + r'(?!\w)',
                                            text) for name in names)
            overlap = max(len(words & terms(name)) for name in names)
            if exact or overlap:
                ranked.append((not exact, -overlap, record['table'] not in schema_context['tables'],
                               record['id'], record))
        return [{**record, 'match': 'exact_surface' if not nonexact else 'lexical_candidate',
                 'candidate_list_complete': False}
                for nonexact, _, _, _, record in sorted(ranked)[:limit]]
