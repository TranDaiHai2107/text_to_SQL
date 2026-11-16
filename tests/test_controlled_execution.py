"""Synthetic-only approval, guard, and budget checks; no cloud calls."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from types import ModuleType
import sys

import pytest

from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.execution_budget import BudgetedDatabase, SQLBudgetLedger, SQLBudgetLimits
from ehrqa.clinsql.execution_control import ExecutionApproval, PHASE_A_SQL_SHA256
from ehrqa.clinsql.execution_errors import (BudgetExceeded, SecurityRejected,
                                            classify_execution_failure,
                                            translate_bigquery_exception)
from ehrqa.clinsql.execution_modes import SmokeExecutionConfig, BenchmarkExecutionConfig
from ehrqa.clinsql.evaluator import prepare_official_sample
from ehrqa.clinsql.phase_a_retention import expire_phase_a_artifacts
from ehrqa.clinsql.dataset import Question
from ehrqa.cli.bigquery_sql_smoke import smoke_cases
from ehrqa.cli.bigquery_approved_smoke import (claim_case_marker, require_scalar_result,
                                              main as approved_smoke_main)
from ehrqa.text2sql.interfaces import DryRun, Execution


def _scope():
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp',
                            'mimiciv_3_1_icu', 'US', 'kltn-text-to-sql')
    with open('data/schema/manifests/mimiciv_3_1_20261112T143303Z.json', encoding='utf-8') as f:
        manifest = json.load(f)
    sql = 'SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`'
    now = datetime.now(timezone.utc)
    approval = ExecutionApproval(
        'synthetic-test', 'synthetic approver', 'synthetic authority',
        'synthetic org policy clearance', 'READ_ONLY_LIKELY_WITH_APPROVED_RISK', True,
        now - timedelta(minutes=1), now + timedelta(minutes=1),
        'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com',
        config.project_id, config.allowed_datasets, config.location, manifest['sha256'],
        'phase_a_smoke', {'hosp_patients_count': hashlib.sha256(sql.encode()).hexdigest()},
        {'hosp_patients_count': 10_485_760}, 30, 2, 'synthetic storage decision')
    return config, manifest, sql, approval, now


def test_approval_is_exact_scoped_and_expires():
    config, manifest, sql, approval, now = _scope()
    args = dict(case_id='hosp_patients_count', sql=sql, config=config, manifest=manifest,
                max_bytes_billed=10_485_760, timeout_seconds=30, max_rows=2, now=now)
    approval.authorize(**args)
    for changes in ({'sql': sql + ' '}, {'case_id': 'icu_icustays_count'},
                    {'max_bytes_billed': 20_000_000}, {'timeout_seconds': 31},
                    {'max_rows': 3}, {'now': now + timedelta(days=1)}):
        with pytest.raises(PermissionError):
            approval.authorize(**(args | changes))
    with pytest.raises(ValueError, match='risk acceptance'):
        ExecutionApproval(**(approval.__dict__ | {'risk_acknowledged': False}))
    # Risk mode can truthfully leave Organization clearance unknown.
    ExecutionApproval(**(approval.__dict__ | {'organization_policy_clearance_reference': ''}))
    with pytest.raises(ValueError, match='Organization policy evidence'):
        ExecutionApproval(**(approval.__dict__ | {'iam_status': 'VERIFIED_READ_ONLY',
                                                 'organization_policy_clearance_reference': ''}))


def test_locked_phase_a_hashes_match_official_validation_source():
    config, _, _, _, _ = _scope()
    computed = {case['id']: hashlib.sha256(case['sql'].encode()).hexdigest()
                for case in smoke_cases(config, Path('external/clinsql_official'))
                if case['id'] in PHASE_A_SQL_SHA256}
    assert computed == PHASE_A_SQL_SHA256


def test_sql_budget_caps_calls_probes_and_bytes():
    class FakeDatabase:
        def __init__(self): self.calls = 0
        def dry_run(self, sql): return DryRun(3, True)
        def execute(self, sql):
            self.calls += 1
            return Execution(('n',), ((1,),), True, bytes_billed=4)
        probe = execute
    db = FakeDatabase()
    ledger = SQLBudgetLedger(SQLBudgetLimits(2, 1, 20, 20))
    bounded = BudgetedDatabase(db, ledger, question_id='validation/1', max_bytes_billed=10)
    bounded.execute('SELECT 1')
    assert ledger.experiment_bytes == 4
    bounded.probe('SELECT 1')
    assert ledger.experiment_bytes == 8 and db.calls == 2
    with pytest.raises(PermissionError, match='budget'):
        bounded.execute('SELECT 1')
    assert db.calls == 2


def test_phase_a_cli_is_offline_until_completed_approval(monkeypatch, capsys):
    monkeypatch.setenv('BQ_PROJECT_ID', 'kltn-text-to-sql')
    monkeypatch.setenv('BQ_HOSP_DATASET', 'mimiciv_3_1_hosp')
    monkeypatch.setenv('BQ_ICU_DATASET', 'mimiciv_3_1_icu')
    monkeypatch.setenv('BQ_LOCATION', 'US')
    monkeypatch.setenv('BQ_BILLING_PROJECT', 'kltn-text-to-sql')
    arguments = ['--case-id', 'hosp_patients_count', '--manifest',
                 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json']
    assert approved_smoke_main(arguments) == 0
    assert 'PLAN_ONLY' in capsys.readouterr().out
    with pytest.raises(PermissionError, match='approval file'):
        approved_smoke_main(arguments + ['--execute-approved'])
    with pytest.raises(ValueError):
        ExecutionApproval.from_file('docs/PHASE_A_APPROVAL_DRAFT.json')


def test_phase_a_marker_blocks_repeat_even_with_new_approval(tmp_path):
    marker = claim_case_marker(tmp_path, case_id='hosp_patients_count',
                               approval_id='first', approval_sha256='a' * 64,
                               sql_sha256=PHASE_A_SQL_SHA256['hosp_patients_count'])
    assert marker.name == 'phase_a_hosp_patients_count.started'
    assert json.loads(marker.read_text())['approval_id'] == 'first'
    with pytest.raises(FileExistsError):
        claim_case_marker(tmp_path, case_id='hosp_patients_count',
                          approval_id='second', approval_sha256='b' * 64,
                          sql_sha256=PHASE_A_SQL_SHA256['hosp_patients_count'])


def test_phase_a_requires_one_complete_scalar_result():
    require_scalar_result(Execution(('n',), ((1,),), True))
    with pytest.raises(ValueError, match='one scalar'):
        require_scalar_result(Execution(('n',), ((1,), (2,)), False))
    with pytest.raises(ValueError, match='one scalar'):
        require_scalar_result(Execution(('a', 'b'), ((1, 2),), True))


def test_smoke_and_benchmark_row_profiles_do_not_overlap(tmp_path):
    assert SmokeExecutionConfig('hosp_patients_count').limits().max_rows == 1
    with pytest.raises(ValueError, match='one-row smoke'):
        BenchmarkExecutionConfig(10_485_760, 30, 1)
    benchmark = BenchmarkExecutionConfig(10_485_760, 30, 100).limits(case_id='validation/001')
    assert benchmark.max_rows == 100 and not benchmark.allow_data_execution
    incomplete = Execution(('n',), ((1,),), False)
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'question')
    with pytest.raises(ValueError, match='Truncated execution result'):
        prepare_official_sample(tmp_path, tmp_path, question, 'SELECT 1', incomplete)


def test_bigquery_sdk_errors_keep_non_sql_status(monkeypatch):
    classes = {name: type(name, (Exception,), {}) for name in
               ('Forbidden', 'Unauthorized', 'DeadlineExceeded', 'ServiceUnavailable',
                'TooManyRequests', 'InternalServerError', 'BadRequest')}
    package = ModuleType('google.api_core')
    errors = ModuleType('google.api_core.exceptions')
    for name, cls in classes.items():
        setattr(errors, name, cls)
    package.exceptions = errors
    monkeypatch.setitem(sys.modules, 'google.api_core', package)
    monkeypatch.setitem(sys.modules, 'google.api_core.exceptions', errors)
    assert classify_execution_failure(translate_bigquery_exception(classes['Forbidden']()),
                                      stage='execute') == 'PERMISSION_DENIED'
    assert classify_execution_failure(translate_bigquery_exception(classes['DeadlineExceeded']()),
                                      stage='execute') == 'TIMEOUT'
    assert classify_execution_failure(translate_bigquery_exception(classes['ServiceUnavailable']()),
                                      stage='execute') == 'INFRASTRUCTURE_ERROR'
    bytes_error = classes['BadRequest']()
    bytes_error.errors = [{'reason': 'bytesBilledLimitExceeded'}]
    assert classify_execution_failure(translate_bigquery_exception(bytes_error),
                                      stage='execute') == 'BUDGET_EXCEEDED'
    sql_error = classes['BadRequest']()
    sql_error.errors = [{'reason': 'invalidQuery'}]
    assert classify_execution_failure(translate_bigquery_exception(sql_error),
                                      stage='dry_run') == 'SQL_SYNTAX_ERROR'
    assert classify_execution_failure(SecurityRejected('blocked'),
                                      stage='dry_run') == 'SECURITY_REJECTED'
    assert classify_execution_failure(BudgetExceeded('cap'),
                                      stage='dry_run') == 'BUDGET_EXCEEDED'


def test_phase_a_retention_requires_due_date_and_records_real_deletion(tmp_path):
    now = datetime.now(timezone.utc)
    case_id = 'hosp_patients_count'
    artifact_id = 'approved_' + case_id
    artifact = tmp_path / f'{artifact_id}.json'
    artifact.write_text('{"rows":[[1]]}', encoding='utf-8')
    marker = tmp_path / f'phase_a_{case_id}.started'
    marker.write_text('started', encoding='utf-8')
    summary = {'phase': 'phase_a_smoke', 'status': 'COMPLETE', 'case_id': case_id,
               'artifact_id': artifact_id,
               'artifact_sha256': hashlib.sha256(artifact.read_bytes()).hexdigest(),
               'artifact_expires_at_utc': (now + timedelta(days=7)).isoformat()}
    summary_path = tmp_path / f'{artifact_id}.summary.json'
    summary_path.write_text(json.dumps(summary), encoding='utf-8')
    kwargs = {'verify_acl': lambda _: True}
    assert expire_phase_a_artifacts(tmp_path, now=now, **kwargs)[0]['status'] == 'NOT_DUE'
    due = now + timedelta(days=8)
    assert expire_phase_a_artifacts(tmp_path, now=due, **kwargs)[0]['status'] == 'DUE_MANUAL_DELETION'
    assert artifact.exists()
    assert expire_phase_a_artifacts(tmp_path, now=due, delete_expired=True,
                                    **kwargs)[0]['status'] == 'DELETED'
    assert not artifact.exists() and marker.exists()
    assert json.loads(summary_path.read_text())['artifact_deleted_at_utc'] == due.isoformat()
    assert expire_phase_a_artifacts(tmp_path, now=due, delete_expired=True,
                                    **kwargs)[0]['status'] == 'ALREADY_DELETED'
