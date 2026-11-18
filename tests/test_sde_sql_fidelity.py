"""Exercise SDE routing and source parity with synthetic SQL and transports."""
from collections import defaultdict

import pytest

from ehrqa.clinsql.baselines import sde_sql
from ehrqa.clinsql.chat_multi_provider import OpenAIChatMultiProvider
from ehrqa.clinsql.execution_errors import BudgetExceeded, IncompleteResultError, SecurityRejected
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.source_templates import isolated_function
from ehrqa.text2sql.interfaces import ProbePresence


def source(file, function):
    return isolated_function('sde_sql_official', f'src/{file}.py', function)


def result(*rows):
    return Execution(('n',), rows, True)


def test_exploration_feedback_matches_native_groups_and_order():
    first = {'Base': ['SELECT 1 ASC LIMIT 1'], 'Condition': ['SELECT 2']}
    second = {'Combined 1': 'SELECT 3'}
    calls = []

    def execute(sql, _):
        calls.append(sql)
        return {'data': [] if sql == 'SELECT 2' else [(None,)]}

    stages = [source('explore_new', name) for name in
              ('first_stages_probe_sqls', 'second_stages_probe_sqls')]
    for stage in stages:
        stage.__globals__['execute_sql'] = execute
    expected_first = stages[0](first, 'synthetic')
    expected_all = expected_first + stages[1](second, 'synthetic')
    model = MockLLM({'sde.explore1': ['invalid', '```json\n{"Base":["SELECT 1 ASC LIMIT 1"],'
                                               '"Condition":["SELECT 2"]}\n```'],
                     'sde.explore2': [second]})
    db = MockBigQuery([], results={'SELECT 2': result()})
    attempts = []
    actual = sde_sql.SDESQL(model, db).probe_before_generation(
        'question with SQLite literal', 'synthetic schema', '', '', attempts)
    assert actual == expected_all
    assert [sql for stage, sql in db.calls if stage == 'probe'] == calls
    assert expected_first in model.calls[-1]['prompt']
    assert 'question with SQLite literal' in model.calls[0]['prompt']
    assert model.calls[0]['prompt'] == model.calls[1]['prompt']


def test_saved_exploration_and_probe_replay_without_model_or_database(tmp_path):
    db = MockBigQuery([])
    model = MockLLM({'sde.explore1': [{'Base': ['SELECT 1']}],
                    'sde.explore2': [{'Combined': 'SELECT 2'}]})
    settings = dict(exploration_checkpoint=tmp_path, saved_probe=('SELECT 1', ProbePresence(287_504)))
    first = sde_sql.SDESQL(model, db, **settings).probe_before_generation('q', 'schema', '', '', [])
    assert [sql for op, sql in db.calls if op == 'probe'] == ['SELECT 2']
    empty_model = MockLLM({})
    again = sde_sql.SDESQL(empty_model, db, **settings).probe_before_generation('q', 'schema', '', '', [])
    assert first == again and 'SELECT 1: 【Not NULL】' in again
    assert not empty_model.calls


@pytest.mark.parametrize('stage', ['sde.explore1', 'sde.explore2'])
def test_invalid_probe_response_stops_after_bounded_retries(stage):
    replies = {'sde.explore1': [{'Base': ['SELECT 1']}], stage: ['{}'] * 7}
    model = MockLLM(replies)
    with pytest.raises(ValueError, match='retry limit'):
        sde_sql.SDESQL(model, MockBigQuery([])).run('question', schema_text='schema')
    assert [call['stage'] for call in model.calls].count(stage) == 7
    assert all(call['stage'] != 'sde.generate' for call in model.calls)


def test_consistency_counts_each_occurrence_and_preserves_nested_types():
    candidates = ['same SQL', 'first tied result', 'same SQL', 'last', 'empty']
    a = (None, [1, 2], {'field': [None], 'other': 3})
    b = (None, [2, 1], {'field': [None], 'other': 3})
    reordered = (None, [1, 2], {'other': 3, 'field': [None]})
    results = [result(a, b, a), result(b), result(b), result(b, reordered), result()]
    assert sde_sql._most_consistent(candidates, results) == 'same SQL'
    assert sde_sql._freeze({'a': 1}) != sde_sql._freeze([['a', 1]])
    assert sde_sql._freeze([1, 2]) != sde_sql._freeze([2, 1])


def test_scalar_consistency_matches_native_result_set_selection():
    candidates = ['a', 'b', 'a', 'c', 'd']
    rows = [[(None,), (1,), (1,)], [(2,)], [(2,)], [(1,), (None,)], []]
    iterator = iter(rows)
    native = source('uils', 'find_most_consistent_sql')
    native.__globals__.update(defaultdict=defaultdict, run_sql_1=None,
                              func_timeout=lambda *args, **kwargs: next(iterator))
    assert sde_sql._most_consistent(candidates, [result(*data) for data in rows]) == native(candidates, 'db')


def workflow(**extra):
    return MockLLM({'sde.explore1': [{'Base': ['SELECT 1']}],
                    'sde.explore2': [{'Combined': 'SELECT 2'}],
                    'sde.generate': ['SELECT 3'] * 9, **extra})


def test_chat_provider_rejects_synthetic_database():
    transport = OpenAIChatMultiProvider(None, client=object())
    with pytest.raises(PermissionError, match='MockBigQuery'):
        sde_sql.SDESQL(transport, MockBigQuery([]))


def test_chat_provider_requires_explicit_probe_feedback_scope():
    transport = OpenAIChatMultiProvider(None, client=object())
    with pytest.raises(PermissionError, match='separate authorization'):
        sde_sql.SDESQL(transport, object())


def test_selected_sql_reexecutes_and_refinement_sees_only_first_five():
    class Database(MockBigQuery):
        def execute(self, sql):
            self.calls.append(('execute', sql))
            if sql == 'SELECT 3' and self.calls.count(('execute', sql)) == 10:
                return Execution(('verified',), ((1,),) * 5 + ((None,),), True, job_id='rerun')
            return result((9,))

    model = workflow(**{'sde.judge': [{'Modification': 'False'}] * 3})
    db = Database([])
    output = sde_sql.SDESQL(model, db).run('question', schema_text='schema')
    assert db.calls.count(('execute', 'SELECT 3')) == 10
    assert output['result'].job_id == 'rerun' and len(output['result'].rows) == 6
    assert "['verified']" in model.calls[-1]['prompt']


def test_empty_diagnosis_success_without_subqueries_does_not_call_search(monkeypatch):
    monkeypatch.setattr(sde_sql, 'timed_bigquery_get_subsqls', lambda _: [])
    model = workflow(**{'sde.refine_probes': [{'Fix': 'SELECT 4'}], 'sde.refine': ['SELECT 5']})
    db = MockBigQuery([], results={'SELECT 3': result()})
    output = sde_sql.SDESQL(model, db).run('question', schema_text='schema')
    assert output['sql'] == 'SELECT 5' and output['result'].complete
    assert [a['phase'] for a in output['attempts'] if a['stage'] == 'probe'] == ['explore1', 'explore2', 'fix']
    assert '1. SELECT 4: 【Not NULL】' in model.calls[-1]['prompt']
    assert not {'sde.search_probes', 'sde.judge'} & {c['stage'] for c in model.calls}


def test_decomposition_error_routes_search_diagnosis_fix_and_final_sql(monkeypatch):
    def cannot_decompose(_):
        raise ValueError('synthetic unsupported syntax')

    monkeypatch.setattr(sde_sql, 'timed_bigquery_get_subsqls', cannot_decompose)
    model = workflow(**{'sde.search_probes': [{'Diagnosis': 'SELECT 4'}],
                        'sde.refine_probes': [{'Fix': 'SELECT 5'}],
                        'sde.refine': ['```sql\nSELECT 6\n```']})
    db = MockBigQuery([], results={'SELECT 3': result(), 'SELECT 4': result()})
    output = sde_sql.SDESQL(model, db).run('question', schema_text='schema')
    assert output['sql'] == 'SELECT 6'
    assert [c['stage'] for c in model.calls[-3:]] == ['sde.search_probes', 'sde.refine_probes', 'sde.refine']
    assert '1. SELECT 4: 【NULL】' in model.calls[-2]['prompt']
    assert '1. SELECT 5: 【Not NULL】' in model.calls[-1]['prompt']


def test_judge_modified_sql_has_no_result_even_if_seen_as_candidate():
    modified = 'SELECT 4'
    model = workflow(**{'sde.judge': ['malformed', {'Modification': 'True', 'Final SQL': 'SELECT 5'},
                                     {'Modification': 'True', 'Final SQL': modified}]})
    model.responses['sde.generate'][-1] = modified
    db = MockBigQuery([], results={modified: result((4,)), 'SELECT 3': result((3,))})
    output = sde_sql.SDESQL(model, db).run('question', schema_text='schema')
    assert output['sql'] == modified and output['status'] == 'judge_modified_unexecuted'
    assert output['result'] is None
    assert db.calls.count(('execute', modified)) == 1


@pytest.mark.parametrize('error', [TimeoutError, BudgetExceeded, PermissionError])
def test_infrastructure_failure_propagates_without_refining(error):
    class Database(MockBigQuery):
        def dry_run(self, sql):
            if sql == 'SELECT 3':
                raise error('synthetic failure')
            return super().dry_run(sql)

    model = workflow()
    with pytest.raises(error):
        sde_sql.SDESQL(model, Database([])).run('question', schema_text='schema')
    assert model.calls[-1]['stage'] == 'sde.generate'


@pytest.mark.parametrize('sql', ['SELECT 1', 'SELECT 3', 'SELECT 4'])
def test_incomplete_results_stop_probes_candidates_and_refinement(sql):
    model = workflow(**{'sde.refine_error': ['SELECT 4']})
    db = MockBigQuery([], results={sql: Execution(('x',), ((1,),), False)},
                      failures={'SELECT 3': 'invalid'} if sql == 'SELECT 4' else {})
    with pytest.raises(IncompleteResultError):
        sde_sql.SDESQL(model, db).run('question', schema_text='schema')


def test_guard_error_refines_without_submitting_rejected_sql():
    class Database(MockBigQuery):
        def dry_run(self, sql):
            if sql == 'SELECT 3':
                raise SecurityRejected('private error')
            return super().dry_run(sql)

    model = workflow(**{'sde.refine_error': ['SELECT 4']})
    db = Database([])
    output = sde_sql.SDESQL(model, db).run('question', schema_text='schema')
    assert output['status'] == 'executed' and output['sql'] == 'SELECT 4'
    assert ('execute', 'SELECT 3') not in db.calls
    assert 'read-only guard' in model.calls[-1]['prompt']
    assert 'private error' not in model.calls[-1]['prompt']


def test_known_guard_message_is_returned_as_feedback():
    class Database(MockBigQuery):
        def dry_run(self, sql):
            if sql == 'SELECT 3':
                raise SecurityRejected('SQL references a table outside the approved BigQuery datasets')
            return super().dry_run(sql)

    model = workflow(**{'sde.refine_error': ['SELECT 4']})
    output = sde_sql.SDESQL(model, Database([])).run('question', schema_text='schema')
    assert output['status'] == 'executed'
    assert 'outside the approved BigQuery datasets' in model.calls[-1]['prompt']
