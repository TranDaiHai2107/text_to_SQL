"""All Phase C.1 tests use fake OpenAI/BigQuery clients; never send requests."""
import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
import json
import sys
from types import ModuleType

import pytest

from ehrqa.cli.phase_c1_pilot import (
    HISTORICAL_PILOT, SOURCE_ALIGNED_NEXT_RUN, _profile_request_settings, _run_root, execute_batch, plan,
)
from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
from ehrqa.clinsql.baselines.mac_sql import (_bird_schema_text, _native_pruning_needed,
                                            _selected_schema_text)
from ehrqa.clinsql.baselines.sde_judge import native_three_vote_judge
from ehrqa.agentic.schema import Schema
from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.bigquery_client import BigQueryClient
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.metadata import schema_records_from_manifest
from ehrqa.clinsql.openai_provider import (AmbiguousModelRequest,
                                           ModelGenerationFailure, OpenAIModelProvider)
from ehrqa.clinsql.pilot_api_budget import PersistentAPIBudgetLedger, PilotAPIBudget
from ehrqa.clinsql.pilot_cases import select_pilot_cases, verify_pilot_cases
from ehrqa.clinsql.real_cot_runner import run_real_cot_case, load_real_cot_checkpoint
from ehrqa.clinsql.pilot_retention import inspect_or_delete_expired
from ehrqa.clinsql.result_artifacts import ResultArtifactStore
from ehrqa.clinsql.schema_index import SchemaIndex
from ehrqa.text2sql.logging import Pricing
from ehrqa.clinsql.evaluator import prepare_official_sample
from ehrqa.clinsql.dataset import Question
from ehrqa.clinsql.cot_runner import ClinSQLCoT
from ehrqa.clinsql.cot import generation_prompt, refinement_prompt, _source_function
from ehrqa.clinsql.execution_errors import SecurityRejected, BudgetExceeded
from run import load_research_env


def _budget(tmp_path, *, calls=3):
    budget = PilotAPIBudget(calls, 100000, 10000, Decimal('1'),
                            Decimal('0.25'), Decimal('2.00'))
    return PersistentAPIBudgetLedger(tmp_path / 'api.sqlite', budget)


def _approval(pilot, manifest):
    now = datetime.now(timezone.utc)
    return BenchmarkExecutionApproval(
        'synthetic-approval', 'Synthetic owner', 'Synthetic project authority', True,
        'READ_ONLY_LIKELY_WITH_APPROVED_RISK', now - timedelta(minutes=1),
        now + timedelta(minutes=5),
        'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com',
        'kltn-text-to-sql', ('kltn-text-to-sql.mimiciv_3_1_hosp',
                             'kltn-text-to-sql.mimiciv_3_1_icu'), 'US',
        manifest['sha256'], pilot['sha256'], 'gpt-5-mini-2025-08-07',
        tuple(c['case_id'] for c in pilot['cases']), 20_000_000, 30, 500,
        1_000_000, 'a'*64, 'b'*64, 'synthetic retention', 7)


def _scope():
    root = Path('external/clinsql_official')
    pilot = verify_pilot_cases(Path('data/clinsql/pilot_5_validation_development_v1.json'), root)
    manifest = json.loads(Path('data/schema/manifests/mimiciv_3_1_20261112T143303Z.json').read_text())
    index = SchemaIndex.load(Path('data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json'), manifest)
    return root, pilot, manifest, index


def test_plan_selects_only_five_development_cases_without_network():
    root, pilot, _, _ = _scope()
    assert pilot == select_pilot_cases(root)
    assert len({c['domain'] for c in pilot['cases']}) == 5
    assert [c['difficulty'] for c in pilot['cases']].count('hard_level_queries') == 1
    preview = plan()
    assert preview['mode'] == 'PLAN_ONLY' and preview['openai_requests_sent'] == 0
    assert preview['bigquery_patient_queries_executed'] == 0
    assert all(c['input_token_upper_bound'] > 0 for c in preview['cases'])


def test_cot_response_output_cap_matches_locked_source():
    source = Path('external/clinsql_official/model_inference/clinical_sql_benchmark_evaluator_CoT.py')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    methods = [node for node in ast.walk(tree)
               if isinstance(node, ast.FunctionDef)
               and node.name == '_generate_sql_openai_responses']
    assert len(methods) == 1
    caps = [keyword.value.value for node in ast.walk(methods[0])
            if isinstance(node, ast.Call) for keyword in node.keywords
            if keyword.arg == 'max_output_tokens'
            and isinstance(keyword.value, ast.Constant)]
    draft = json.loads(Path('docs/PHASE_C1_API_BUDGET_DRAFT.json').read_text())
    assert caps == [draft['max_output_tokens_per_call']] == [2048]


def test_cot_prompt_only_rebinds_source_dataset_project_from_manifest():
    _, _, manifest, _ = _scope()
    schema_text = '\n'.join(row['ddl'] for row in schema_records_from_manifest(manifest))
    native_generation = _source_function('prompt_utils', 'build_generation_prompt')(
        'Synthetic question', schema_text)
    native_refinement = _source_function('prompt_utils', 'build_refinement_prompt')(
        'Synthetic question', 'SELECT 1', 'redacted syntax error', schema_text)
    expected = lambda text: text.replace('physionet-data.mimiciv_3_1_hosp',
                                        'kltn-text-to-sql.mimiciv_3_1_hosp').replace(
                                        'physionet-data.mimiciv_3_1_icu',
                                        'kltn-text-to-sql.mimiciv_3_1_icu')
    assert generation_prompt('Synthetic question', schema_text) == expected(native_generation)
    assert refinement_prompt('Synthetic question', schema_text, 'SELECT 1',
                             'redacted syntax error') == expected(native_refinement)
    assert 'physionet-data' not in generation_prompt('Synthetic question', schema_text)


def test_cot_refines_guard_rejected_catalog_without_executing_it():
    from ehrqa.text2sql.interfaces import Execution
    bad = 'SELECT x FROM `physionet-data.mimiciv_3_1_hosp.patients`'
    good = 'SELECT 1 AS n'
    class Model:
        prompts = []
        def complete(self, stage, prompt):
            self.prompts.append((stage, prompt))
            return {'content': f'```sql\n{bad if stage == "generate" else good}\n```',
                    'usage': {}}
    class Database:
        executed = []
        def dry_run(self, sql):
            if sql.rstrip(';') == bad:
                raise SecurityRejected('Outside allowlist')
        def execute(self, sql):
            self.executed.append(sql)
            return Execution(('n',), ((1,),), True)
    model, database = Model(), Database()
    outcome = ClinSQLCoT(model, database, 'CREATE TABLE patients (`n` INT64)').run(
        'synthetic/easy/001', 'Synthetic question')
    assert outcome.status == 'executed'
    assert [sql.rstrip(';') for sql in database.executed] == [good]
    assert [stage for stage, _ in model.prompts] == ['generate', 'refine_1']
    assert 'fully qualified tables' in model.prompts[1][1]


def test_source_aligned_cot_rejects_historical_cap_and_ignores_reasoning_override(monkeypatch):
    monkeypatch.setenv('OPENAI_REASONING_EFFORT', 'medium')
    with pytest.raises(ValueError, match='2048'):
        _profile_request_settings(SOURCE_ALIGNED_NEXT_RUN, {'max_output_tokens_per_call': 8192})
    assert _profile_request_settings(SOURCE_ALIGNED_NEXT_RUN, {'max_output_tokens_per_call': 2048}) == {
        'max_output_tokens': 2048, 'reasoning_effort': None}
    assert _run_root('a' * 64, profile=SOURCE_ALIGNED_NEXT_RUN) != _run_root(
        'a' * 64, profile=HISTORICAL_PILOT)


def test_source_aligned_cot_does_not_refine_a_guard_rejection():
    calls = []

    def complete(stage, prompt):
        calls.append(stage)
        return {'content': '```sql\nSELECT 1\n```'}

    def dry_run(sql):
        raise SecurityRejected('Outside allowlist')

    pipeline = ClinSQLCoT(SimpleNamespace(complete=complete), SimpleNamespace(dry_run=dry_run),
                          'CREATE TABLE patients (n INT64)', refine_guard_rejections=False)
    with pytest.raises(SecurityRejected):
        pipeline.run('synthetic', 'Synthetic question')
    assert calls == ['generate']


def test_dry_run_budget_error_carries_estimate_without_patient_rows():
    from ehrqa.text2sql.logging import MeteredDatabase, RunLog
    class FakeClient:
        def dry_run(self, sql, *, timeout_seconds):
            return 8297536531
    records = [{'table': 'patients', 'dataset': 'mimiciv_3_1_hosp',
                'ddl': 'CREATE TABLE `kltn-text-to-sql.mimiciv_3_1_hosp.patients` '
                       '(`subject_id` INT64)'}]
    database = BigQueryAdapter(
        FakeClient(), records, Limits(268435456),
        allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',))
    log = RunLog('synthetic', 'clinsql_cot')
    metered = MeteredDatabase(database, log)
    with pytest.raises(BudgetExceeded) as error:
        metered.dry_run('SELECT subject_id FROM '
                        '`kltn-text-to-sql.mimiciv_3_1_hosp.patients`')
    assert error.value.estimated_bytes == 8297536531
    assert log.events[-1]['estimated_bytes'] == 8297536531
    assert 'rows' not in log.events[-1]


def test_mac_source_pruning_threshold_and_unmentioned_tables_retained():
    _, _, manifest, _ = _scope()
    schema = Schema.from_records(schema_records_from_manifest(manifest), dialect='bigquery')
    assert _native_pruning_needed(schema)
    rendered = _selected_schema_text(schema, {'patients': ['subject_id']})
    assert 'mimiciv_3_1_hosp.admissions' in rendered
    assert 'mimiciv_3_1_hosp.patients' in rendered
    tiny = Schema.from_records([{'table': 'x', 'ddl': 'CREATE TABLE x (`id` INT64)'}],
                               dialect='bigquery')
    assert not _native_pruning_needed(tiny)


def test_mac_selector_column_fill_order_matches_source():
    names = tuple('abcdefgh')
    ddl = 'CREATE TABLE x (\n' + ',\n'.join(f'  `{n}` STRING' for n in names) + '\n)'
    schema = Schema.from_records([{'table': 'x', 'ddl': ddl}], dialect='bigquery')
    rendered = _selected_schema_text(schema, {'x': ['h']})
    assert [part.split('`')[1] for part in rendered.splitlines() if part.startswith('  `')] == [
        'h', 'a', 'b', 'c', 'd', 'e']


def test_mac_bird_schema_layout_matches_source_method_on_synthetic_columns():
    import ast
    from pathlib import Path

    path = Path('external/mac_sql_official/core/agents.py')
    tree = ast.parse(path.read_text(encoding='utf-8'))
    selector = next(node for node in tree.body
                    if isinstance(node, ast.ClassDef) and node.name == 'Selector')
    method = next(node for node in selector.body
                  if isinstance(node, ast.FunctionDef) and
                  node.name == '_build_bird_table_schema_list_str')
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), 'exec'), namespace)
    native = namespace[method.name]
    columns = [('subject_id', 'subject id', ''), ('anchor_age', 'anchor age', '')]
    values = [('subject_id', ''), ('anchor_age', '')]
    expected = native(object(), 'patients', columns, values).strip()
    record = {
        'table': 'patients',
        'ddl': 'CREATE TABLE patients (`subject_id` INT64, `anchor_age` INT64)',
        'column_descriptions': {col: {'full_name': label} for col, label, _ in columns},
    }
    schema = Schema.from_records([record], dialect='bigquery')
    assert _bird_schema_text(schema, {}, records=[record]).strip() == expected


def test_sde_native_three_vote_selects_last_modified_sql():
    class Model:
        def __init__(self, votes):
            self.votes = votes
        def generate(self, stage, prompt, *, n):
            assert stage == 'sde.judge' and n == 3
            assert 'SELECT 1' in prompt and 'column_a' in prompt
            return [{'content': json.dumps(vote)} for vote in self.votes]
    votes = [{'Modification': 'True', 'Final SQL': 'SELECT 2'},
             {'Modification': 'False'},
             {'Modification': 'True', 'Final SQL': 'SELECT 3'}]
    result = native_three_vote_judge(Model(votes), question='synthetic question',
                                     sql='SELECT 1', evidence='',
                                     result_columns=('column_a',))
    assert result == {'sql': 'SELECT 3', 'modification_votes': 2, 'modified': True}
    votes[2] = {'Modification': 'False'}
    assert native_three_vote_judge(Model(votes), question='synthetic question',
                                   sql='SELECT 1', evidence='',
                                   result_columns=('column_a',))['sql'] == 'SELECT 1'


def test_openai_transport_serialization_usage_and_ambiguous_failure(tmp_path):
    sql = 'SELECT 1'
    calls = []
    class FakeResponses:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(status='completed', output_text=sql,
                                   model='gpt-5-mini-2025-08-07', id='resp-synthetic',
                                   usage=SimpleNamespace(input_tokens=50, output_tokens=10))
    provider = OpenAIModelProvider(_budget(tmp_path), client=SimpleNamespace(responses=FakeResponses()))
    output = provider.complete('generate', 'Original CLINSQL prompt')
    assert output['content'] == sql and output['usage'] == {'prompt_tokens': 50,
                                                              'completion_tokens': 10,
                                                              'reasoning_tokens': 0}
    assert calls[0]['input'] == [{'role': 'user', 'content': [
        {'type': 'input_text', 'text': 'Original CLINSQL prompt'}]}]
    assert calls[0]['model'] == 'gpt-5-mini-2025-08-07' and calls[0]['store'] is False
    assert provider.ledger.snapshot()['calls'] == 1
    class FailingResponses:
        def create(self, **_): raise TimeoutError('synthetic timeout')
    failing = OpenAIModelProvider(_budget(tmp_path / 'failure'),
                                  client=SimpleNamespace(responses=FailingResponses()))
    with pytest.raises(AmbiguousModelRequest) as ambiguous:
        failing.complete('generate', 'Prompt')
    assert ambiguous.value.cause_type == 'TimeoutError'
    assert ambiguous.value.http_status is None
    assert failing.ledger.snapshot()['pending'] == 1
    with pytest.raises(NotImplementedError):
        provider.generate('sde.generate', 'Prompt', n=9)
    class IncompleteResponses:
        def create(self, **_):
            return SimpleNamespace(status='incomplete', output_text='',
                                   model='gpt-5-mini-2025-08-07',
                                   usage=SimpleNamespace(input_tokens=5, output_tokens=8))
    incomplete = OpenAIModelProvider(_budget(tmp_path / 'incomplete'),
                                     client=SimpleNamespace(responses=IncompleteResponses()))
    with pytest.raises(ModelGenerationFailure) as incomplete_error:
        incomplete.complete('generate', 'Prompt')
    assert incomplete_error.value.usage == {'prompt_tokens': 5,
                                            'completion_tokens': 8,
                                            'reasoning_tokens': 0}
    assert incomplete.ledger.snapshot()['pending'] == 0


def test_openai_transport_pins_snapshot_reasoning_and_usage(tmp_path):
    captured = []
    class Responses:
        def create(self, **kwargs):
            captured.append(kwargs)
            return SimpleNamespace(status='completed', output_text='SELECT 1',
                                   model='gpt-5-mini-2025-08-07', id='synthetic-response',
                                   usage=SimpleNamespace(
                                       input_tokens=17, output_tokens=20,
                                       output_tokens_details=SimpleNamespace(reasoning_tokens=8)))
    provider = OpenAIModelProvider(_budget(tmp_path),
                                   model_id='gpt-5-mini-2025-08-07',
                                   reasoning_effort='medium',
                                   client=SimpleNamespace(responses=Responses()))
    result = provider.complete('synthetic', 'Question')
    assert captured[0]['reasoning'] == {'effort': 'medium'}
    assert captured[0]['store'] is False
    assert result['model_snapshot'] == 'gpt-5-mini-2025-08-07'
    assert result['usage']['reasoning_tokens'] == 8


def test_api_budget_persists_and_stops_before_second_call(tmp_path):
    ledger = _budget(tmp_path, calls=1)
    reservation = ledger.reserve(stage='generate', prompt='abc', output_cap=2048)
    with pytest.raises(PermissionError, match='budget'):
        PersistentAPIBudgetLedger(tmp_path / 'api.sqlite', ledger.budget).reserve(
            stage='refine', prompt='abc', output_cap=2048)
    ledger.reconcile(reservation, input_tokens=5, output_tokens=7)
    assert ledger.snapshot()['pending'] == 0


def test_november_unlimited_policy_has_no_usd_cap_but_expires_and_locks(tmp_path):
    budget = PilotAPIBudget(1, 1000, 512, None, Decimal('0.25'),
                            Decimal('2.00'), 'UNLIMITED_RESEARCH_NOV_2026')
    budget.verify_active(datetime(2026, 10, 31, 17, 0, tzinfo=timezone.utc))
    with pytest.raises(PermissionError, match='expired'):
        budget.verify_active(datetime(2026, 11, 30, 17, 0, tzinfo=timezone.utc))
    ledger = PersistentAPIBudgetLedger(tmp_path / 'research.sqlite', budget)
    ledger.reserve(stage='synthetic', prompt='abc', output_cap=512)
    assert ledger.snapshot()['policy'] == 'UNLIMITED_RESEARCH_NOV_2026'
    with pytest.raises(PermissionError, match='lock'):
        PersistentAPIBudgetLedger(tmp_path / 'research.sqlite',
                                  PilotAPIBudget(2, 1000, 512, None,
                                                 Decimal('0.25'), Decimal('2.00'),
                                                 'UNLIMITED_RESEARCH_NOV_2026'))


def test_dotenv_loader_preserves_process_precedence_and_ignores_legacy(tmp_path):
    dotenv = tmp_path / '.env'
    dotenv.write_text('OPENAI_API_KEY=synthetic-secret\n'
                      'OPENAI_MODEL=gpt-5-mini-2025-08-07\n'
                      'BQ_LOCATION=US\nDB_PASS=not-for-research\n', encoding='utf-8')
    env = {'OPENAI_MODEL': 'already-locked'}
    load_research_env(dotenv, env)
    assert env['OPENAI_MODEL'] == 'already-locked'
    assert env['OPENAI_API_KEY'] == 'synthetic-secret'
    assert env['BQ_LOCATION'] == 'US' and 'DB_PASS' not in env


def test_pilot_batch_runs_pinned_order_and_refuses_interrupted_replay(tmp_path, monkeypatch):
    from ehrqa.cli import phase_c1_pilot as cli
    root, pilot, manifest, index = _scope()
    questions, _ = load_official_questions(root)
    monkeypatch.setattr(cli, 'ROOT', tmp_path)
    monkeypatch.setattr(cli, '_run_root', lambda *_, **_kwargs: tmp_path / 'results/phase_c1_runs')
    monkeypatch.setattr(cli, '_load_scope', lambda: (pilot, manifest, index))
    monkeypatch.setattr(cli, 'load_official_questions', lambda _: (questions, []))
    monkeypatch.setattr(cli.BenchmarkExecutionApproval, 'from_file',
                        lambda _: SimpleNamespace(
                            approval_id='synthetic', verify_pilot=lambda _: None,
                            verify_active=lambda: None))
    calls = []
    def fake_execute(case_id, **_):
        calls.append(case_id)
        return {'status': 'sql_error' if len(calls) == 3 else 'executed'}
    monkeypatch.setattr(cli, 'execute_one', fake_execute)
    budget = tmp_path / 'synthetic.json'
    budget.write_text('{}', encoding='utf-8')
    output = execute_batch(approval_path=budget, api_budget_path=budget,
                           sql_budget_path=budget)
    assert calls == [row['case_id'] for row in pilot['cases']]
    assert output['case_count'] == 5
    assert output['completed'][2]['status'] == 'sql_error'
    first = tmp_path / 'results/phase_c1_runs' / (calls[0].replace('/', '__') + '.started')
    first.parent.mkdir(parents=True)
    first.write_text('synthetic', encoding='utf-8')
    with pytest.raises(FileNotFoundError, match='Interrupted'):
        execute_batch(approval_path=budget, api_budget_path=budget,
                      sql_budget_path=budget)
    assert len(calls) == 5


def test_phase_a_approval_cannot_be_reused_and_case_scope_is_exact():
    _, pilot, manifest, _ = _scope()
    approval = _approval(pilot, manifest)
    approval.verify_pilot(pilot)
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp',
                            'mimiciv_3_1_icu', 'US', 'kltn-text-to-sql')
    approval.authorize(case_id=pilot['cases'][0]['case_id'], sql='SELECT 1', config=config,
                       manifest=manifest, max_bytes_billed=20_000_000,
                       timeout_seconds=30, max_rows=501, max_result_bytes=1_000_000)
    with pytest.raises(PermissionError):
        approval.authorize(case_id='outside/validation/999', sql='SELECT 1',
                           config=config, manifest=manifest, max_bytes_billed=20_000_000,
                           timeout_seconds=30, max_rows=501)
    with pytest.raises(ValueError):
        BenchmarkExecutionApproval.from_file(Path('docs/PHASE_A_APPROVAL_DRAFT.json'))


def test_bigquery_real_transport_contract_marks_result_byte_cap_incomplete(monkeypatch):
    _, pilot, manifest, _ = _scope()
    class QueryJobConfig:
        def __init__(self, **kwargs): self.__dict__.update(kwargs)
    bigquery = ModuleType('google.cloud.bigquery')
    bigquery.QueryJobConfig = QueryJobConfig
    monkeypatch.setitem(sys.modules, 'google.cloud.bigquery', bigquery)
    monkeypatch.setattr('ehrqa.clinsql.bigquery_client.verify_reader_adc', lambda: object())
    monkeypatch.setattr('ehrqa.clinsql.bigquery_client.verify_reader_credentials', lambda _: None)
    class Job:
        total_bytes_processed = 1000
        total_bytes_billed = 1000
        job_id = 'synthetic-job'
        schema = [SimpleNamespace(name='n', field_type='INT64')]
        def result(self, **_):
            class Rows:
                schema = Job.schema
                total_rows = 3
                def __iter__(self):
                    return iter([SimpleNamespace(values=lambda n=n: {'n': n}.values())
                                 for n in (1, 2, 3)])
            return Rows()
        def cancel(self): pass
    class FakeClient:
        _credentials = object()
        def query(self, sql, *, job_config, **_):
            return Job()
    config = BigQueryConfig('kltn-text-to-sql', 'mimiciv_3_1_hosp',
                            'mimiciv_3_1_icu', 'US', 'kltn-text-to-sql')
    transport = BigQueryClient(config, client=FakeClient(), allow_data_execution=True,
                               schema_manifest=manifest, execution_approval=_approval(pilot, manifest))
    adapter = BigQueryAdapter(transport, schema_records_from_manifest(manifest),
                              Limits(20_000_000, max_rows=500, max_result_bytes=5,
                                     allow_data_execution=True, case_id=pilot['cases'][0]['case_id']),
                              allowed_datasets=config.allowed_datasets)
    sql = 'SELECT subject_id AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients`'
    result = adapter.execute(sql)
    assert not result.complete and result.rows == ((1,),)
    assert result.column_types == ('INT64',) and result.job_id == 'synthetic-job'
    with pytest.raises(PermissionError):
        adapter.execute('DELETE FROM `kltn-text-to-sql.mimiciv_3_1_hosp.patients` WHERE TRUE')


def test_evaluation_staging_uses_native_pandas_csv_format(tmp_path):
    import pandas as pd
    from ehrqa.text2sql.interfaces import Execution
    question = Question('Labs/easy/001', 'validation', 'Labs', 'easy', 'synthetic')
    source = tmp_path / 'benchmark/data/splits/validation/Labs/easy/001'
    source.mkdir(parents=True)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (source / name).write_text('{}', encoding='utf-8')
    rows = ((1, None), (1, None), (2, Decimal('1.25')))
    result = Execution(('n', 'value'), rows, True)
    staged = prepare_official_sample(tmp_path / 'out', tmp_path / 'benchmark',
                                     question, 'SELECT n,value FROM synthetic', result)
    expected = pd.DataFrame(rows, columns=('n', 'value')).to_csv(index=False)
    assert (staged / 'result_001.csv').read_bytes().decode('utf-8') == expected
    assert len(pd.read_csv(staged / 'result_001.csv')) == 3


def test_pilot_artifact_retention_requires_expiry_and_hash(tmp_path):
    runs, restricted = tmp_path / 'runs', tmp_path / 'restricted'
    runs.mkdir(); restricted.mkdir()
    artifact = restricted / 'pilot_synthetic.json'
    artifact.write_text('{"synthetic":true}', encoding='utf-8')
    import hashlib
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    now = datetime.now(timezone.utc)
    (runs / 'case.json').write_text(json.dumps({'events': [{
        'stage': 'result_artifact', 'artifact_id': 'pilot_synthetic',
        'sha256': digest, 'artifact_expires_at_utc':
        (now + timedelta(days=7)).isoformat()}]}), encoding='utf-8')
    kwargs = {'verify_acl': lambda _: True}
    assert inspect_or_delete_expired(runs, restricted, now=now, **kwargs)[0]['status'] == 'NOT_DUE'
    due = now + timedelta(days=8)
    assert inspect_or_delete_expired(runs, restricted, now=due, **kwargs)[0]['status'] == 'DUE_MANUAL_DELETION'
    assert inspect_or_delete_expired(runs, restricted, now=due, delete_expired=True,
                                     **kwargs)[0]['status'] == 'DELETED'
    assert not artifact.exists()
    assert inspect_or_delete_expired(runs, restricted, now=due, **kwargs)[0]['status'] == 'ALREADY_DELETED'


def test_real_cot_contract_with_fake_clients_and_restricted_artifact(tmp_path):
    root, pilot, manifest, index = _scope()
    questions, _ = load_official_questions(root)
    question = next(q for q in questions if q.query_id == pilot['cases'][0]['case_id'])
    sql = 'SELECT COUNT(*) AS n FROM `kltn-text-to-sql.mimiciv_3_1_hosp.admissions`'
    class FakeResponses:
        def create(self, **_):
            return SimpleNamespace(status='completed', output_text=f'```sql\n{sql}\n```',
                                   model='gpt-5-mini-2025-08-07', id='resp-synthetic',
                                   usage=SimpleNamespace(input_tokens=600, output_tokens=50))
    class FakeBigQueryClient:
        def dry_run(self, sql, **_): return 1000
        def execute(self, sql, **_):
            return {'columns': ['n'], 'column_types': ['INT64'], 'rows': [(1,), (None,)],
                    'total_rows': 2, 'bytes_billed': 1000,
                    'job_id': 'synthetic-job', 'latency_seconds': 0.1}
    records = schema_records_from_manifest(manifest)
    database = BigQueryAdapter(FakeBigQueryClient(), records,
                               Limits(20_000_000, max_rows=500, allow_data_execution=True),
                               allowed_datasets=('kltn-text-to-sql.mimiciv_3_1_hosp',
                                                 'kltn-text-to-sql.mimiciv_3_1_icu'))
    store_root = tmp_path / 'restricted'
    store_root.mkdir()
    store = ResultArtifactStore(store_root, verify_private_acl=lambda _: True)
    model = OpenAIModelProvider(_budget(tmp_path),
                                client=SimpleNamespace(responses=FakeResponses()))
    output = run_real_cot_case(question, pilot_manifest=pilot,
                               approval=_approval(pilot, manifest), model=model,
                               database=database, schema_index=index, result_store=store,
                               output_root=tmp_path / 'runs', model_id='gpt-5-mini-2025-08-07',
                               pricing=Pricing(.25, 2), code_commit='synthetic')
    assert output['status'] == 'executed' and output['artifact']['row_count'] == 2
    assert store.load(output['artifact']['artifact_id'],
                      expected_sha256=output['artifact']['sha256']).rows == ((1,), (None,))
    saved = json.loads(Path(output['log_path']).read_text())
    assert all(event.get('rows') is None for event in saved['events'])
    assert saved['summary']['api_calls'] == 1
    resumed = load_real_cot_checkpoint(question, pilot_manifest=pilot,
                                       schema_index=index, output_root=tmp_path / 'runs')
    assert resumed['sql'] == output['sql'] and resumed['usage']['api_calls'] == 1
    with pytest.raises(FileExistsError):
        run_real_cot_case(question, pilot_manifest=pilot,
                          approval=_approval(pilot, manifest), model=model,
                          database=database, schema_index=index, result_store=store,
                          output_root=tmp_path / 'runs', model_id='gpt-5-mini-2025-08-07',
                          pricing=Pricing(.25, 2))
