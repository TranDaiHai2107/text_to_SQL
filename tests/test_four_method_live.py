"""Shared live-runner contracts exercised exclusively with local fixtures."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import pytest

from ehrqa.cli.four_method_pilot import _ledger_root, _questions, _scope
from ehrqa.clinsql import four_method_runner as runner
from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.catalog_export import FIELDS, catalog_queries, export_catalog
from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
from ehrqa.clinsql.execution_control import EXPECTED_DATASETS, EXPECTED_PROJECT, READER_PRINCIPAL
from ehrqa.clinsql.execution_errors import IncompleteResultError, SecurityRejected
from ehrqa.clinsql.experiment_state import ExperimentState
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.result_artifacts import ResultArtifactStore


@pytest.fixture
def scope():
    master, pilot, manifest, index = _scope()
    return master, pilot, manifest, index, _questions(pilot, master)[0]


def approval_for(scope, method='mac_sql', **overrides):
    master, pilot, manifest, index, _ = scope
    now = datetime.now(timezone.utc)
    params = dict(approval_id='fixture', approver='fixture', authority='fixture',
                  risk_acknowledged=True, iam_status='READ_ONLY_LIKELY_WITH_APPROVED_RISK',
                  valid_from_utc=now - timedelta(minutes=1), valid_until_utc=now + timedelta(hours=1),
                  principal=READER_PRINCIPAL, project_id=EXPECTED_PROJECT, datasets=tuple(EXPECTED_DATASETS),
                  location='US', manifest_sha256=manifest['sha256'], pilot_manifest_sha256=pilot['sha256'],
                  model_id=runner.MODEL, case_ids=tuple(master['pilot_case_ids']), max_bytes_billed_per_sql=10,
                  timeout_seconds=10, max_rows=100, max_result_bytes=1000, api_budget_sha256='a' * 64,
                  sql_budget_sha256='b' * 64, result_storage_policy_reference='fixture',
                  artifact_retention_days=7, method=method, variant='metadata_only',
                  evidence={'A': 'question_and_schema', 'C': 'sql_and_sanitized_errors',
                            'E': 'row_presence_and_null'},
                  policy_reference='synthetic', index_sha256=index.index['sha256'], catalog_sha256=None,
                  configuration_sha256='c' * 64)
    return runner.FourMethodApproval(**(params | overrides))


def test_scope_rejects_missing_evidence_wrong_reader_and_changed_question(scope):
    with pytest.raises(ValueError, match='evidence'):
        approval_for(scope, evidence={'A': 'question_and_schema', 'C': 'sql_and_sanitized_errors'})
    with pytest.raises(ValueError, match='reader'):
        approval_for(scope, principal='owner')
    master, pilot, _, index, question = scope
    changed = SimpleNamespace(query_id=question.query_id, split='validation', text='different question')
    with pytest.raises(PermissionError, match='Question'):
        runner.verify_case(changed, approval_for(scope), pilot, master, index)
    tampered = {**pilot, 'cases': [{**pilot['cases'][0], 'question_sha256': '0'*64}, *pilot['cases'][1:]]}
    with pytest.raises(PermissionError, match='scope'):
        runner.verify_case(question, approval_for(scope), tampered, master, index)


@pytest.mark.parametrize('complete', [True, False])
def test_mac_runner_separately_executes_last_correction_then_resumes(tmp_path, scope, complete):
    master, pilot, _, index, question = scope
    state = ExperimentState(tmp_path / 'state.sqlite', master)
    with pytest.raises(PermissionError, match='phase scope'):
        state.claim(runner.PHASE, 'mac_sql', question.query_id)

    class HistoricalSyntheticState(ExperimentState):
        def _allowed(self, phase, method, case_id):
            return (phase, method, case_id) == (runner.PHASE, 'mac_sql', question.query_id)

    state = HistoricalSyntheticState(tmp_path / 'state.sqlite', master)
    sqls = [f'SELECT {n}' for n in range(4)]
    model = MockLLM({'mac.decomposer': [f'```sql\n{sqls[0]}\n```'],
                     'mac.refiner': [f'```sql\n{sql}\n```' for sql in sqls[1:]]},
                    model_id=runner.MODEL)
    db = MockBigQuery([{'table': 'x', 'ddl': 'CREATE TABLE x (a INT64)'}],
                      results={sqls[-1]: Execution(('n',), ((3,), (4,)), complete, job_id='final')},
                      failures={sql: 'synthetic invalid query' for sql in sqls[:-1]})
    store = ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True)
    kwargs = dict(state=state, approval=approval_for(scope), pilot=pilot, schema_index=index,
                  store=store, output_root=tmp_path, model=model, database=db)
    saved = runner.run_case(question, **kwargs)
    assert saved['status'] == ('EXECUTED' if complete else 'INCOMPLETE_RESULT')
    assert saved['sql'] == sqls[-1] and saved['inference_status'] == 'corrected_unexecuted'
    assert [call for call in db.calls if call[0] == 'execute'] == [('execute', sqls[-1])]
    assert saved['events'][-2 if complete else -1]['stage'] == 'execute'
    assert all(event.get('rows') is None for event in saved['events'])
    if complete:
        value = store.load(saved['artifact']['artifact_id'], expected_sha256=saved['artifact']['sha256'])
        assert value.job_id == 'final' and value.rows == ((3,), (4,))
    else:
        assert 'artifact' not in saved
    calls = len(db.calls), len(model.calls)
    assert runner.run_case(question, **kwargs) == saved
    assert (len(db.calls), len(model.calls)) == calls


def test_sde_final_judge_sql_gets_its_own_execution(tmp_path, scope):
    master, pilot, _, index, question = scope
    final = 'SELECT 99'
    db = MockBigQuery([], results={final: Execution(('final',), ((99,),), True, job_id='judge-final')})
    model = MockLLM({'sde.explore1': [{'Base': ['SELECT 1']}],
                     'sde.explore2': [{'Combined': 'SELECT 2'}],
                     'sde.generate': ['SELECT 3'] * 9,
                     'sde.judge': [{'Modification': 'True', 'Final SQL': final}] * 3},
                    model_id=runner.MODEL)
    approval = approval_for(scope, 'sde_sql', variant='probe_labels_only', evidence={
        'A': 'question_and_schema', 'C': 'sql_and_sanitized_errors', 'E': 'probe_labels_and_column_names'})
    store = ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True)
    result = runner.run_case(question, state=ExperimentState(tmp_path / 'state.sqlite', master),
                             approval=approval, pilot=pilot, schema_index=index, store=store,
                             output_root=tmp_path, model=model, database=db)
    assert result['inference_status'] == 'judge_modified_unexecuted'
    assert result['artifact']['job_id'] == 'judge-final' and result['sql'] == final
    assert [e['choices'] for e in result['events'] if e['stage'] == 'llm'] == [1, 1, 9, 3]


def test_catalog_export_uses_guard_and_loader(tmp_path, scope):
    _, _, manifest, index, _ = scope
    queries = catalog_queries(manifest)
    rows = [('001', 9, 'Example condition'), ('A12', 10, 'Example procedure'),
            (123, 'Example assay', 'Blood', 'Chemistry'),
            (234, 'Example pressure', 'EP', 'chartevents', 'mmHg', 'Measurements')]

    class Client:
        def dry_run(self, sql, **kwargs):
            assert sql in queries.values()
            return 0

        def execute(self, sql, **kwargs):
            i = list(queries.values()).index(sql)
            table = list(queries)[i]
            result = [rows[i]]
            if table == 'd_labitems':
                result.append((124, None, 'Blood', 'Chemistry'))
            return {'columns': FIELDS[table], 'rows': result, 'total_rows': len(result)}

    datasets = tuple(f"{manifest['project_id']}.{name}" for name in manifest['datasets'].values())
    db = BigQueryAdapter(Client(), index.schema_records(), Limits(100, allow_data_execution=True),
                         allowed_datasets=datasets)
    path = tmp_path / 'catalog.json'
    exported = export_catalog(db, manifest, path, source='synthetic', authorization='fixture')
    catalog = ClinicalCatalog.load(path, expected_sha256=exported['sha256'], schema_sha256=manifest['sha256'])
    assert exported['row_counts']['d_labitems'] == 2
    assert catalog.records['d_labitems::124']['label'] is None
    assert {row['code'] for row in catalog.search('Example condition and EP', {'tables': []})} >= {'001', 234}
    with pytest.raises(SecurityRejected):
        db.dry_run('DELETE FROM patients WHERE TRUE')
    bad_db = MockBigQuery([], results={next(iter(queries.values())): Execution((), (), False)})
    with pytest.raises(IncompleteResultError):
        export_catalog(bad_db, manifest, tmp_path / 'bad.json', source='synthetic', authorization='fixture')
    assert not (tmp_path / 'bad.json').exists()


def test_interrupted_checkpoint_never_replays(tmp_path, scope):
    master, pilot, _, index, question = scope
    state = ExperimentState(tmp_path / 'state.sqlite', master)
    state.claim(runner.PHASE, 'sde_sql', question.query_id)
    model, db = MockLLM({}, model_id=runner.MODEL), MockBigQuery([])
    with pytest.raises(FileExistsError, match='reconciliation'):
        runner.run_case(question, state=state, approval=approval_for(scope, 'sde_sql',
                        variant='probe_labels_only', evidence={'A': 'question_and_schema',
                        'C': 'sql_and_sanitized_errors', 'E': 'probe_labels_and_column_names'}),
                        pilot=pilot, schema_index=index,
                        store=ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True),
                        output_root=tmp_path, model=model, database=db)
    assert not model.calls and not db.calls


def test_ledger_scope_cannot_be_changed_under_same_approval_id(tmp_path, scope):
    store = ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True)
    approval = approval_for(scope)
    assert _ledger_root(store, tmp_path, approval) == _ledger_root(store, tmp_path, approval)
    with pytest.raises(PermissionError, match='reset'):
        _ledger_root(store, tmp_path, approval_for(scope, max_rows=200))


def test_ours_runner_uses_pinned_catalog_without_reference_inputs(tmp_path, scope, monkeypatch):
    from ehrqa.clinsql.retrieval import FewShotIndex

    master, pilot, _, index, question = scope
    catalog = ClinicalCatalog([
        {'table': 'd_icd_diagnoses', 'icd_code': 'A12', 'icd_version': 10,
         'long_title': 'Mechanical support fixture'}], source='fixture', sha256='f' * 64)
    approval = approval_for(scope, 'ours', variant='dictionary_rag', catalog_sha256=catalog.sha256,
                            evidence={'A': 'question_and_schema', 'B': 'dictionary_metadata',
                                      'C': 'sql_and_sanitized_errors', 'E': 'shape_and_row_counts'})
    captures = []
    original = runner.build_pipeline

    def build(*args, **kwargs):
        pipeline = original(*args, **kwargs)
        captures.append(pipeline)
        return pipeline

    monkeypatch.setattr(runner, 'build_pipeline', build)
    model = MockLLM({'link': ['{}', '{}']}, model_id=runner.MODEL)
    db = MockBigQuery(index.schema_records())
    saved = runner.run_case(question, state=ExperimentState(tmp_path / 'state.sqlite', master),
                            approval=approval, pilot=pilot, schema_index=index,
                            store=ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True),
                            output_root=tmp_path, model=model, database=db,
                            clinical=catalog, few_shot=FewShotIndex([]))
    assert len(captures) == 1 and saved['status'] == 'MODEL_GENERATION_FAILURE'
    payload = json.loads(model.calls[0]['prompt'][1]['content'])
    assert payload['catalog'][0]['code'] == 'A12'
    assert not {'gold_sql', 'reference_results', 'rubric'} & set(payload)


def test_cot_reuse_and_staging_only_read_saved_results(tmp_path, scope):
    master, pilot, manifest, _, question = scope
    store = ResultArtifactStore(tmp_path, verify_private_acl=lambda _: True)
    artifact = store.save('fixture', Execution(('n',), ((1,),), True, job_id='saved'))
    artifact.update(stage='result_artifact', artifact_expires_at_utc=(
        datetime.now(timezone.utc) + timedelta(days=1)).isoformat())
    source = tmp_path / 'source.json'
    source.write_text(json.dumps({'summary': {'query_id': question.query_id}, 'events': [
        {'stage': 'prediction', 'status': 'executed', 'sql': 'SELECT 1'},
        {'stage': 'execute', 'sql': 'SELECT 1', 'job_id': 'saved', 'complete': True}, artifact]}))
    audit = {'pilot_manifest_sha256': pilot['sha256'], 'schema_sha256': manifest['sha256'],
             'model_id': runner.MODEL, 'cases': {question.query_id: {
                 'run_log': str(source), 'artifact_sha256': artifact['sha256'],
                 'job_id': 'saved', 'row_count': 1}}}
    state = ExperimentState(tmp_path / 'state.sqlite', master)
    record = runner.reuse_cot(question, state=state, audit=audit, store=store, output_root=tmp_path)
    benchmark = tmp_path / 'benchmark'
    reference = benchmark / 'data/splits/validation' / question.query_id
    reference.mkdir(parents=True)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (reference / name).write_text('{}')
    (reference / 'gold_sql.sql').write_text('GOLD')
    staged = runner.stage_saved_prediction(record, question, store=store, root=tmp_path,
                                           benchmark_root=benchmark)
    assert not (staged / 'gold_sql.sql').exists()
    assert len(list(staged.glob('result_*.csv'))) == 1
