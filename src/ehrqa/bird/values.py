"""Stored-value retrieval: the BIRD counterpart of Ours' dictionary (catalog) layer.

Distinct short text values of every column are indexed once per database (cached as JSON).
A question (plus external knowledge) retrieves values whose words it mentions, so the
generator can compare against values exactly as stored. Records follow the catalog format
used by the linker contract (table/column/code_column/code/label).
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import threading

MAX_VALUE_CHARS = 80
MAX_DISTINCT_PER_COLUMN = 50_000
MAX_VALUE_WORDS = 8
STOP = set('''a an and are as at be by did do does for from had has have how in is it its many me
much of on or that the their there these this those to was were what when where which who whom whose
why with list name names give show tell find all any each number count total average among than more
most less least between'''.split())


def words(text: str) -> list[str]:
    return re.findall(r'[0-9a-z]+', str(text).casefold())


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class ValueIndex:
    def __init__(self, database, cache_dir: Path | None):
        self.db = database
        self.cache = Path(cache_dir) / f'{database.db_id}.json' if cache_dir else None
        self._lock = threading.Lock()
        self._postings = None
        self._values = None

    def _build(self) -> list[list]:
        values = []
        con = self.db._connect()
        try:
            for table, columns in self.db.schema.tables.items():
                for column, kind in columns.items():
                    if any(t in kind.upper() for t in ('INT', 'REAL', 'FLOA', 'DOUB', 'NUM', 'DEC', 'BLOB')):
                        continue
                    sql = (f'SELECT DISTINCT {_quote(column)} FROM {_quote(table)} WHERE {_quote(column)} IS NOT NULL '
                           f'AND typeof({_quote(column)})=\'text\' AND length({_quote(column)}) BETWEEN 1 AND {MAX_VALUE_CHARS} '
                           f'LIMIT {MAX_DISTINCT_PER_COLUMN + 1}')
                    rows = [r[0] for r in con.execute(sql)]
                    if len(rows) > MAX_DISTINCT_PER_COLUMN:
                        continue  # free-text/identifier-like column; not a categorical value set
                    values.extend([table, column, v] for v in rows if len(words(v)) <= MAX_VALUE_WORDS)
        finally:
            con.close()
        return values

    def _load(self):
        with self._lock:
            if self._values is not None:
                return
            if self.cache and self.cache.exists():
                values = json.loads(self.cache.read_text(encoding='utf-8'))
            else:
                values = self._build()
                if self.cache:
                    self.cache.parent.mkdir(parents=True, exist_ok=True)
                    self.cache.write_text(json.dumps(values, ensure_ascii=False), encoding='utf-8')
            postings = defaultdict(list)
            for i, (_, _, value) in enumerate(values):
                for w in set(words(value)):
                    if w not in STOP:
                        postings[w].append(i)
            self._values, self._postings = values, postings

    def search(self, question: str, limit: int = 24, per_column: int = 4) -> list[dict]:
        self._load()
        text = question.casefold()
        qwords = [w for w in words(question) if w not in STOP and (len(w) >= 3 or w.isdigit())]
        quoted = {m.casefold() for pair in re.findall(r"'([^']{1,80})'|\"([^\"]{1,80})\"", question)
                  for m in pair if m}
        hits = defaultdict(int)
        for w in set(qwords):
            postings = self._postings.get(w, ())
            if len(postings) > 2000:
                continue  # word too common to identify a value
            for i in postings:
                hits[i] += 1
        scored = []
        for i, matched in hits.items():
            table, column, value = self._values[i]
            folded = str(value).casefold()
            vwords = [w for w in words(value) if w not in STOP] or words(value)
            coverage = matched / max(1, len(set(vwords)))
            exact = folded in quoted or bool(re.search(r'(?<![0-9a-z])' + re.escape(folded) + r'(?![0-9a-z])', text))
            if not re.search(r'[a-z]', folded):
                if folded not in quoted:
                    continue  # bare numbers are compared numerically, not looked up as stored text
            if not exact and coverage < 0.5:
                continue
            scored.append((int(exact) * 100 + round(coverage * 10) + matched, table, column, value, exact))
        scored.sort(key=lambda r: (-r[0], len(str(r[3])), r[1], r[2], str(r[3])))
        per = defaultdict(int)
        records = []
        for score, table, column, value, exact in scored:
            if per[(table, column)] >= per_column:
                continue
            per[(table, column)] += 1
            records.append({'id': f'{table}:{column}:{value}', 'table': table, 'column': column,
                            'code_column': column, 'code': value, 'label': value,
                            'match': 'exact_surface' if exact else 'lexical_candidate', 'score': score,
                            'candidate_list_complete': False})
            if len(records) >= limit:
                break
        return records
