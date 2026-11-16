"""One pinned, approval-closed BigQuery backend for all four CLINSQL methods."""
from __future__ import annotations

from .bigquery_adapter import BigQueryAdapter
from .bigquery_client import BigQueryClient
from .config import BigQueryConfig
from .execution_budget import BudgetedDatabase, PersistentSQLBudgetLedger
from .execution_modes import BenchmarkExecutionConfig
from .metadata import schema_records_from_manifest, verify_schema_manifest
from .schema_index import SchemaIndex
from .benchmark_approval import BenchmarkExecutionApproval


def make_benchmark_database(config: BigQueryConfig, manifest: dict,
                            schema_index: SchemaIndex, execution: BenchmarkExecutionConfig,
                            *, case_id: str, client=None,
                            ledger: PersistentSQLBudgetLedger | None = None,
                            approval: BenchmarkExecutionApproval | None = None,
                            budget_scope: str | None = None, pinned_reader=False):
    """Build a common dry-run backend; patient execution needs a separate Phase B gate.

    This factory never accepts the Phase A approval object and never enables
    data execution. The injected client permits offline transport tests.
    """
    verify_schema_manifest(manifest)
    if (manifest['project_id'] != config.project_id or
        manifest['location'].upper() != config.location.upper() or
        manifest['datasets'] != {'hosp': config.hosp_dataset, 'icu': config.icu_dataset}):
        raise ValueError('Benchmark database configuration differs from pinned manifest')
    if schema_index.index['schema_sha256'] != manifest['sha256']:
        raise ValueError('Schema index differs from benchmark manifest')
    if approval is not None:
        if not isinstance(approval, BenchmarkExecutionApproval):
            raise PermissionError('Phase A approval cannot authorize benchmark execution')
        if case_id not in approval.case_ids or approval.manifest_sha256 != manifest['sha256']:
            raise PermissionError('Approval does not match benchmark case/manifest')
    transport = BigQueryClient(config, client=client, allow_data_execution=approval is not None,
                               schema_manifest=manifest, execution_approval=approval,
                               pinned_reader=pinned_reader)
    adapter = BigQueryAdapter(transport, schema_records_from_manifest(manifest),
                              execution.limits(case_id=case_id,
                                               allow_data_execution=approval is not None),
                              allowed_datasets=config.allowed_datasets)
    if ledger is None:
        return adapter
    return BudgetedDatabase(adapter, ledger, question_id=budget_scope or case_id,
                            max_bytes_billed=execution.max_bytes_billed)
