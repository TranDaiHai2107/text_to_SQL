"""Read-only BigQuery implementation of MAC-SQL's column value sampler."""
from datetime import date, datetime, time
import ast
from functools import lru_cache
from hashlib import sha256
import re
from types import SimpleNamespace

from sqlglot import exp, parse_one

from ..execution_errors import IncompleteResultError
from ..source_templates import ROOT, isolated_function


_NUMERIC = {'INT64', 'FLOAT64', 'NUMERIC', 'BIGNUMERIC'}
_SCALAR = _NUMERIC | {'STRING', 'BOOL', 'DATE', 'DATETIME', 'TIME', 'TIMESTAMP'}
_TEMPORAL = {'DATE', 'DATETIME', 'TIME', 'TIMESTAMP'}
_DATE_BEARING = _TEMPORAL - {'TIME'}
# Match the whitespace used by Python str.strip() and the email pattern.
_WHITESPACE = r'\x09-\x0D\x1C-\x20\x85\xA0\x{1680}\x{2000}-\x{200A}\x{2028}\x{2029}\x{202F}\x{205F}\x{3000}'


@lru_cache(maxsize=1)
def _native_formatter():
    def utility(name):
        return isolated_function('mac_sql_official', 'core/utils.py', name)

    is_date = utility('is_valid_date')
    is_date.__globals__['re'] = re
    is_date_column = utility('is_valid_date_column')
    is_date_column.__globals__['is_valid_date'] = is_date
    is_email = utility('is_email')
    is_email.__globals__['re'] = re
    return native_selector_method('_get_value_examples_str',
                                  dict(List=list, is_valid_date_column=is_date_column, is_email=is_email))


def native_selector_method(name, scope=None):
    path = ROOT / 'mac_sql_official/core/agents.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    selector = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == 'Selector')
    method = next(node for node in selector.body if isinstance(node, ast.FunctionDef) and node.name == name)
    scope = {} if scope is None else scope
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), scope)
    return scope[name]


def format_examples(values, kind):
    # Preserve the database values, converting typed temporal values to the text
    # representation that the source formatter inspects for a date prefix.
    values = [str(value) if isinstance(value, (date, datetime, time)) else value
              for value in values]
    source_type = 'NUMERIC' if kind in _NUMERIC else 'TEXT' if kind == 'STRING' else kind
    return _native_formatter()(SimpleNamespace(dataset_name='bird'), values, source_type)


def qualified_table(ddl):
    tree = parse_one(ddl, read='bigquery')
    table = tree.this.this
    if not isinstance(table, exp.Table) or len(table.parts) != 3 or any(
        not re.fullmatch(r'[A-Za-z0-9_-]+', part.name) for part in table.parts
    ):
        raise ValueError('MAC-SQL sampling requires a qualified metadata table')
    return '`' + '.'.join(part.name for part in table.parts) + '`'


def column_sample_queries(schema, keys, *, bounded=True, legacy=False):
    for table, columns in schema.tables.items():
        table_sql = qualified_table(schema.ddl[table])
        for column, kind in columns.items():
            kind = kind.split('(', 1)[0].upper()
            if (column in keys.get(table, ()) or column.lower().endswith(('id', 'email', 'url'))
                or kind not in _SCALAR):
                continue
            if not re.fullmatch(r'[A-Za-z0-9_]+', column):
                raise ValueError('Unsafe MAC-SQL sampling column identifier')
            field = f'`{column}`'
            sql = f'SELECT {field} FROM {table_sql} GROUP BY {field} ORDER BY COUNT(*) DESC, {field}'
            if kind in _NUMERIC:
                sql += ' LIMIT 11'
            elif bounded and (legacy or kind != 'STRING'):
                # Reserve a slot for NULL without displacing the first usable
                # value(s) in the original frequency and value ordering.
                limit = 2 if kind in (_TEMPORAL if legacy else _DATE_BEARING) else 7
                group_key = '1' if column.casefold() in {'frequency', 'sample_value'} else field
                sql = (
                    f'WITH ranked AS (SELECT {field} AS sample_value, COUNT(*) AS frequency '
                    f'FROM {table_sql} GROUP BY {group_key}) '
                )
                source, condition = 'ranked', ''
                if kind == 'STRING':
                    bad = (f"LENGTH(sample_value) > 50 OR STRPOS(sample_value, 'http://') > 0 "
                           f"OR STRPOS(sample_value, 'https://') > 0 OR REGEXP_CONTAINS(sample_value, "
                           rf"r'^[^{_WHITESPACE}@]+@[^{_WHITESPACE}@]+\.[^{_WHITESPACE}@]+$')")
                    sql += (f', screened AS (SELECT *, COUNTIF({bad}) OVER () AS invalid_values FROM ranked) ')
                    source = 'screened'
                    condition = (f"WHERE invalid_values = 0 AND (sample_value IS NULL OR "
                                 f"NOT REGEXP_CONTAINS(sample_value, r'^[{_WHITESPACE}]*$')) ")
                sql += (f'SELECT sample_value FROM {source} {condition}'
                        f'ORDER BY sample_value IS NULL DESC, frequency DESC, sample_value LIMIT {limit}')
            yield table, column, kind, sql


def missing_sample_columns(schema, keys, settled):
    """Find slots that lack either a source-aligned or original distinct job."""
    current = column_sample_queries(schema, keys)
    original = column_sample_queries(schema, keys, bounded=False)
    return [(table, column) for (table, column, _, sql), (_, _, _, raw) in zip(current, original, strict=True)
            if all(sha256(query.encode()).hexdigest() not in settled for query in (sql, raw))]


def sample_column_values(database, schema, keys, *, recover=None, recover_bounded=None):
    """Return evidence locally through the existing guarded dry-run/probe interface."""
    samples = {table: {} for table in schema.tables}
    original = {(table, column): sql for table, column, _, sql in
                column_sample_queries(schema, keys, bounded=False)} if recover else {}
    for table, column, kind, sql in column_sample_queries(schema, keys):
        if recover_bounded is not None:
            saved = recover_bounded(sql, kind)
            if saved is not None:
                samples[table][column] = saved
                continue
        if recover is not None and (recover_bounded is None or original[table, column] != sql):
            saved = recover(original[table, column], kind)
            if saved is not None:
                samples[table][column] = saved
                continue
        try:
            if not database.dry_run(sql).valid:
                raise ValueError('MAC-SQL sample failed dry run')
            result = database.probe(sql)
        except ValueError as error:
            raise RuntimeError('MAC-SQL column sampling SQL failed before inference') from error
        if not result.complete:
            raise IncompleteResultError('Incomplete MAC-SQL column sample')
        samples[table][column] = format_examples([row[0] for row in result.rows], kind)
    return samples


def recover_examples(iterator, kind, *, max_rows):
    """Extract native examples from the ordered pages of a settled sample job."""
    retained = []
    null_seen = False
    count = 0
    for count, row in enumerate(iterator, 1):
        if count > max_rows:
            raise IncompleteResultError('Saved MAC-SQL sample exceeded recovery row limit')
        value = row[0]
        if kind in _NUMERIC:
            retained.append(value)
            if count == 11:
                return ''
        elif value is None:
            null_seen = True
        elif str(value).strip():
            if kind == 'STRING' and not format_examples([value], kind):
                return ''
            if len(retained) < (1 if kind in _DATE_BEARING else 6):
                retained.append(value)
        if kind in _DATE_BEARING and retained and null_seen:
            return format_examples([None, *retained], kind)
    if count != iterator.total_rows:
        raise IncompleteResultError('Saved MAC-SQL sample pages are incomplete')
    return format_examples(([None] if null_seen else []) + retained, kind)
