"""Approved, split-aware retrieval inputs for the benchmark-independent core."""
from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
import re


def _normal(text: str) -> str:
    return ' '.join(re.findall(r'\w+', text.casefold()))


def _near_duplicate(left, right):
    left, right = _normal(left), _normal(right)
    if left == right:
        return True
    # Mask instance numbers to exclude the same question template.
    left, right = (re.sub(r'\d+', '0', text) for text in (left, right))
    a, b = set(left.split()), set(right.split())
    return bool(a and b) and (len(a & b) / len(a | b) >= .8 or
                              SequenceMatcher(None, left, right, autojunk=False).ratio() >= .88)


class FewShotIndex:
    def __init__(self, examples: list[dict], *, blocked_sql_hashes=frozenset()):
        seen_ids = set()
        self.examples = []
        for row in examples:
            if row.get('split') != 'validation' or row.get('partition') != 'development':
                raise ValueError('Few-shot examples must come only from development validation')
            if row['query_id'] in seen_ids:
                raise ValueError('Duplicate few-shot ID')
            seen_ids.add(row['query_id'])
            digest = hashlib.sha256(_normal(row['sql']).encode()).hexdigest()
            if digest not in blocked_sql_hashes:
                self.examples.append({**row, 'sql_hash': digest})

    def retrieve(self, question: str, *, query_id: str | None = None, limit: int = 3):
        if not 0 <= limit <= 3:
            raise ValueError('CLINSQL few-shot cap is three')
        words = set(_normal(question).split())
        blocked = {row['sql_hash'] for row in self.examples if
                   row['query_id'] == query_id or _near_duplicate(row['question'], question)}
        candidates = [row for row in self.examples if row['sql_hash'] not in blocked
                      and words & set(_normal(row['question']).split())]
        candidates.sort(key=lambda r: (-len(words & set(_normal(r['question']).split())), r['query_id']))
        items = []
        seen = set()
        for row in candidates:
            if len(items) == limit:
                break
            if row['sql_hash'] in seen or any(_near_duplicate(row['question'], item['question']) for item in items):
                continue
            items.append({'question': row['question'], 'sql': row['sql'], 'source_id': row['query_id']})
            seen.add(row['sql_hash'])
        return {'items': items, 'found': bool(items),
                'few_shot_count': limit, 'source': 'validation_development_only'}


class ApprovedICDCatalog:
    """Dictionary/code labels supplied by a permitted offline source, never patient rows."""

    def __init__(self, records: list[dict] = ()): 
        self.records = tuple(records)
        for row in self.records:
            if row.get('table') not in {'d_icd_diagnoses', 'd_icd_procedures'}:
                raise ValueError('ICD catalog accepts dictionary records only')

    def search(self, question, _schema_context):
        words = set(_normal(question).split())
        return [r for r in self.records if words & set(_normal(r.get('label', '')).split())][:24]
