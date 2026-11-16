"""No network, real patient database, test gold or paid judge in these tests."""
import json
import hashlib
import sys
from types import ModuleType

import pytest

from ehrqa.agentic.schema import Schema
from ehrqa.clinsql.baselines.mac_sql import MACSQL
from ehrqa.clinsql.baselines.sde_sql import SDESQL
from ehrqa.clinsql.bigquery_client import (BigQueryClient, discover_dataset_location,
                                          METADATA_MAX_BYTES_BILLED)
from ehrqa.clinsql.config import BigQueryConfig, ExperimentConfig
from ehrqa.clinsql.cot_runner import ClinSQLCoT
from ehrqa.clinsql.dataset import Question
from ehrqa.clinsql.evaluator import (OfficialClinSQLEvaluator, prepare_official_sample,
                                     prepare_saved_run_sample)
from ehrqa.clinsql.metadata import (mock_schema_records, HOSP_TABLES, ICU_TABLES,
                                   build_schema_manifest, schema_records_from_manifest,
                                   information_schema_sql, verify_schema_manifest)
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import build_pipeline
from ehrqa.clinsql.retrieval import ApprovedICDCatalog, FewShotIndex
from ehrqa.clinsql.runner import run_validation_one
from ehrqa.text2sql.interfaces import Execution
from ehrqa.text2sql.logging import MeteredModel, Pricing, RunLog
from ehrqa.cli.bigquery_preflight import inspect_remote, plan as bigquery_plan


def records():
    return mock_schema_records('demo', 'hosp', 'icu')


def test_metadata_and_config_are_offline_and_31_table_complete(monkeypatch):
    rows = records()
    assert len(rows) == 31 and sum(r['dataset'] == 'hosp' for r in rows) == 22
    assert all(r['type_source'] == 'synthetic_mock_only' for r in rows)
    schema = Schema.from_records(rows, dialect='bigquery')
    assert schema.inspect('SELECT COUNT(*) FROM demo.hosp.admissions')['valid']
    with pytest.raises(ValueError):
        BigQueryConfig.from_env()
    for key, value in {'BQ_PROJECT_ID': 'demo', 'BQ_HOSP_DATASET': 'hosp',
                       'BQ_ICU_DATASET': 'icu', 'BQ_LOCATION': 'US',
                       'BQ_BILLING_PROJECT': 'billing'}.items():
        monkeypatch.setenv(key, value)
    assert BigQueryConfig.from_env().allowed_datasets == ('demo.hosp', 'demo.icu')
    assert bigquery_plan()['queries_executed'] == 0


def test_verified_schema_loader_uses_injected_metadata_only():
    tables = {role: [{'table_name': name, 'table_type': 'BASE TABLE'} for name in names]
              for role, names in (('hosp', HOSP_TABLES), ('icu', ICU_TABLES))}
    columns = {role: [{'table_name': name, 'column_name': 'subject_id', 'data_type': 'INT64',
                       'is_nullable': 'NO', 'ordinal_position': 1} for name in names]
               for role, names in (('hosp', HOSP_TABLES), ('icu', ICU_TABLES))}
    config = BigQueryConfig('demo', 'hosp', 'icu', 'US', 'billing')
    manifest = build_schema_manifest(config, tables, columns)
    rows = schema_records_from_manifest(manifest)
    assert len(rows) == 31 and len(manifest['sha256']) == 64
    assert manifest['captured_at_utc'].endswith('+00:00')
    assert all('`subject_id` INT64' in row['ddl'] for row in rows)
    assert all(row['type_source'] == 'bigquery_information_schema' for row in rows)
    assert 'INFORMATION_SCHEMA.COLUMNS' in information_schema_sql('demo', 'hosp', 'COLUMNS')
    manifest['tables'][0]['columns'][0]['type'] = 'STRING'
    with pytest.raises(ValueError, match='corrupted'):
        verify_schema_manifest(manifest)


def test_remote_preflight_uses_only_metadata_and_dry_runs_with_fake_sdk(monkeypatch):
    calls = {'get_table': [], 'query': []}
    class Table:
        num_rows = 42
    class Job:
        def __init__(self, rows): self.rows = rows
        def result(self, **_kwargs): return [type('Row', (), {'items': lambda self, row=row: row.items()})() for row in self.rows]
    class Client:
        def __init__(self, **_kwargs):
            pass
        def get_dataset(self, dataset_id):
            return type('Dataset', (), {'location': 'US'})()
        def get_table(self, table_id):
            calls['get_table'].append(table_id)
            return Table()
        def query(self, sql, *, job_config, **_kwargs):
            assert job_config.use_legacy_sql is False
            assert job_config.maximum_bytes_billed == METADATA_MAX_BYTES_BILLED
            calls['query'].append(sql)
            role = 'hosp' if '.hosp.' in sql else 'icu'
            names = HOSP_TABLES if role == 'hosp' else ICU_TABLES
            if sql.endswith('table_name'):
                return Job([{'table_name': name, 'table_type': 'BASE TABLE'} for name in names])
            return Job([{'table_name': name, 'column_name': 'subject_id', 'data_type': 'INT64',
                         'is_nullable': 'NO', 'ordinal_position': 1} for name in names])
    class QueryJobConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
    google = ModuleType('google')
    cloud = ModuleType('google.cloud')
    bigquery = ModuleType('google.cloud.bigquery')
    bigquery.Client, bigquery.QueryJobConfig = Client, QueryJobConfig
    cloud.bigquery = bigquery
    google.cloud = cloud
    for name, module in [('google', google), ('google.cloud', cloud),
                         ('google.cloud.bigquery', bigquery)]:
        monkeypatch.setitem(sys.modules, name, module)
    report = inspect_remote(BigQueryConfig('demo', 'hosp', 'icu', 'US', 'billing'))
    assert len(calls['get_table']) == 31 and len(calls['query']) == 4
    assert report['patient_queries_executed'] == 0 and report['table_count'] == 31
    assert report['location'] == 'US'
    assert report['schema_validation']['datetimeevents_present']
    assert 'admissions' in report['schema_validation']['missing_critical_columns']
    assert set(report['row_count_metadata'].values()) == {42}


def test_location_discovery_rejects_cross_region_datasets():
    class Client:
        def get_dataset(self, dataset_id):
            return type('Dataset', (), {'location': 'US' if dataset_id.endswith('.hosp') else 'EU'})()
    with pytest.raises(ValueError, match='share one verified location'):
        discover_dataset_location('demo', 'hosp', 'icu', 'billing', client=Client())


def test_bigquery_transport_blocks_writes_and_requires_explicit_execution(monkeypatch):
    calls = []
    class QueryJobConfig:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    class Job:
        total_bytes_processed = 25
        total_bytes_billed = 25
        schema = [type('Field', (), {'name': 'n', 'field_type': 'INTEGER'})()]
        def result(self, **_kwargs):
            return [type('Row', (), {'values': lambda self: (1,)})()]
    class Client:
        def query(self, sql, **kwargs):
            calls.append((sql, kwargs))
            return Job()
    bigquery = ModuleType('google.cloud.bigquery')
    bigquery.QueryJobConfig = QueryJobConfig
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', bigquery)
    config = BigQueryConfig('demo', 'hosp', 'icu', 'US', 'billing')
    sql = 'SELECT 1 AS n'
    transport = BigQueryClient(config, client=Client())
    with pytest.raises(PermissionError, match='read-only'):
        transport.execute('DELETE FROM `demo.hosp.admissions` WHERE TRUE',
                          max_bytes_billed=100, timeout_seconds=2, max_rows=2)
    with pytest.raises(PermissionError, match='disabled'):
        transport.execute(sql, max_bytes_billed=100, timeout_seconds=2, max_rows=2)
    assert calls == []
    enabled = BigQueryClient(config, client=Client(), allow_data_execution=True)
    with pytest.raises(PermissionError, match='scoped execution approval'):
        enabled.execute(sql, max_bytes_billed=100, timeout_seconds=2, max_rows=2)
    assert calls == []


def test_bigquery_adapter_redacts_query_errors_and_blocks_unlisted_tables():
    from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
    class FailingClient:
        def dry_run(self, sql, **_kwargs):
            raise RuntimeError('sensitive database diagnostic')
    adapter = BigQueryAdapter(FailingClient(), records(), Limits(100),
                              allowed_datasets=('demo.hosp', 'demo.icu'))
    with pytest.raises(PermissionError, match='outside the verified schema'):
        adapter.dry_run('SELECT * FROM `demo.hosp.secret_table`')
    with pytest.raises(ConnectionError, match='details withheld') as error:
        adapter.dry_run('SELECT * FROM `demo.hosp.admissions`')
    assert 'sensitive' not in str(error.value)


def test_retrieval_rejects_non_development_and_current_question():
    sample = {'query_id': 'Labs/easy/001', 'split': 'validation', 'partition': 'development',
              'question': 'How many admissions?', 'sql': 'SELECT COUNT(*) FROM admissions'}
    index = FewShotIndex([sample])
    assert not index.retrieve('How many admissions?')['items']
    assert len(index.retrieve('Count hospital admissions')['items']) == 1
    blocked = hashlib.sha256('select count from admissions'.encode()).hexdigest()
    assert FewShotIndex([{**sample, 'sql': 'SELECT COUNT FROM admissions'}],
                        blocked_sql_hashes={blocked}).retrieve('Other question')['items'] == []
    with pytest.raises(ValueError):
        FewShotIndex([{**sample, 'split': 'test'}])
    with pytest.raises(ValueError):
        FewShotIndex([{**sample, 'partition': 'internal_check'}])
    with pytest.raises(ValueError):
        ApprovedICDCatalog([{'table': 'patients', 'label': 'x'}])


def test_mac_sql_runs_selector_decomposer_and_refiner_with_mocks():
    first = 'SELECT bad FROM demo.hosp.admissions'
    final = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    db = MockBigQuery(records(), failures={first: 'syntax error'})
    model = MockLLM({'mac.selector': [{'admissions': ['hadm_id'], 'patients': ['subject_id'],
                                      'transfers': ['hadm_id']}],
                     'mac.decomposer': [f'```sql\n{first}\n```'],
                     'mac.refiner': [f'```sql\n{final}\n```']})
    output = MACSQL(model, db, value_evidence=lambda *_: 'synthetic allowed evidence').run('How many admissions?')
    assert output['status'] == 'executed' and output['sql'] == final
    assert [x['stage'] for x in model.calls] == ['mac.selector', 'mac.decomposer', 'mac.refiner']
    assert len(output['attempts']) == 3
    assert ('execute', final) in db.calls  # next ChatManager round
    with pytest.raises(ValueError):
        MACSQL(model, db, value_evidence=None)
    with pytest.raises(PermissionError, match='Column value examples'):
        MACSQL(model, db, value_evidence=lambda *_: {
            'evidence': '', 'column_values': {'patients': {'gender': "['F', 'M']"}}
        }).run('How many admissions?')


def test_sde_sql_keeps_two_probe_stages_nine_candidates_and_judge():
    sql = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    db = MockBigQuery(records())
    model = MockLLM({'sde.explore1': [{'Base SQL Probes': [sql]}],
                     'sde.explore2': [{'Combined SQL Probes': sql}],
                     'sde.generate': [sql] * 9,
                     'sde.judge': [{'Modification': 'False'}] * 3})
    output = SDESQL(model, db).run('How many admissions?', schema_text='admissions')
    assert output['status'] == 'executed' and output['sql'] == sql
    assert len([c for c in model.calls if c['stage'] == 'sde.generate']) == 9
    assert len([c for c in db.calls if c[0] == 'probe']) == 2
    assert len([c for c in model.calls if c['stage'] == 'sde.judge']) == 3
    with pytest.raises(ValueError, match='Custom Boolean judge'):
        SDESQL(model, db, judge=lambda *_: True)


def test_sde_sql_refinement_uses_diagnostic_probe_before_accepting():
    first = 'SELECT hadm_id FROM demo.hosp.admissions WHERE hadm_id < 0'
    fixed = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    model = MockLLM({'sde.explore1': [{'Base': [fixed]}],
                     'sde.explore2': [{'Combined': fixed}],
                     'sde.generate': [first] * 9,
                     'sde.refine_probes': [{'Diagnostic': fixed}],
                     'sde.refine': [fixed]})
    db = MockBigQuery(records(), results={first: Execution(('hadm_id',), (), True)})
    output = SDESQL(model, db).run('Count admissions', schema_text='admissions')
    assert output['sql'] == fixed and output['status'] == 'executed'
    assert not any(a['stage'] == 'judge' for a in output['attempts'])
    assert any(a['stage'] == 'refinement_decision' and a['reason'] == 'no data selected'
               for a in output['attempts'])
    assert len([c for c in db.calls if c[0] == 'probe']) == 5
    assert 'sde.search_probes' not in [c['stage'] for c in model.calls]


def test_sde_sql_execution_error_uses_native_error_prompt_without_diagnostic_probes():
    first = 'SELECT bad FROM demo.hosp.admissions'
    fixed = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    model = MockLLM({'sde.explore1': [{'Base': [fixed]}],
                     'sde.explore2': [{'Combined': fixed}],
                     'sde.generate': [first] * 9,
                     'sde.refine_error': [fixed]})
    db = MockBigQuery(records(), failures={first: 'syntax error'})
    output = SDESQL(model, db).run('Count admissions', schema_text='admissions')
    assert output['status'] == 'executed' and output['sql'] == fixed
    assert 'sde.refine_error' in [c['stage'] for c in model.calls]
    assert 'sde.refine_probes' not in [c['stage'] for c in model.calls]


def test_sde_native_three_vote_modified_sql_is_not_executed_by_judge():
    original = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    revised = 'SELECT COUNT(DISTINCT hadm_id) FROM demo.hosp.admissions'
    model = MockLLM({
        'sde.explore1': [{'Base': [original]}],
        'sde.explore2': [{'Combined': original}],
        'sde.generate': [original] * 9,
        'sde.judge': [{'Modification': 'False'},
                      {'Modification': 'True', 'Final SQL': revised},
                      {'Modification': 'True', 'Final SQL': revised}],
    })
    db = MockBigQuery(records())
    output = SDESQL(model, db).run('Count distinct admissions', schema_text='admissions')
    assert output['sql'] == revised and output['status'] == 'judge_modified_unexecuted'
    assert ('execute', revised) not in db.calls
    assert len([a for a in output['attempts'] if a['stage'] == 'judge']) == 1


def test_sde_refinement_retries_at_most_three_without_outer_regeneration():
    bad = 'SELECT bad FROM demo.hosp.admissions'
    fixes = [f'SELECT bad_{i} FROM demo.hosp.admissions' for i in range(3)]
    db = MockBigQuery(records(), failures={sql: 'synthetic syntax error'
                                             for sql in [bad, *fixes]})
    model = MockLLM({'sde.explore1': [{'Base': ['SELECT 1']}],
                     'sde.explore2': [{'Combined': 'SELECT 1'}],
                     'sde.generate': [bad] * 9,
                     'sde.refine_error': fixes})
    output = SDESQL(model, db).run('Synthetic question', schema_text='admissions')
    assert output['status'] == 'unresolved' and output['sql'] == fixes[-1]
    assert len([a for a in output['attempts'] if a['stage'] == 'refine']) == 3
    assert len([c for c in model.calls if c['stage'] == 'sde.generate']) == 9
    assert not any(c['stage'] == 'sde.judge' for c in model.calls)


def test_evaluation_staging_and_saved_prediction_scoring_are_separate(tmp_path):
    source = tmp_path / 'source'
    sample = source / 'data/splits/validation/Labs/easy/001'
    sample.mkdir(parents=True)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (sample / name).write_text('{}', encoding='utf-8')
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'How many admissions?')
    target = prepare_official_sample(tmp_path / 'predictions', source, question, 'SELECT 1',
                                     Execution(('n',), ((1,),), True))
    assert (target / 'sql_001.sql').read_text() == 'SELECT 1'
    assert (target / 'result_001.csv').read_text().splitlines() == ['n', '1']
    scorer_source = source / 'evaluation'
    scorer_source.mkdir()
    (scorer_source / 'clinical_rubric_scorer.py').write_text('# mock source', encoding='utf-8')
    class FakeScore:
        sql_score = 0.8
        results_score = 0.6
    class FakeScorer:
        def score_sample(self, path):
            assert path == target
            return FakeScore()
    evaluator = OfficialClinSQLEvaluator(source, source_commit='locked', judge_config_hash='mock',
                                          scorer_factory=FakeScorer)
    result = evaluator.evaluate_saved_predictions(str(tmp_path / 'predictions'), split='validation')
    assert result['sql_score'] == 0.8 and result['execution_score'] == 0.6
    with pytest.raises(PermissionError):
        prepare_official_sample(tmp_path, source, Question('Labs/easy/001', 'test', 'Labs', 'easy', 'q'), 'SELECT 1', None)


def test_logging_captures_usage_cost_and_prevents_overwrite(tmp_path):
    log = RunLog('q1', 'mac', Pricing(1.0, 2.0))
    model = MeteredModel(MockLLM({'generate': ['SELECT 1']}), log)
    model.generate('generate', 'prompt')
    log.add('execute', sql='SELECT 1', rows=[[1]], error=None)
    summary = log.summary()
    assert summary['api_calls'] == 1 and summary['input_tokens'] == 10
    assert summary['estimated_inference_cost_usd'] == 0.00002
    path = log.save(tmp_path / 'record.json')
    assert json.loads(path.read_text())['events'][1]['sql'] == 'SELECT 1'
    with pytest.raises(FileExistsError):
        log.save(path)


def test_proposed_full_agentic_pipeline_runs_end_to_end_with_mocks():
    sql = 'SELECT COUNT(*) AS n FROM demo.hosp.admissions'
    question = 'How many admissions?'
    link = {'requirements': [{'id': 'r1', 'kind': 'output', 'span': question,
                              'description': 'Count admissions'}],
            'links': [{'requirement_id': 'r1', 'span': question,
                       'table': 'admissions', 'column': 'hadm_id',
                       'role': 'admission identity', 'catalog_id': None}],
            'joins': [], 'ambiguities': []}
    plan = {'steps': [{'id': 's1', 'operation': 'aggregate', 'depends_on': [],
                       'requirement_ids': ['r1'], 'tables': ['admissions'],
                       'description': 'Count admissions'}], 'output_step': 's1'}
    def verification(candidate):
        return {'checks': [{'requirement_id': 'r1', 'status': 'satisfied',
                            'sql_evidence_ids': [f'{candidate}:e1'],
                            'schema_refs': ['admissions'], 'evidence': 'COUNT over admissions'}],
                'question_coverage': {'status': 'complete', 'uncovered_spans': [],
                                      'extra_constraints': []}, 'verdict': 'supported'}
    model = MockLLM({'link': [link], 'decompose': [plan],
                     'generate': [{'sql': sql, 'unresolved': []}] * 3,
                     'verify': [verification(f'c{i}') for i in range(1, 4)]})
    db = MockBigQuery(records(), results={sql: Execution(('n',), ((1,),), True)})
    pipeline = build_pipeline(db, model, icd_catalog=ApprovedICDCatalog())
    output = pipeline.run(question, query_id='validation/sample')
    assert output['status'] == 'answered', output['reason']
    assert output['sql'] == sql
    assert output['ctx']['examples']['items'] == []
    assert [c['stage'] for c in model.calls][:2] == ['link', 'decompose']
    assert sum(c[0] == 'execute' for c in db.calls) == 3
    with pytest.raises(PermissionError, match='result-to-LLM'):
        pipeline.answer(question, output, include_values=True)


def test_proposed_bigquery_profile_repairs_invalid_sql_offline():
    question = 'How many admissions?'
    sql = 'SELECT COUNT(*) AS n FROM demo.hosp.admissions'
    link = {'requirements': [{'id': 'r1', 'kind': 'output', 'span': question,
                              'description': 'Count admissions'}],
            'links': [{'requirement_id': 'r1', 'span': question, 'table': 'admissions',
                       'column': 'hadm_id', 'role': 'identity', 'catalog_id': None}],
            'joins': [], 'ambiguities': []}
    plan = {'steps': [{'id': 's1', 'operation': 'aggregate', 'depends_on': [],
                       'requirement_ids': ['r1'], 'tables': ['admissions'],
                       'description': 'Count admissions'}], 'output_step': 's1'}
    verify = lambda cid: {'checks': [{'requirement_id': 'r1', 'status': 'satisfied',
                                     'sql_evidence_ids': [f'{cid}:e1'],
                                     'schema_refs': ['admissions'], 'evidence': 'aggregate'}],
                          'question_coverage': {'status': 'complete', 'uncovered_spans': [],
                                                'extra_constraints': []}, 'verdict': 'supported'}
    model = MockLLM({'link': [link], 'decompose': [plan],
                     'generate': [{'sql': 'SELECT bad FROM demo.hosp.admissions', 'unresolved': []},
                                  {'sql': sql, 'unresolved': []}, {'sql': sql, 'unresolved': []}],
                     'repair': [{'sql': sql, 'unresolved': []}],
                     'verify': [verify(f'c{i}') for i in range(1, 4)]})
    output = build_pipeline(MockBigQuery(records()), model).run(question)
    assert output['status'] == 'answered' and output['sql'] == sql
    assert [c['stage'] for c in model.calls].count('repair') == 1
    assert any(e['stage'] == 'candidate.execution' and e['error'] for e in output['trace'])


def test_common_runner_persists_prediction_and_blocks_repeat_and_test(tmp_path):
    sql = 'SELECT COUNT(*) FROM demo.hosp.admissions;'
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'How many admissions?')
    model = MockLLM({'generate': [f'```sql\n{sql}\n```']})
    db = MockBigQuery(records())
    output = run_validation_one('clinsql_cot', question, model=model, database=db,
                                output_root=tmp_path, config=ExperimentConfig(),
                                pricing=Pricing(1, 2))
    assert output['status'] == 'executed'
    saved = json.loads((tmp_path / 'clinsql_cot' / 'Labs__easy__001.json').read_text())
    assert saved['summary']['api_calls'] == 1
    assert saved['events'][-1]['sql'] == sql
    assert any(e['stage'] == 'execute' for e in saved['events'])
    source = tmp_path / 'source'
    benchmark_sample = source / 'data/splits/validation/Labs/easy/001'
    benchmark_sample.mkdir(parents=True)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (benchmark_sample / name).write_text('{}')
    prepared = prepare_saved_run_sample(output['log_path'], tmp_path / 'evaluation', source, question)
    assert (prepared / 'result_001.csv').read_text().splitlines() == ['count', '1']
    assert len(model.calls) == 1  # evaluation preparation never re-runs inference
    with pytest.raises(FileExistsError):
        run_validation_one('clinsql_cot', question, model=model, database=db,
                           output_root=tmp_path, config=ExperimentConfig())
    with pytest.raises(PermissionError):
        run_validation_one('clinsql_cot', Question('Labs/easy/002', 'test', 'Labs', 'easy', 'q'),
                           model=model, database=db, output_root=tmp_path,
                           config=ExperimentConfig())


def test_common_runner_accepts_mac_and_sde_with_same_mock_database(tmp_path):
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'Count admissions')
    sql = 'SELECT COUNT(*) FROM demo.hosp.admissions'
    db = MockBigQuery(records())
    mac = MockLLM({'mac.selector': [{'admissions': ['hadm_id'], 'patients': ['subject_id'],
                                    'transfers': ['hadm_id']}],
                   'mac.decomposer': [f'```sql\n{sql}\n```']})
    mac_result = run_validation_one('mac_sql', question, model=mac, database=db,
                                    output_root=tmp_path, config=ExperimentConfig(),
                                    value_evidence=lambda *_: 'synthetic catalog values', historical=True)
    sde = MockLLM({'sde.explore1': [{'Base': [sql]}],
                   'sde.explore2': [{'Combined': sql}],
                   'sde.generate': [sql] * 9,
                   'sde.judge': [{'Modification': 'False'}] * 3})
    sde_result = run_validation_one('sde_sql', question, model=sde, database=db,
                                    output_root=tmp_path, config=ExperimentConfig())
    assert mac_result['usage']['api_calls'] == 2
    assert sde_result['usage']['api_calls'] == 4
    assert mac_result['sql'] == sde_result['sql'] == sql


def test_clinsql_cot_stops_on_empty_generation_without_sql_probe():
    model = MockLLM({'generate': ['']})
    db = MockBigQuery(records())
    output = ClinSQLCoT(model, db, 'CREATE TABLE admissions (hadm_id INT64)').run('q', 'Count admissions')
    assert output.status == 'generation_failure' and output.execution_attempts == 0
    assert db.calls == [] and len(model.calls) == 1


def test_runner_persists_failure_without_retrying_paid_transport(tmp_path):
    question = Question('Labs/easy/003', 'validation', 'Labs', 'easy', 'Count admissions')
    model = MockLLM({})
    with pytest.raises(ValueError, match='value-evidence provider'):
        run_validation_one('mac_sql', question, model=model, database=MockBigQuery(records()),
                           output_root=tmp_path, config=ExperimentConfig(), historical=True)
    path = tmp_path / 'mac_sql' / 'Labs__easy__003.json'
    saved = json.loads(path.read_text())
    assert saved['events'][-1]['status'] == 'error'
    assert saved['summary']['api_calls'] == 0
