"""AST-based safety and schema validation for generated MIMIC-IV SQL.

Only one read-only PostgreSQL query is accepted. SQLGlot resolves aliases,
CTEs and nested queries before columns are checked against ``mimic_schema.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlglot import exp, parse, parse_one
from sqlglot.errors import ParseError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import build_scope


BASE_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = BASE_DIR / "mimic_schema.json"

# Functions that can read server files, sleep, make external connections, or
# mutate server/session state even when invoked from SELECT.
DENIED_FUNCTIONS = {
    "dblink",
    "dblink_connect",
    "dblink_connect_u",
    "dblink_disconnect",
    "dblink_exec",
    "lo_export",
    "lo_import",
    "lo_create",
    "lo_unlink",
    "nextval",
    "pg_advisory_lock",
    "pg_advisory_lock_shared",
    "pg_advisory_unlock",
    "pg_advisory_unlock_all",
    "pg_advisory_unlock_shared",
    "pg_cancel_backend",
    "pg_create_restore_point",
    "pg_export_snapshot",
    "pg_ls_archive_statusdir",
    "pg_ls_dir",
    "pg_ls_logdir",
    "pg_ls_waldir",
    "pg_read_binary_file",
    "pg_read_file",
    "pg_reload_conf",
    "pg_rotate_logfile",
    "pg_sleep",
    "pg_stat_file",
    "pg_switch_wal",
    "pg_terminate_backend",
    "pg_try_advisory_lock",
    "pg_try_advisory_lock_shared",
    "pg_notify",
    "set_config",
    "setval",
}


def _load_schema() -> dict[str, dict[str, str]]:
    """Load table/column names from the same DDL documents used by RAG."""
    with SCHEMA_FILE.open(encoding="utf-8") as handle:
        records = json.load(handle)

    schema: dict[str, dict[str, str]] = {}
    for record in records:
        table_name = str(record["table"]).lower()
        ddl = record.get("ddl", "")
        try:
            statement = parse_one(ddl, read="postgres")
        except ParseError as exc:
            raise RuntimeError(f"DDL của bảng {table_name} không parse được: {exc}") from exc

        columns: dict[str, str] = {}
        for column_def in statement.find_all(exp.ColumnDef):
            name = column_def.name.lower()
            kind = column_def.args.get("kind")
            columns[name] = kind.sql(dialect="postgres") if kind else "UNKNOWN"
        if not columns:
            raise RuntimeError(f"Không tìm thấy cột trong DDL của bảng {table_name}")
        schema[table_name] = columns
    return schema


SCHEMA = _load_schema()
VALID_TABLES = frozenset(SCHEMA)
VALID_COLUMNS = {table: frozenset(columns) for table, columns in SCHEMA.items()}


def _function_name(node: exp.Func) -> str:
    if isinstance(node, exp.Anonymous):
        return node.name.lower()
    return node.sql_name().lower()


def _column_pair(node: exp.EQ) -> tuple[tuple[str, str], tuple[str, str]] | None:
    left, right = node.this, node.expression
    if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
        return None
    return ((left.table.lower(), left.name.lower()), (right.table.lower(), right.name.lower()))


def _missing_join_key(
    expression: exp.Expression,
    left_table: str,
    right_table: str,
    column: str,
) -> bool:
    """Return True when two present tables are not equi-joined on ``column``."""
    aliases: dict[str, str] = {}
    present: set[str] = set()
    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        present.add(name)
        aliases[table.alias_or_name.lower()] = name
        aliases[name] = name

    if left_table not in present or right_table not in present:
        return False

    for equality in expression.find_all(exp.EQ):
        pair = _column_pair(equality)
        if not pair:
            continue
        (left_alias, left_col), (right_alias, right_col) = pair
        resolved = {
            (aliases.get(left_alias, left_alias), left_col),
            (aliases.get(right_alias, right_alias), right_col),
        }
        if resolved == {(left_table, column), (right_table, column)}:
            return False
    return True


def _format_error(exc: Exception) -> str:
    return str(exc).splitlines()[0]


def validate_sql_schema(sql: str) -> dict[str, Any]:
    """Validate one PostgreSQL SELECT/CTE query against the MIMIC schema."""
    errors: list[str] = []
    warnings: list[str] = []

    if not sql or not sql.strip():
        return {"valid": False, "errors": ["SQL rỗng."], "warnings": []}

    try:
        statements = [statement for statement in parse(sql, read="postgres") if statement]
    except ParseError as exc:
        return {
            "valid": False,
            "errors": [f"SQL không đúng cú pháp PostgreSQL: {_format_error(exc)}"],
            "warnings": [],
        }

    if len(statements) != 1:
        return {
            "valid": False,
            "errors": ["Chỉ cho phép đúng một câu truy vấn SQL."],
            "warnings": [],
        }

    expression = statements[0]
    if not isinstance(expression, exp.Query):
        return {
            "valid": False,
            "errors": ["Chỉ cho phép truy vấn SELECT hoặc WITH ... SELECT ở chế độ chỉ đọc."],
            "warnings": [],
        }

    if expression.find(exp.Into):
        errors.append("Không cho phép SELECT INTO vì câu lệnh này tạo hoặc ghi bảng.")
    if expression.find(exp.Lock):
        errors.append("Không cho phép SELECT ... FOR UPDATE/SHARE vì truy vấn có thể khóa dữ liệu.")
    for node_type in (exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter):
        if expression.find(node_type):
            errors.append("Truy vấn chứa thao tác thay đổi dữ liệu hoặc cấu trúc.")
            break

    for function in expression.find_all(exp.Func):
        name = _function_name(function)
        if name in DENIED_FUNCTIONS:
            errors.append(f"Không cho phép gọi hàm PostgreSQL '{name}'.")

    cte_names = {cte.alias_or_name.lower() for cte in expression.find_all(exp.CTE)}
    tables_used: set[str] = set()
    for table in expression.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        tables_used.add(name)
        if table.catalog or (table.db and table.db.lower() != "public"):
            errors.append(f"Không cho phép truy cập ngoài schema public: '{table.sql()}'.")
        elif name not in VALID_TABLES:
            errors.append(f"Bảng '{name}' không tồn tại trong schema MIMIC-IV đã cấu hình.")

    if not tables_used:
        errors.append("Truy vấn phải đọc ít nhất một bảng MIMIC-IV.")

    if not errors:
        try:
            qualify(
                expression.copy(),
                dialect="postgres",
                schema=SCHEMA,
                expand_stars=False,
                infer_schema=False,
                validate_qualify_columns=True,
                quote_identifiers=False,
                identify=False,
                allow_partial_qualification=False,
            )
            build_scope(expression)
        except Exception as exc:  # Optimizer exception hierarchy varies by SQLGlot version.
            errors.append(f"Cột hoặc phạm vi truy vấn không hợp lệ: {_format_error(exc)}")

    required_join_keys = (
        ("diagnoses_icd", "d_icd_diagnoses", "icd_code"),
        ("diagnoses_icd", "d_icd_diagnoses", "icd_version"),
        ("procedures_icd", "d_icd_procedures", "icd_code"),
        ("procedures_icd", "d_icd_procedures", "icd_version"),
        ("emar", "emar_detail", "emar_id"),
        ("emar", "emar_detail", "emar_seq"),
    )
    for left_table, right_table, column in required_join_keys:
        if _missing_join_key(expression, left_table, right_table, column):
            errors.append(
                f"JOIN {left_table} với {right_table} phải khớp thêm cột '{column}'."
            )

    return {
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "warnings": warnings,
        "tables": sorted(tables_used),
    }


def get_validator_prompt_hint(validation_result: dict[str, Any]) -> str:
    """Turn validator failures into concise feedback for SQL self-correction."""
    if validation_result.get("valid"):
        return ""
    errors = validation_result.get("errors", [])
    return "SQL chưa hợp lệ:\n" + "\n".join(f"- {error}" for error in errors)


if __name__ == "__main__":
    samples = [
        "SELECT COUNT(*) FROM patients",
        "WITH older AS (SELECT subject_id FROM patients WHERE anchor_age > 65) SELECT COUNT(*) FROM older",
        "SELECT p.nonexistent FROM patients p",
        "SELECT pg_read_file('/etc/passwd') FROM patients LIMIT 1",
    ]
    for sample in samples:
        print(sample)
        print(validate_sql_schema(sample))
