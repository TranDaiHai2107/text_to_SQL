"""SQLite schema and read-only execution for one BIRD database.

Schema text shown to the model is the baseline's own per-table DDL (OmniSQL ``input_seq``:
column types, descriptions and example values), so Ours and the baseline see the same
database information. Column names/types and foreign keys come from SQLite itself.
"""
from __future__ import annotations

from pathlib import Path
import re
import sqlite3
import time

from ehrqa.agentic.database import QueryResult
from ehrqa.agentic.schema import Schema

from .values import ValueIndex

EXECUTION_TIMEOUT_SECONDS = 60  # same limit as the scorer (score_bird.py --timeout 60)
MAX_ROWS = 200_000
_CREATE = re.compile(r'CREATE TABLE\s+(`[^`]+`|"[^"]+"|\S+)\s*\(', re.I)


def schema_ddl_blocks(input_seq: str) -> dict[str, str]:
    """Per-table DDL from an OmniSQL prompt (``Database Schema:`` section)."""
    start = input_seq.index('Database Schema:\n') + len('Database Schema:\n')
    end = input_seq.index('\nThis schema describes', start)
    text = input_seq[start:end]
    positions = [m.start() for m in _CREATE.finditer(text)] + [len(text)]
    blocks = {}
    for a, b in zip(positions, positions[1:]):
        block = text[a:b].strip()
        name = _CREATE.match(block).group(1).strip('`"')
        blocks[name] = block
    return blocks


class BirdSchema(Schema):
    """SQLite identifiers are case-insensitive: canonicalize to the stored spelling."""

    def __post_init__(self):
        super().__post_init__()
        self._tables = {t.lower(): t for t in self.tables}
        self._columns = {t: {c.lower(): c for c in cols} for t, cols in self.tables.items()}

    def canonical_table(self, name):
        return self._tables.get(str(name).strip('`"[]').lower()) if name is not None else None

    def canonical_ref(self, ref):
        if not isinstance(ref, str) or ref.count('.') != 1:
            return None
        table, column = ref.split('.')
        table = self.canonical_table(table)
        if table is None:
            return None
        column = self._columns[table].get(column.strip('`"[]').lower())
        return f'{table}.{column}' if column else None

    def has_ref(self, ref):
        return self.canonical_ref(ref) is not None

    def edge_path(self, left, right):
        return super().edge_path(self.canonical_ref(left) or left, self.canonical_ref(right) or right)

    def _canonical_tables(self, tables):
        return {self.canonical_table(t) for t in tables} - {None}

    def join_closure(self, tables):
        return super().join_closure(self._canonical_tables(tables))

    def payload(self, tables=None):
        return super().payload(None if tables is None else self._canonical_tables(tables))


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class BirdDatabase:
    def __init__(self, db_file: Path, input_seq: str, *, value_index_dir: Path | None = None,
                 timeout: float = EXECUTION_TIMEOUT_SECONDS):
        self.path = Path(db_file)
        self.db_id = self.path.stem
        self.timeout = timeout
        blocks = schema_ddl_blocks(input_seq)
        tables, ddl = {}, {}
        foreign, primary = [], {}
        con = self._connect()
        try:
            names = [r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            by_lower = {k.lower(): v for k, v in blocks.items()}
            for name in names:
                info = con.execute(f'PRAGMA table_info({_quote(name)})').fetchall()
                tables[name] = {row[1]: (row[2] or 'TEXT') for row in info}
                ddl[name] = by_lower.get(name.lower())
                primary[name] = [row[1] for row in sorted(info, key=lambda r: r[5]) if row[5]]
                for fk in con.execute(f'PRAGMA foreign_key_list({_quote(name)})').fetchall():
                    foreign.append((name, fk[3], fk[2], fk[4]))
        finally:
            con.close()
        missing = [t for t, text in ddl.items() if text is None]
        if missing:
            raise ValueError(f'{self.db_id}: no prompt DDL for tables {missing}')
        self.schema = BirdSchema(tables, ddl, 'sqlite', {t: t for t in tables})
        for table, column, ref_table, ref_column in foreign:
            target = self.schema.canonical_table(ref_table)
            if target is None:
                continue
            if ref_column is None:  # FOREIGN KEY ... REFERENCES t: the primary key of t
                ref_column = primary[target][0] if len(primary[target]) == 1 else None
            left = self.schema.canonical_ref(f'{table}.{column}')
            right = self.schema.canonical_ref(f'{target}.{ref_column}')
            if left and right:
                self.schema.add_edge(left, right, 'sqlite_foreign_key')
        self.values = ValueIndex(self, value_index_dir)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(f'file:{self.path.as_posix()}?mode=ro', uri=True, check_same_thread=False)

    def execute(self, sql: str, question: str = '') -> QueryResult:
        con = self._connect()
        started = time.monotonic()
        con.set_progress_handler(lambda: 1 if time.monotonic() - started > self.timeout else 0, 10_000)
        try:
            cursor = con.execute(sql)
            rows = cursor.fetchmany(MAX_ROWS)
            columns = [d[0] for d in cursor.description or ()]
        except sqlite3.OperationalError as error:
            if 'interrupted' in str(error):
                raise ValueError(f'SQLite execution exceeded {self.timeout:.0f} s; the query is too slow '
                                 '(check joins and filters)') from None
            raise ValueError(f'SQLite error: {error}') from None
        except (sqlite3.Error, sqlite3.Warning) as error:
            raise ValueError(f'SQLite error: {error}') from None
        finally:
            con.close()
        return QueryResult(columns=columns, rows=[tuple(r) for r in rows], complete=True)

    def catalog_search(self, question: str, tables) -> list[dict]:
        return self.values.search(question)
