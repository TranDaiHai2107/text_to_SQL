"""Offline execution preparation only; no BigQuery or LLM calls."""
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.bigquery_client import BigQueryClient
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.metadata import schema_records_from_manifest
from ehrqa.clinsql.result_artifacts import ResultArtifactStore
from ehrqa.clinsql.execution_errors import BudgetExceeded, SecurityRejected
from ehrqa.clinsql.proposed import PipelineDatabase
from ehrqa.cli.bigquery_sql_smoke import smoke_cases
from ehrqa.text2sql.interfaces import DryRun, Execution
from ehrqa.text2sql.logging import MeteredDatabase, RunLog


@pytest.mark.parametrize('total', [0, 99_999, 100_000, 100_001, 287_504])
def test_probe_summary_uses_completed_row_count_without_iterating(total):
    class MetadataOnly:
        total_rows = total

        def __iter__(self):
            pytest.fail('Presence reads must not iterate rows')

    class Client:
        def execute(self, sql, **kwargs):
            assert kwargs['presence_only'] and kwargs['max_rows'] == 1
            job = SimpleNamespace(job_id='probe', total_bytes_billed=10, total_bytes_processed=9)
            import time
            return BigQueryClient._presence(job, MetadataOnly(), time.monotonic())

    adapter = BigQueryAdapter(Client(), [], Limits(20, max_rows=100_000, allow_data_execution=True),
                              allowed_datasets=('project.dataset',))
    log = RunLog('case', 'sde_sql')
    class BudgetedStub:
        def probe_presence(self, sql):
            return adapter.probe_presence(sql, max_bytes_billed=20, job_id='probe')

    result = MeteredDatabase(BudgetedStub(), log).probe_presence('SELECT 1')
    assert result.has_rows is (total > 0)
    assert log.events[-1]['total_rows'] == total and log.events[-1]['summary_only']
    assert 'rows' not in log.events[-1]


@pytest.mark.parametrize('total', [99_999, 100_000, 100_001])
def test_final_result_completeness_checks_total_after_all_pages(total):
    class Client:
        def dry_run(self, sql, **kwargs):
            return 1

        def execute(self, sql, **kwargs):
            assert kwargs['max_rows'] == 100_001 and 'presence_only' not in kwargs
            return {'columns': ['n'], 'total_rows': total,
                    'rows': [(i,) for i in range(total)]}

    adapter = BigQueryAdapter(Client(), [], Limits(20, max_rows=100_000, allow_data_execution=True),
                              allowed_datasets=('project.dataset',))
    result = adapter.execute('SELECT 1')
    assert len(result.rows) == min(total, 100_000)
    assert result.complete is (total <= 100_000)


def test_real_transport_consumes_all_result_pages(monkeypatch):
    from ehrqa.clinsql import bigquery_client as module
    from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
    from itertools import chain

    approval = object.__new__(BenchmarkExecutionApproval)
    monkeypatch.setattr(BenchmarkExecutionApproval, 'authorize', lambda self, **kwargs: None)
    monkeypatch.setattr(module, 'verify_reader_adc', lambda: None)
    monkeypatch.setattr(module, 'verify_reader_credentials', lambda creds: None)
    bigquery = ModuleType('google.cloud.bigquery')
    bigquery.QueryJobConfig = SimpleNamespace
    cloud = ModuleType('google.cloud')
    cloud.bigquery = bigquery
    monkeypatch.setitem(sys.modules, 'google.cloud', cloud)

    class PageIterator:
        total_rows = 3
        schema = (SimpleNamespace(name='v', field_type='INT64'),)

        def __iter__(self):
            return chain([{'v': 1}, {'v': 2}], [{'v': 3}])

    def result(**kwargs):
        assert kwargs['max_results'] in (0, 4)
        return PageIterator()

    job = SimpleNamespace(result=result, job_id='test', total_bytes_billed=10, total_bytes_processed=8)
    config = BigQueryConfig('project', 'hosp', 'icu', 'US', 'project')
    client = BigQueryClient(config, client=SimpleNamespace(query=lambda *args, **kwargs: job),
                            allow_data_execution=True, schema_manifest={}, execution_approval=approval)
    monkeypatch.setattr(client, '_validate_data_sql', lambda sql: None)
    monkeypatch.setattr(client, 'dry_run', lambda *args, **kwargs: 8)
    options = dict(max_bytes_billed=10, timeout_seconds=30, max_rows=4, case_id='test')
    assert client.execute('SELECT 1', **options)['rows'] == [(1,), (2,), (3,)]
    assert client.execute('SELECT 1', **options, presence_only=True).total_rows == 3


def test_manifest_guard_rejects_mutation_script_and_external():
    class Client:
        def dry_run(self, sql, **kwargs): return 0
    adapter = BigQueryAdapter(Client(), [], Limits(10),
                              allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    rejected = [
        'DELETE FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients` WHERE TRUE',
        'SELECT 1; SELECT 2',
        'CREATE TABLE `kltn-text-to-sql.mimiciv_3_1_hosp.x` AS SELECT 1',
        "SELECT * FROM EXTERNAL_QUERY('x', 'SELECT 1')",
        "SELECT `kltn-text-to-sql.mimiciv_3_1_hosp.remote_fn`(1)",
        'SELECT * FROM `other.dataset.table`',
    ]
    for sql in rejected:
        with pytest.raises(SecurityRejected): adapter.dry_run(sql)


def test_guard_accepts_cte_only_with_manifest_tables():
    class Client:
        def dry_run(self, sql, **kwargs): return 0
    adapter = BigQueryAdapter(
        Client(), [{'dataset': 'mimiciv_3_1_hosp', 'table': 'patients'}], Limits(10),
        allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    valid = ('WITH p AS (SELECT subject_id FROM '
             '`kltn-text-to-sql.mimiciv_3_1_hosp.patients`) SELECT COUNT(*) FROM p')
    assert adapter.dry_run(valid).estimated_bytes == 0
    with pytest.raises(SecurityRejected, match='manifest'):
        adapter.dry_run('SELECT * FROM `kltn-text-to-sql.mimiciv_3_1_hosp.unknown`')


def test_bytes_cap_permission_and_no_patient_rows_in_log(tmp_path):
    class Client:
        def dry_run(self, sql, **kwargs): return 101
        def execute(self, sql, **kwargs):
            return {'columns': ['n'], 'column_types': ['INT64'], 'rows': [(42,)], 'total_rows': 1,
                    'job_id': 'fake-job', 'bytes_processed': 101, 'bytes_billed': 101,
                    'latency_seconds': 0.1}
    sql = 'SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`'
    records = [{'dataset': 'mimiciv_3_1_hosp', 'table': 'patients'}]
    blocked = BigQueryAdapter(Client(), records, Limits(100, allow_data_execution=True),
                              allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    with pytest.raises(BudgetExceeded, match='bytes-billed cap'): blocked.execute(sql)
    disabled = BigQueryAdapter(Client(), records, Limits(200),
                               allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    with pytest.raises(PermissionError): disabled.execute(sql)
    enabled = BigQueryAdapter(Client(), records, Limits(200, allow_data_execution=True),
                              allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    log = RunLog('q1', 'mock')
    with pytest.raises(PermissionError, match='synthetic mock'):
        MeteredDatabase(enabled, log, capture_rows=True)
    result = MeteredDatabase(enabled, log).execute(sql)
    assert result.columns == ('n',) and result.column_types == ('INT64',)
    assert result.job_id == 'fake-job' and result.rows == ((42,),)
    saved = log.save(tmp_path / 'run.json').read_text()
    assert 'fake-job' in saved and '"rows": null' in saved and '"42"' not in saved


def test_restricted_result_artifact_round_trip_synthetic_only(tmp_path):
    root = tmp_path / 'private'
    result = Execution(('n',), ((42,),), True, column_types=('INT64',), job_id='fake-job')
    with pytest.raises(PermissionError): ResultArtifactStore(root).save('q1', result)
    store = ResultArtifactStore(root, verify_private_acl=lambda _: True)
    record = store.save('q1', result)
    assert 'rows' not in record and store.load('q1', expected_sha256=record['sha256']).rows == ((42,),)
    with pytest.raises(FileExistsError): store.save('q1', result)
    with pytest.raises(ValueError, match='hash mismatch'):
        store.load('q1', expected_sha256='0' * 64)


def test_smoke_cases_use_validation_gold_without_changing_source():
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp', 'mimiciv_3_1_icu',
                            'US', 'kltn-text-to-sql')
    from pathlib import Path
    root = Path('external/clinsql_official')
    cases = smoke_cases(config, root)
    assert len(cases) == 5 and cases[0]['sql'] == 'SELECT 1 AS smoke_constant'
    original = (root / 'data/splits/validation/Patient_Demographics_and_Admissions'
                / 'easy_level_queries/043/sql_043.sql').read_text(encoding='utf-8')
    assert 'physionet-data' in original and 'physionet-data' not in cases[-1]['sql']
    assert 'APPROX_QUANTILES' in cases[-1]['sql']


def test_transport_timeout_cancels_job_and_permission_error_propagates(monkeypatch):
    class QueryJobConfig:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    module = ModuleType('google.cloud.bigquery')
    module.QueryJobConfig = QueryJobConfig
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', module)
    class Job:
        total_bytes_processed = 1
        def __init__(self): self.cancelled = False
        def result(self, **kwargs):
            assert kwargs['timeout'] == 2
            raise TimeoutError('mock deadline')
        def cancel(self): self.cancelled = True
    job = Job()
    class Client:
        def __init__(self): self.deny = False; self.configs = []
        def query(self, sql, *, job_config, **kwargs):
            if self.deny: raise PermissionError('mock denied')
            self.configs.append(job_config)
            return job
    raw = Client()
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp', 'mimiciv_3_1_icu',
                            'US', 'kltn-text-to-sql')
    from ehrqa.clinsql.execution_control import ExecutionApproval
    from datetime import datetime, timedelta, timezone
    import hashlib
    manifest = json.loads(open('data/schema/manifests/mimiciv_3_1_20261112T143303Z.json', encoding='utf-8').read())
    sql = 'SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`'
    now = datetime.now(timezone.utc)
    approval = ExecutionApproval(
        'synthetic-test', 'test approver', 'test authority', 'test org policy evidence',
        'READ_ONLY_LIKELY_WITH_APPROVED_RISK', True, now - timedelta(minutes=1),
        now + timedelta(minutes=1),
        'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com',
        config.project_id, config.allowed_datasets, config.location, manifest['sha256'],
        'phase_a_smoke', {'hosp_patients_count': hashlib.sha256(sql.encode()).hexdigest()},
        {'hosp_patients_count': 10}, 2, 1, 'synthetic storage policy')
    monkeypatch.setattr('ehrqa.clinsql.bigquery_client.verify_reader_adc', lambda: None)
    monkeypatch.setattr('ehrqa.clinsql.bigquery_client.verify_reader_credentials', lambda _: None)
    transport = BigQueryClient(config, client=raw, allow_data_execution=True,
                               schema_manifest=manifest, execution_approval=approval)
    with pytest.raises(TimeoutError):
        transport.execute(sql, max_bytes_billed=10, timeout_seconds=2, max_rows=1,
                          case_id='hosp_patients_count')
    assert job.cancelled
    assert raw.configs[0].dry_run is True
    assert raw.configs[1].maximum_bytes_billed == 10
    assert raw.configs[1].use_query_cache is False
    raw.deny = True
    with pytest.raises(PermissionError): transport.dry_run(sql, timeout_seconds=2)


def test_pipeline_keeps_column_names_and_types_from_executor():
    class Adapter:
        def schema_metadata(self):
            return [{'table': 'patients', 'dataset': 'mimiciv_3_1_hosp',
                     'ddl': 'CREATE TABLE `kltn-text-to-sql.mimiciv_3_1_hosp.patients` (`subject_id` INT64)',
                     'description_en': 'patients'}]
        def dry_run(self, sql):
            return DryRun(0, True)
        def execute(self, sql):
            return Execution(('n',), ((1,),), True, column_types=('INT64',))
    db = PipelineDatabase(Adapter())
    result = db.execute('SELECT COUNT(subject_id) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`')
    assert result.columns == ['n'] and result.column_types == ('INT64',)


def test_constant_smoke_is_exact_and_does_not_enable_general_execution(monkeypatch):
    import google.auth
    from google.auth import impersonated_credentials
    class FakeCredentials:
        service_account_email = 'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com'
    monkeypatch.setattr(impersonated_credentials, 'Credentials', FakeCredentials)
    monkeypatch.setattr(google.auth, 'default', lambda: (FakeCredentials(), None))
    monkeypatch.delenv('GOOGLE_APPLICATION_CREDENTIALS', raising=False)
    class QueryJobConfig:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    module = ModuleType('google.cloud.bigquery')
    module.QueryJobConfig = QueryJobConfig
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', module)
    class Job:
        total_bytes_processed = 0
        total_bytes_billed = 0
        job_id = 'constant-only-job'
        schema = None
        def result(self, **kwargs):
            class Iterator:
                schema = [type('Field', (), {'name': 'smoke_constant'})()]
                def __iter__(self):
                    return iter([type('Row', (), {'values': lambda self: (1,)})()])
            return Iterator()
    class Client:
        def __init__(self):
            self.calls = []
            self._credentials = FakeCredentials()
        def query(self, sql, **kwargs):
            self.calls.append((sql, kwargs['job_config']))
            return Job()
    raw = Client()
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp', 'mimiciv_3_1_icu',
                            'US', 'kltn-text-to-sql')
    transport = BigQueryClient(config, client=raw)
    output = transport.execute_constant_smoke()
    assert output['result'] == 1 and output['job_id'] == 'constant-only-job'
    assert [sql for sql, _ in raw.calls] == ['SELECT 1 AS smoke_constant'] * 2
    assert raw.calls[0][1].dry_run and raw.calls[1][1].maximum_bytes_billed == 10_485_760
    with pytest.raises(PermissionError):
        transport.execute('SELECT 1', max_bytes_billed=10_485_760,
                          timeout_seconds=15, max_rows=2)
    raw._credentials = object()
    with pytest.raises(PermissionError, match='Query client'):
        transport.execute_constant_smoke()
    raw._credentials = FakeCredentials()
    monkeypatch.setattr(google.auth, 'default', lambda: (object(), None))
    with pytest.raises(PermissionError): transport.execute_constant_smoke()
    assert len(raw.calls) == 2
