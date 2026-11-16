"""Bounded read-only BigQuery adapter; no credentials or network at import time."""
from __future__ import annotations

from dataclasses import dataclass
import re

from sqlglot import exp, parse

from .interfaces import DryRun, Execution
from .execution_errors import BudgetExceeded, IncompleteResultError, SecurityRejected, translate_bigquery_exception


@dataclass(frozen=True)
class Limits:
    max_bytes_billed: int
    timeout_seconds: int = 30
    max_rows: int = 100
    max_result_bytes: int = 8_388_608
    allow_data_execution: bool = False
    case_id: str | None = None

    def __post_init__(self):
        if min(self.max_bytes_billed, self.timeout_seconds, self.max_rows,
               self.max_result_bytes) <= 0:
            raise ValueError('Positive query limits required')


class BigQueryAdapter:
    def __init__(self, client, schema_records: list[dict], limits: Limits, *, allowed_datasets: tuple[str, ...]):
        if not allowed_datasets:
            raise ValueError('Explicit dataset allowlist required')
        self.client = client
        self.records = schema_records
        self.limits = limits
        self.allowed_datasets = allowed_datasets
        self.allowed_tables = {f"{record['dataset']}.{record['table']}" for record in schema_records}

    def schema_metadata(self) -> list[dict]:
        return self.records

    def _validate(self, sql: str):
        if not isinstance(sql, str) or not sql.strip():
            raise ValueError('Missing SQL')
        try:
            statements = [s for s in parse(sql, read='bigquery') if s is not None]
        except Exception:
            raise ValueError('BigQuery SQL syntax error; details withheld') from None
        if len(statements) != 1 or not isinstance(statements[0], (exp.Select, exp.Union)):
            raise SecurityRejected('One read-only SELECT/CTE is required')
        tree = statements[0]
        cte_names = {cte.alias for cte in tree.find_all(exp.CTE)}
        for node in tree.walk():
            if isinstance(node, (exp.Insert, exp.Update, exp.Delete, exp.Create, exp.Drop, exp.Alter, exp.Command)):
                raise SecurityRejected('Data-changing SQL is prohibited')
            if isinstance(node, exp.Anonymous) and ('.' in node.name or
                    node.name.upper() in {'EXTERNAL_QUERY', 'REMOTE_FUNCTION'}):
                raise SecurityRejected('External or user-defined routines are prohibited')
        for table in tree.find_all(exp.Table):
            catalog = table.catalog
            db = table.db
            if not catalog and not db and table.name in cte_names:
                continue
            if not catalog or not db or f'{catalog}.{db}' not in self.allowed_datasets:
                raise SecurityRejected('SQL references a table outside the approved BigQuery datasets')
            if f'{db}.{table.name}' not in self.allowed_tables:
                raise SecurityRejected('SQL references a table outside the verified schema manifest')
        if re.search(r'(?i)\b(EXTERNAL_QUERY|EXPORT_DATA|REMOTE_FUNCTION)\b', sql):
            raise SecurityRejected('External data access is prohibited')

    def dry_run(self, sql: str) -> DryRun:
        self._validate(sql)
        try:
            estimate = self.client.dry_run(sql, timeout_seconds=self.limits.timeout_seconds)
        except Exception as exc:
            raise translate_bigquery_exception(exc) from None
        if estimate > self.limits.max_bytes_billed:
            raise BudgetExceeded('Dry run exceeds bytes-billed cap',
                                 estimated_bytes=int(estimate),
                                 cap_bytes=self.limits.max_bytes_billed)
        return DryRun(int(estimate), True)

    def _run(self, sql: str, *, max_bytes_billed=None, job_id=None) -> Execution:
        if not self.limits.allow_data_execution:
            raise PermissionError('MIMIC data execution is disabled pending authorization and data policy verification')
        ceiling = self.limits.max_bytes_billed
        if max_bytes_billed is not None and not 0 < max_bytes_billed <= ceiling:
            raise BudgetExceeded('Dynamic cap exceeds approved per-query ceiling')
        self.dry_run(sql)
        try:
            arguments = {'max_bytes_billed': max_bytes_billed or ceiling,
                         'timeout_seconds': self.limits.timeout_seconds,
                         'max_rows': self.limits.max_rows + 1,
                         'max_result_bytes': self.limits.max_result_bytes}
            if self.limits.case_id:
                arguments['case_id'] = self.limits.case_id
            if job_id is not None:
                arguments['job_id'] = job_id
            result = self.client.execute(sql, **arguments)
        except Exception as exc:
            raise translate_bigquery_exception(exc) from None
        rows = tuple(tuple(row) for row in result['rows'])
        total_rows = result.get('total_rows')
        complete = not result.get('result_bytes_exceeded', False) and len(rows) <= self.limits.max_rows and (
            total_rows == len(rows))
        return Execution(tuple(result['columns']), rows[:self.limits.max_rows],
                         complete, result.get('bytes_billed'),
                         tuple(result.get('column_types', ())), result.get('job_id'),
                         result.get('bytes_processed'), result.get('latency_seconds'))

    def probe(self, sql: str, **kwargs) -> Execution:
        return self._run(sql, **kwargs)

    def probe_presence(self, sql, *, max_bytes_billed, job_id):
        if not self.limits.allow_data_execution:
            raise PermissionError('MIMIC data execution is disabled')
        if not 0 < max_bytes_billed <= self.limits.max_bytes_billed:
            raise BudgetExceeded('Dynamic cap exceeds approved per-query ceiling')
        self._validate(sql)
        try:
            return self.client.execute(sql, max_bytes_billed=max_bytes_billed, job_id=job_id,
                                       timeout_seconds=self.limits.timeout_seconds, max_rows=1,
                                       case_id=self.limits.case_id, presence_only=True)
        except Exception as exc:
            if isinstance(exc, IncompleteResultError):
                raise
            raise translate_bigquery_exception(exc) from None

    def saved_probe_presence(self, sql, job_id, *, max_bytes_billed):
        return self.client.saved_probe_presence(sql, job_id, case_id=self.limits.case_id,
                                                max_bytes_billed=max_bytes_billed,
                                                timeout_seconds=self.limits.timeout_seconds)

    def saved_sample(self, sql, job_id, *, cap, billed, kind):
        from .baselines.mac_sampling import recover_examples
        job = self.client._saved_probe_job(sql, job_id, case_id=self.limits.case_id,
                                           max_bytes_billed=cap, timeout_seconds=self.limits.timeout_seconds)
        if job.total_bytes_billed != billed:
            raise ValueError('Saved sample billed bytes differ from ledger')
        result = job.result(timeout=self.limits.timeout_seconds, page_size=10_000,
                            max_results=self.limits.max_rows + 1)
        return recover_examples(result, kind, max_rows=self.limits.max_rows)

    def execute(self, sql: str, **kwargs) -> Execution:
        return self._run(sql, **kwargs)
