"""SDE native subquery decomposition with a narrow BigQuery dialect adapter."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import sqlglot


ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = ROOT / 'external/sde_sql_official/src'
SOURCE_FILE = SOURCE_ROOT / 'reader/core_function.py'
LOCK = ROOT / 'PAPER_SOURCE_LOCK.json'


def _native_generate_result():
    expected = json.loads(LOCK.read_text(encoding='utf-8'))['sde_sql']['key_files'][
        'src/reader/core_function.py']
    if hashlib.sha256(SOURCE_FILE.read_bytes()).hexdigest() != expected:
        raise ValueError('SDE native subquery source differs from locked hash')
    path = str(SOURCE_ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)
    module = importlib.import_module('reader.core_function')
    if Path(module.__file__).resolve() != SOURCE_FILE.resolve():
        raise ImportError('SDE native decomposition resolved outside the locked checkout')
    return module.generate_result


def native_get_subsqls(sql: str) -> list[str]:
    """Mirror refine_new.get_subsqls without importing that module's API code."""
    generate_result = _native_generate_result()
    subsql_dict, _, _, _, _ = generate_result(sql.replace('`', '"'))
    subsqls = [piece.replace('"', '`') for group in subsql_dict.values()
               for piece in group.values() if ' * ' not in piece]
    return sorted(subsqls, key=lambda piece: len(piece.split('FROM')[0].strip()))


def bigquery_get_subsqls(sql: str) -> list[str]:
    """Transpile only at the SQLite/BigQuery boundary; fail for multi-statements."""
    statements = [part for part in sqlglot.parse(sql, read='bigquery') if part is not None]
    if len(statements) != 1:
        raise ValueError('SDE diagnosis requires one SQL statement')
    sqlite_sql = statements[0].sql(dialect='sqlite', unsupported_level=sqlglot.ErrorLevel.RAISE)
    pieces = native_get_subsqls(sqlite_sql)
    output = []
    for piece in pieces:
        queries = sqlglot.transpile(piece, read='sqlite', write='bigquery',
                                    unsupported_level=sqlglot.ErrorLevel.RAISE)
        if len(queries) != 1:
            raise ValueError('SDE diagnosis probe must contain one statement')
        output.append(queries[0])
    return output


def timed_bigquery_get_subsqls(sql: str) -> list[str]:
    """Run native AST decomposition under its 60-second deadline."""
    worker = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); "
        "from ehrqa.clinsql.baselines.sde_subqueries import bigquery_get_subsqls; "
        "print(json.dumps(bigquery_get_subsqls(sys.stdin.read())))"
    )
    try:
        result = subprocess.run([sys.executable, '-X', 'utf8', '-c', worker, str(ROOT / 'src')],
                                input=sql, capture_output=True, encoding='utf-8',
                                timeout=60, check=True)
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        raise ValueError('SDE native diagnosis decomposition failed or timed out') from None
    return json.loads(result.stdout)
