"""Bounded read-only BigQuery adapter; no credentials or network at import time."""
from __future__ import annotations

from dataclasses import dataclass
import re

from sqlglot import exp, parse

from .interfaces import DryRun, Execution


@dataclass(frozen=True)
class Limits:
    max_bytes_billed: int
    timeout_seconds: int = 30
    max_rows: int = 100
    allow_data_execution: bool = False

    def __post_init__(self):
        if min(self.max_bytes_billed, self.timeout_seconds, self.max_rows) <= 0:
            raise ValueError('Positive query limits required')


class BigQueryAdapter:
    def __init__(self, client, schema_records: list[dict], limits: Limits, *, allowed_datasets: tuple[str, ...]):
        if not allowed_datasets:
            raise ValueError('Explicit dataset allowlist required')
        self.client = client
        self.records = schema_records
        self.limits = limits
        self.allowed_datasets = allowed_datasets

    def schema_metadata(self) -> list[dict]:
        return self.records

    def _validate(self, sql: str):
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError('Missing SQL')
        statements = [s for s in parse(sql, read='bigquery') if s is not None]
        if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
            raise ValueError('One read-only SELECT/CTE is required')
        tree = statements[0]
        for node in tree.walk():
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)):
                raise ValueError('Data-changing SQL is prohibited')
        for table in tree.find_all(exp.Table):
            catalog = table.catalog
            db = table.db
            if not catalog or not db or f'{catalog}.{db}' not in self.allowed_datasets:
                raise ValueError('SQL references a table outside the approved BigQuery datasets')
        if re.search(r'(?i)\b(EXTERNAL_QUERY|EXPORT_DATA|REMOTE_FUNCTION)\b', sql):
            raise ValueError('External data access is prohibited')

    def dry_run(self, sql: str) -> DryRun:
        self._validate(sql)
        try:
            estimate = self.client.dry_run(sql, timeout_seconds=self.limits.timeout_seconds)
        except (PermissionError, ConnectionError, TimeoutError):
            raise
        except Exception:
            raise ValueError('BigQuery dry-run SQL error; details withheld') from None
        if estimate > self.limits.max_bytes_billed:
            raise ValueError('Dry run exceeds bytes-billed cap')
        return DryRun(int(estimate), True)

    def _run(self, sql: str) -> Execution:
        if not self.limits.allow_data_execution:
            raise PermissionError('MIMIC data execution is disabled pending authorization and data policy verification')
        self.dry_run(sql)
        try:
            result = self.client.execute(sql, max_bytes_billed=self.limits.max_bytes_billed,
                                         timeout_seconds=self.limits.timeout_seconds,
                                         max_rows=self.limits.max_rows + 1)
        except (PermissionError, ConnectionError, TimeoutError):
            raise
        except Exception:
            raise ValueError('BigQuery execution SQL error; details withheld') from None
        rows = tuple(tuple(row) for row in result['rows'])
        return Execution(tuple(result['columns']), rows[:self.limits.max_rows],
                         len(rows) <= self.limits.max_rows, result.get('bytes_billed'))

    def probe(self, sql: str) -> Execution:
        return self._run(sql)

    def execute(self, sql: str) -> Execution:
        return self._run(sql)
