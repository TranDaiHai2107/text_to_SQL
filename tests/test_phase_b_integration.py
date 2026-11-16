"""Phase B checks use official validation questions with synthetic transports only."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.baselines.sde_sql import _most_consistent
from ehrqa.clinsql.benchmark_backend import make_benchmark_database
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.config import ExperimentConfig
from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.dataset import Question
from ehrqa.clinsql.evaluator import prepare_saved_run_sample
from ehrqa.clinsql.execution_budget import (BudgetedDatabase, PersistentSQLBudgetLedger,
                                              SQLBudgetLimits)
from ehrqa.clinsql.execution_modes import BenchmarkExecutionConfig
from ehrqa.clinsql.metadata import schema_records_from_manifest
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.result_artifacts import ResultArtifactStore
from ehrqa.clinsql.runner import load_validation_checkpoint, run_validation_one
from ehrqa.clinsql.schema_index import SchemaIndex, build_schema_index, save_schema_index
from ehrqa.text2sql.interfaces import DryRun, Execution


MANIFEST = Path('data/schema/manifests/mimiciv_3_1_20261112T143303Z.json')
INDEX = Path('data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json')


def scope():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    return manifest, SchemaIndex.load(INDEX, manifest)


def test_schema_index_pins_all_31_real_metadata_tables(tmp_path):
    manifest, index = scope()
    assert len(index.schema_records()) == 31
    assert index.index == build_schema_index(manifest)
    assert {e['table'] for e in index.retrieve('icustays stay_id', limit=4)} >= {'icustays'}
    assert all('gold' not in row for row in index.schema_records())
    with pytest.raises(FileExistsError):
        save_schema_index(INDEX, index.index, manifest)
    altered = json.loads(INDEX.read_text(encoding='utf-8'))
    altered['entries'][0]['ddl'] += ' -- altered'
    with pytest.raises(ValueError, match='differs'):
        SchemaIndex(altered, manifest)


def test_persistent_budget_survives_restart_and_charges_pending(tmp_path):
    path = tmp_path / 'budget.sqlite'
    limits = SQLBudgetLimits(2, 1, 20, 20)
    ledger = PersistentSQLBudgetLedger(path, limits)
    first = ledger.reserve('validation/1', is_probe=True, max_bytes_billed=10)
    assert PersistentSQLBudgetLedger(path, limits).snapshot() == {
        'calls': 1, 'probes': 1, 'charged_bytes': 10, 'pending': 1}
    ledger.reconcile('validation/1', reserved_bytes=10, actual_bytes_billed=4,
                     reservation_id=first)
    restarted = PersistentSQLBudgetLedger(path, limits)
    restarted.reserve('validation/1', is_probe=False, max_bytes_billed=10)
    assert restarted.snapshot()['charged_bytes'] == 14
    with pytest.raises(PermissionError, match='budget'):
        restarted.reserve('validation/1', is_probe=False, max_bytes_billed=10)
    with pytest.raises(ValueError, match='already reconciled'):
        restarted.reconcile('validation/1', reserved_bytes=10, actual_bytes_billed=4,
                            reservation_id=first)


def test_budgeted_database_uses_persistent_reservation(tmp_path):
    db = MockBigQuery([], results={'SELECT 1': Execution(('n',), ((1,),), True, 3)})
    ledger = PersistentSQLBudgetLedger(tmp_path / 'ledger.sqlite', SQLBudgetLimits(1, 0, 10, 10))
    assert BudgetedDatabase(db, ledger, question_id='q', max_bytes_billed=10).execute('SELECT 1').rows == ((1,),)
    assert ledger.snapshot()['charged_bytes'] == 3


def test_restricted_artifact_round_trips_bigquery_types_and_duplicates(tmp_path):
    root = tmp_path / 'restricted'
    root.mkdir()
    store = ResultArtifactStore(root, verify_private_acl=lambda _: True)
    row = (None, date(2026, 11, 13), datetime(2026, 11, 13, tzinfo=timezone.utc),
           Decimal('1.2300'), [1, None, Decimal('2.5')], {'code': 'x', 'nested': [None]})
    result = Execution(('nullable', 'd', 'ts', 'num', 'arr', 'struct'), (row, row), True,
                       column_types=('STRING', 'DATE', 'TIMESTAMP', 'NUMERIC', 'ARRAY', 'STRUCT'))
    info = store.save('phase_b_synthetic', result)
    restored = store.load('phase_b_synthetic', expected_sha256=info['sha256'])
    assert restored.rows == result.rows and restored.column_types == result.column_types
    assert len(restored.rows) == 2
    with pytest.raises(ValueError, match='Truncated'):
        store.save('incomplete', Execution(('n',), ((1,),), False))


def test_saved_prediction_can_stage_restricted_result_without_model_call(tmp_path):
    root = tmp_path / 'restricted'
    root.mkdir()
    store = ResultArtifactStore(root, verify_private_acl=lambda _: True)
    info = store.save('synthetic_rows', Execution(('d', 'n'),
                      ((date(2026, 1, 1), None), (date(2026, 1, 1), None)), True,
                      job_id='synthetic-job'))
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'Synthetic question')
    log = tmp_path / 'prediction.json'
    log.write_text(json.dumps({'summary': {'query_id': question.query_id},
                               'events': [{'stage': 'execute', 'sql': 'SELECT d,n FROM synthetic',
                                           'error': None, 'job_id': 'synthetic-job',
                                           'row_count': 2, 'complete': True},
                                          {'stage': 'prediction', 'split': 'validation',
                                           'sql': 'SELECT d,n FROM synthetic'},
                                          {**info, 'stage': 'result_artifact',
                                           'artifact_expires_at_utc': '2099-01-01T00:00:00+00:00'}]}), encoding='utf-8')
    source = tmp_path / 'benchmark/data/splits/validation/Labs/easy/001'
    source.mkdir(parents=True)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (source / name).write_text('{}', encoding='utf-8')
    staged = prepare_saved_run_sample(log, tmp_path / 'staged', tmp_path / 'benchmark',
                                      question, result_store=store, artifact_id='synthetic_rows',
                                      artifact_sha256=info['sha256'])
    assert (staged / 'result_001.csv').read_text(encoding='utf-8').splitlines() == [
        'd,n', '2026-01-01,', '2026-01-01,']
    assert '2026-01-01' not in log.read_text(encoding='utf-8')
    mismatched = json.loads(log.read_text(encoding='utf-8'))
    mismatched['events'][0]['job_id'] = 'other-job'
    log.write_text(json.dumps(mismatched), encoding='utf-8')
    with pytest.raises(ValueError, match='matching successful SQL job'):
        prepare_saved_run_sample(log, tmp_path / 'staged2', tmp_path / 'benchmark',
                                 question, result_store=store, artifact_id='synthetic_rows',
                                 artifact_sha256=info['sha256'])


def test_adapter_marks_partial_results_incomplete_even_when_page_short():
    class Client:
        def dry_run(self, sql, **kwargs): return 1
        def execute(self, sql, **kwargs):
            return {'columns': ['n'], 'column_types': ['INT64'], 'rows': [(1,), (2,)],
                    'total_rows': 10}
    adapter = BigQueryAdapter(Client(), [], Limits(10, max_rows=5, allow_data_execution=True),
                              allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    assert not adapter.execute('SELECT 1').complete


def test_sde_native_consistency_ignores_duplicates_empty_results_and_keeps_first_tie():
    candidates = ['first', 'second', 'third', 'fourth']
    successful = {
        'first': Execution(('x',), ((1,), (1,)), True),
        'second': Execution(('x',), ((1,),), True),
        'third': Execution(('x',), ((2,),), True),
        'fourth': Execution(('x',), (), True),
    }
    assert _most_consistent(candidates, list(successful.values())) == 'first'
    assert _most_consistent(candidates, [successful['first'], None, successful['third'], None]) == 'first'
    assert _most_consistent(candidates, [None, None, None, successful['fourth']]) == 'first'


def test_shared_benchmark_backend_is_manifest_pinned_and_execution_closed():
    manifest, index = scope()
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp',
                            'mimiciv_3_1_icu', 'US', 'kltn-text-to-sql')
    backend = make_benchmark_database(config, manifest, index,
                                      BenchmarkExecutionConfig(20_000_000, 30, 500),
                                      case_id='validation/example', client=object())
    assert len(backend.schema_metadata()) == 31
    with pytest.raises(PermissionError, match='disabled'):
        backend.execute('SELECT COUNT(*) FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`')
    wrong = BigQueryConfig('other-project', 'mimiciv_3_1_hosp',
                           'mimiciv_3_1_icu', 'US', 'other-project')
    with pytest.raises(ValueError, match='differs'):
        make_benchmark_database(wrong, manifest, index,
                                BenchmarkExecutionConfig(20_000_000, 30, 500),
                                case_id='validation/example', client=object())


def _model(method, question, sql):
    if method == 'clinsql_cot':
        return MockLLM({'generate': [f'```sql\n{sql}\n```']})
    if method == 'mac_sql':
        return MockLLM({'mac.selector': [{'admissions': ['hadm_id'], 'patients': ['subject_id'],
                                          'transfers': ['hadm_id']}],
                        'mac.decomposer': [f'```sql\n{sql}\n```']})
    if method == 'sde_sql':
        return MockLLM({'sde.explore1': [{'Base': [sql]}],
                        'sde.explore2': [{'Combined': sql}], 'sde.generate': [sql] * 9,
                        'sde.judge': [{'Modification': 'False'}] * 3})
    link = {'requirements': [{'id': 'r1', 'kind': 'output', 'span': question,
                              'description': 'Synthetic count request'}],
            'links': [{'requirement_id': 'r1', 'span': question, 'table': 'admissions',
                       'column': 'hadm_id', 'role': 'admission identity', 'catalog_id': None}],
            'joins': [], 'ambiguities': []}
    plan = {'steps': [{'id': 's1', 'operation': 'aggregate', 'depends_on': [],
                       'requirement_ids': ['r1'], 'tables': ['admissions'],
                       'description': 'Synthetic count'}], 'output_step': 's1'}
    def verified(cid):
        return {'checks': [{'requirement_id': 'r1', 'status': 'satisfied',
                            'sql_evidence_ids': [f'{cid}:e1'], 'schema_refs': ['admissions'],
                            'evidence': 'COUNT'}],
                'question_coverage': {'status': 'complete', 'uncovered_spans': [],
                                      'extra_constraints': []}, 'verdict': 'supported'}
    return MockLLM({'link': [link], 'decompose': [plan],
                    'generate': [{'sql': sql, 'unresolved': []}] * 3,
                    'verify': [verified(f'c{i}') for i in range(1, 4)]})


def test_four_methods_end_to_end_on_two_official_validation_questions(tmp_path):
    manifest, index = scope()
    questions, question_hash = load_official_questions(Path('external/clinsql_official'))
    assert len(questions) == 190 and len(question_hash) == 64
    sql = ('SELECT COUNT(*) AS n FROM '
           '`kltn-text-to-sql.mimiciv_3_1_hosp.admissions`')
    config = ExperimentConfig()
    for question in questions[:2]:
        for method in ('clinsql_cot', 'mac_sql', 'sde_sql', 'proposed'):
            model = _model(method, question.text, sql)
            db = MockBigQuery(schema_records_from_manifest(manifest),
                              results={sql: Execution(('n',), ((1,),), True)})
            output = run_validation_one(method, question, model=model, database=db,
                                        output_root=tmp_path, config=config,
                                        schema_index=index if method == 'proposed' else None,
                                        value_evidence=lambda *_: 'synthetic dictionary evidence')
            assert output['sql'].rstrip(';') == sql and output['status'] in {'executed', 'answered'}, (method, output)
            assert any(stage == 'execute' for stage, _ in db.calls)
            assert load_validation_checkpoint(method, question, output_root=tmp_path,
                                              config=config,
                                              schema_index=index if method == 'proposed' else None)['sql'] == output['sql']
            with pytest.raises(FileExistsError):
                run_validation_one(method, question, model=model, database=db,
                                   output_root=tmp_path, config=config)
    assert len(list(tmp_path.glob('*/*.json'))) == 8
