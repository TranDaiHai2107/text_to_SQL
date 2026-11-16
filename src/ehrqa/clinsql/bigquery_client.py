"""Lazy BigQuery SDK transport. No connection occurs at import time."""
from __future__ import annotations

import re
import time
import json
import os

from .config import BigQueryConfig
from .metadata import (build_schema_manifest, information_schema_sql,
                       schema_records_from_manifest)
from .execution_control import (ExecutionApproval, verify_reader_adc,
                                verify_reader_credentials)
from .execution_errors import BudgetExceeded
from .benchmark_approval import BenchmarkExecutionApproval
from .result_artifacts import _encode
from ehrqa.text2sql.interfaces import ProbePresence

METADATA_MAX_BYTES_BILLED = 10_485_760  # BigQuery on-demand minimum per INFORMATION_SCHEMA query.
CONSTANT_SMOKE_SQL = 'SELECT 1 AS smoke_constant'


def discover_dataset_location(project_id: str, hosp_dataset: str, icu_dataset: str,
                              billing_project: str, *, client=None) -> str:
    """Read two dataset metadata objects, without creating a query job."""
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+', value)
           for value in (project_id, hosp_dataset, icu_dataset, billing_project)):
        raise ValueError('Invalid BigQuery project/dataset identifier')
    if client is None:
        from google.cloud import bigquery
        client = bigquery.Client(project=billing_project)
    locations = []
    for dataset in (hosp_dataset, icu_dataset):
        metadata = client.get_dataset(f'{project_id}.{dataset}')
        locations.append(metadata.location)
    if not locations[0] or locations[0].upper() != locations[1].upper():
        raise ValueError('HOSP and ICU BigQuery datasets must share one verified location')
    return locations[0]


class BigQueryClient:
    def __init__(self, config: BigQueryConfig, *, client=None, allow_data_execution: bool = False,
                 schema_manifest: dict | None = None,
                 execution_approval: ExecutionApproval | BenchmarkExecutionApproval | None = None,
                 pinned_reader=False):
        self.config = config
        self.allow_data_execution = allow_data_execution
        self.schema_manifest = schema_manifest
        self.execution_approval = execution_approval
        if client is None:
            from google.cloud import bigquery
            client = bigquery.Client(project=config.billing_project, location=config.location)
        self.client = client
        self.pinned_reader = pinned_reader

    def _verify_reader(self):
        if not self.pinned_reader:
            verify_reader_adc()
        if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
            raise PermissionError('Expected reader ADC impersonation is not active')
        verify_reader_credentials(getattr(self.client, '_credentials', None))

    def _validate_data_sql(self, sql: str) -> None:
        from .bigquery_adapter import BigQueryAdapter, Limits
        records = schema_records_from_manifest(self.schema_manifest) if self.schema_manifest else []
        BigQueryAdapter(self, records, Limits(1),
                        allowed_datasets=self.config.allowed_datasets)._validate(sql)

    def dry_run(self, sql: str, *, timeout_seconds: int) -> int:
        self._validate_data_sql(sql)
        if self.execution_approval is not None:
            self._verify_reader()
        from google.cloud import bigquery
        job = self.client.query(sql, location=self.config.location, timeout=timeout_seconds,
                                job_config=bigquery.QueryJobConfig(
                                    dry_run=True, use_query_cache=False, use_legacy_sql=False))
        return int(job.total_bytes_processed or 0)

    def execute(self, sql: str, *, max_bytes_billed: int, timeout_seconds: int,
                max_rows: int, case_id: str | None = None,
                max_result_bytes: int = 8_388_608, job_id: str | None = None,
                presence_only: bool = False) -> dict | ProbePresence:
        self._validate_data_sql(sql)
        if not self.allow_data_execution:
            raise PermissionError('BigQuery data execution is disabled by the transport')
        if self.execution_approval is None or self.schema_manifest is None or not case_id:
            raise PermissionError('A scoped execution approval and case ID are required')
        self._verify_reader()
        approval_args = dict(case_id=case_id, sql=sql, config=self.config,
                             manifest=self.schema_manifest,
                             max_bytes_billed=max_bytes_billed,
                             timeout_seconds=timeout_seconds, max_rows=max_rows)
        if isinstance(self.execution_approval, BenchmarkExecutionApproval):
            approval_args['max_result_bytes'] = max_result_bytes
        self.execution_approval.authorize(**approval_args)
        if min(max_bytes_billed, timeout_seconds, max_rows, max_result_bytes) <= 0:
            raise ValueError('Positive query limits required')
        if self.dry_run(sql, timeout_seconds=timeout_seconds) > max_bytes_billed:
            raise BudgetExceeded('Dry run exceeds bytes-billed cap')
        from google.cloud import bigquery
        started = time.monotonic()
        options = {'job_id': job_id, 'job_retry': None} if job_id is not None else {}
        job = self.client.query(sql, location=self.config.location, timeout=timeout_seconds, **options,
                                job_config=bigquery.QueryJobConfig(
                                    maximum_bytes_billed=max_bytes_billed,
                                    use_legacy_sql=False, use_query_cache=False))
        try:
            iterator = job.result(timeout=timeout_seconds, max_results=0 if presence_only else max_rows)
            if presence_only:
                return self._presence(job, iterator, started)
            rows, result_bytes, exceeded = [], 0, False
            for row in iterator:
                values = tuple(row.values())
                result_bytes += len(json.dumps([_encode(v) for v in values],
                                               ensure_ascii=False, allow_nan=False).encode('utf-8'))
                if result_bytes > max_result_bytes:
                    exceeded = True
                    break
                rows.append(values)
        except Exception:
            job.cancel()
            raise
        schema = iterator.schema or job.schema or ()
        return {'columns': [field.name for field in schema],
                'column_types': [field.field_type for field in schema], 'rows': rows,
                'total_rows': getattr(iterator, 'total_rows', None),
                'result_bytes_exceeded': exceeded, 'result_bytes_observed': result_bytes,
                'bytes_billed': getattr(job, 'total_bytes_billed', None),
                'bytes_processed': getattr(job, 'total_bytes_processed', None),
                'job_id': getattr(job, 'job_id', None),
                'latency_seconds': time.monotonic() - started}

    @staticmethod
    def _presence(job, iterator, started):
        total_rows = iterator.total_rows
        if not isinstance(total_rows, int) or total_rows < 0:
            from .execution_errors import IncompleteResultError
            raise IncompleteResultError('BigQuery did not report the completed probe row count')
        return ProbePresence(total_rows, job.job_id, job.total_bytes_billed,
                             job.total_bytes_processed, time.monotonic() - started)

    def saved_probe_presence(self, sql, job_id, *, case_id, max_bytes_billed, timeout_seconds):
        started = time.monotonic()
        job = self._saved_probe_job(sql, job_id, case_id=case_id, max_bytes_billed=max_bytes_billed,
                                   timeout_seconds=timeout_seconds)
        return self._presence(job, job.result(timeout=timeout_seconds, max_results=0), started)

    def _saved_probe_job(self, sql, job_id, *, case_id, max_bytes_billed, timeout_seconds):
        self._validate_data_sql(sql)
        if not self.allow_data_execution or not isinstance(self.execution_approval, BenchmarkExecutionApproval):
            raise PermissionError('Probe recovery requires a scoped benchmark approval')
        self.execution_approval.authorize(case_id=case_id, sql=sql, config=self.config,
                                          manifest=self.schema_manifest, max_bytes_billed=max_bytes_billed,
                                          timeout_seconds=timeout_seconds, max_rows=1)
        self._verify_reader()
        job = self.client.get_job(job_id, project=self.config.billing_project,
                                  location=self.config.location, timeout=timeout_seconds)
        if (job.query != sql or job.state != 'DONE' or job.error_result or
                job.total_bytes_billed is None or job.total_bytes_billed > max_bytes_billed):
            raise ValueError('Saved probe job does not match its reservation')
        return job

    def execute_constant_smoke(self) -> dict:
        """One exact table-free statement, with no change to the data-execution gate."""
        from google.cloud import bigquery

        verify_reader_adc()
        verify_reader_credentials(getattr(self.client, '_credentials', None))
        self._validate_data_sql(CONSTANT_SMOKE_SQL)
        estimate = self.dry_run(CONSTANT_SMOKE_SQL, timeout_seconds=15)
        if estimate != 0:
            raise ValueError('Constant smoke unexpectedly scans data')
        started = time.monotonic()
        job = self.client.query(
            CONSTANT_SMOKE_SQL, location=self.config.location, timeout=15,
            job_config=bigquery.QueryJobConfig(use_legacy_sql=False,
                                               maximum_bytes_billed=10_485_760))
        try:
            iterator = job.result(timeout=15, max_results=2)
            rows = [tuple(row.values()) for row in iterator]
        except Exception:
            job.cancel()
            raise
        schema = iterator.schema or job.schema or ()
        names = [field.name for field in schema]
        if names != ['smoke_constant'] or rows != [(1,)]:
            raise ValueError('Constant smoke returned an unexpected result')
        return {'status': 'PASS', 'sql': CONSTANT_SMOKE_SQL, 'result': 1,
                'column': names[0], 'job_id': job.job_id,
                'bytes_billed': getattr(job, 'total_bytes_billed', None),
                'bytes_processed': getattr(job, 'total_bytes_processed', None),
                'latency_seconds': time.monotonic() - started}

    def load_schema_manifest(self, *, timeout_seconds: int = 30) -> dict:
        """Four dataset INFORMATION_SCHEMA reads. Explicit call; never patient rows."""
        from google.cloud import bigquery
        tables, columns = {}, {}
        for role, dataset in (('hosp', self.config.hosp_dataset), ('icu', self.config.icu_dataset)):
            for view, target in (('TABLES', tables), ('COLUMNS', columns)):
                sql = information_schema_sql(self.config.project_id, dataset, view)
                job = self.client.query(sql, location=self.config.location, timeout=timeout_seconds,
                                        job_config=bigquery.QueryJobConfig(
                                            use_legacy_sql=False,
                                            maximum_bytes_billed=METADATA_MAX_BYTES_BILLED))
                target[role] = [dict(row.items()) for row in job.result(timeout=timeout_seconds)]
        return build_schema_manifest(self.config, tables, columns)

    def load_verified_schema_records(self) -> list[dict]:
        return schema_records_from_manifest(self.load_schema_manifest())
