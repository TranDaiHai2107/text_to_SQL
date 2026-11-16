"""Source parity and BigQuery sampler tests without network access."""
import ast
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
from types import SimpleNamespace
import time

import pytest

from ehrqa.agentic.schema import Schema
from ehrqa.clinsql.baselines.mac_sampling import (
    column_sample_queries, format_examples, missing_sample_columns, recover_examples, sample_column_values,
)
from ehrqa.clinsql.baselines.mac_sql import MACSQL, _bird_schema_text, _chosen_columns, _fk_text, _selector_response, _sql
from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.source_templates import constant


CORE = Path(__file__).resolve().parents[1] / 'external/mac_sql_official/core'
RECORD = {'table': 'x', 'dataset': 'hosp',
          'ddl': 'CREATE TABLE `demo.hosp.x` (id INT64, label STRING, age INT64, event_date DATE)'}


def source_methods(filename, cls, names, namespace):
    tree = ast.parse((CORE / filename).read_text(encoding='utf-8'))
    source = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == cls)
    methods = [node for node in source.body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=methods, type_ignores=[]), filename, 'exec'), namespace)
    return namespace


def source_utility(name, **namespace):
    path = CORE / 'utils.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    # The source defines parse_json twice. Python dispatches to its last definition.
    function = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name][-1]
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


@pytest.mark.parametrize('reply', [
    '{"x":"drop_all"}',
    '```json\n{"x": ["label"], "y": "invalid"}\n```',
    '```json\n{"x":"drop_all"}\n```\n```json\n{"x":"keep_all"}\n```',
    '```json\n{"x": ["label"], "unknown": "keep_all"}\n```',
])
def test_selector_parser_uses_native_first_fence_and_whole_response_validation(reply):
    validate = source_utility('check_selector_response', Dict=dict, print=lambda *args: None)
    parse = source_utility('parse_json', json=json, check_selector_response=validate,
                           print=lambda *args: None)
    assert _selector_response(reply) == parse(reply)


@pytest.mark.parametrize('reply', ['```SQL\nSELECT 1\n```', '```sql```',
                                    '```sql\nSELECT 1\n```\n```sql\nSELECT 2\n```'])
def test_sql_extraction_uses_native_last_case_sensitive_fence(reply):
    assert _sql(reply) == source_utility('parse_sql_from_string', re=re)(reply)


@pytest.mark.parametrize('values', [
    ['alias+tag@example.invalid', 'fictional label'],
    ['alias@example.invalid\n', 'fictional label'],
    ['2030-02-01 12:00:00', '2030-02-02 12:00:00', None],
    ['2030-99-01', '2030-02-01'],
    ['', ' \t', 'literal SQLite', None],
    ['https://example.invalid', 'fictional label'],
])
def test_port_sample_filters_match_source(values):
    date = source_utility('is_valid_date', re=re)
    dates = source_utility('is_valid_date_column', is_valid_date=date)
    email = source_utility('is_email', re=re)
    native = source_methods('agents.py', 'Selector', {'_get_value_examples_str'},
                            dict(List=list, is_valid_date_column=dates, is_email=email))
    source_format = native['_get_value_examples_str']
    selector = SimpleNamespace(dataset_name='bird')
    expected = source_format(selector, values, 'TEXT')
    assert format_examples(values, 'STRING') == expected

    class Rows:
        total_rows = len(values)

        def __iter__(self):
            yield from ((value,) for value in values)

    assert recover_examples(Rows(), 'STRING', max_rows=len(values)) == expected


def test_selector_and_decomposer_render_same_source_prompts_for_matching_context():
    def template(name):
        return constant('mac_sql_official', 'core/const.py', name)

    question = 'Count synthetic labels'
    record = dict(RECORD, ddl='CREATE TABLE x (a INT64, b INT64, c INT64, d INT64, '
                              'e INT64, f INT64, label STRING)')
    schema = Schema.from_records([record], dialect='bigquery')
    shown = _bird_schema_text(schema, {}, records=[record])
    captured = []

    def model_call(prompt, **kwargs):
        captured.append(prompt)
        return '```sql\nSELECT COUNT(label) FROM x\n```'

    namespace = dict(LLM_API_FUC=model_call, extract_world_info=lambda _message: {})
    prune = source_methods('agents.py', 'Selector', {'_prune'},
                           {**namespace, 'selector_template': template('selector_template'),
                            'parse_json': lambda _reply: {}})['_prune']
    prune(SimpleNamespace(_message={}), 'mimic_iv_3_1', question, shown, '', '')
    talk = source_methods('agents.py', 'Decomposer', {'talk'},
                          {**namespace, 'decompose_template_bird': template('decompose_template_bird'),
                           'parse_sql_from_string': source_utility('parse_sql_from_string', re=re),
                           'REFINER_NAME': 'Refiner'})['talk']
    talk(SimpleNamespace(name='Decomposer', dataset_name='bird'),
         {'send_to': 'Decomposer', 'query': question, 'evidence': '', 'desc_str': shown, 'fk_str': ''})
    model = MockLLM({'mac.selector': ['```json\n{}\n```'],
                     'mac.decomposer': ['```sql\nSELECT COUNT(label) FROM x\n```']})
    MACSQL(model, MockBigQuery([record]), value_evidence=lambda *_: '').run(question)
    assert [call['prompt'] for call in model.calls] == captured


def test_refiner_adapts_only_static_dialect_text_and_keeps_input_evidence():
    template = constant('mac_sql_official', 'core/const.py', 'refiner_template')
    captured = []

    def reply(prompt, **kwargs):
        captured.append(prompt)
        return '```sql\nSELECT 2\n```'

    native = source_methods('agents.py', 'Refiner', {'_refine'}, {
        'refiner_template': template.replace('SQLite', 'BigQuery'),
        'add_prefix': source_utility('add_prefix'),
        'extract_world_info': lambda _: {}, 'LLM_API_FUC': reply,
        'parse_sql_from_string': source_utility('parse_sql_from_string', re=re),
    })['_refine']
    question, description = 'Find the literal SQLite', 'Value examples: SQLite'
    error = {'sql': 'SELECT 1', 'sqlite_error': 'BigQuery rejected the SQL; details withheld',
             'exception_class': 'ValueError'}
    assert native(SimpleNamespace(_message={}), question, '', description, '', error) == 'SELECT 2'
    db = MockBigQuery([], failures={'SELECT 1': 'fixture error'})
    model = MockLLM({'mac.refiner': ['```sql\nSELECT 2\n```']})
    port = MACSQL(model, db, value_evidence=lambda *_: '')
    port._refiner_turn({'final_sql': 'SELECT 1'}, question, '', description, '', [])
    assert model.calls[0]['prompt'] == captured[0]


@pytest.mark.parametrize('outcome', ['success', 'exhausted', 'parser_error'])
def test_chat_manager_source_rounds_and_refiner_state(outcome):
    constants = dict(MAX_ROUND=3, SYSTEM_NAME='System', SELECTOR_NAME='Selector', REFINER_NAME='Refiner')
    native = source_methods('chat_manager.py', 'ChatManager', {'start', '_chat_single_round'},
                            {**constants, 'time': time})
    refiner = source_methods('agents.py', 'Refiner', {'talk', '_is_need_refine'},
                             {**constants, 'FunctionTimedOut': TimeoutError})
    queries = [f'SELECT {i}' for i in range(4)]
    first = 'error: No SQL found in the input string' if outcome == 'parser_error' else queries[0]
    rows = {sql: ([] if i == 0 or outcome == 'exhausted' else [(i,)]) for i, sql in enumerate(queries)}
    expected_calls = []

    def execute(sql, _db_id):
        expected_calls.append(sql)
        return {'sql': sql, 'data': rows[sql], 'sqlite_error': '', 'exception_class': ''}

    corrections = iter(queries[1:])
    agent = SimpleNamespace(name='Refiner', dataset_name='bird', _execute_sql=execute,
                            _refine=lambda *args: next(corrections))
    agent._is_need_refine = lambda result: refiner['_is_need_refine'](agent, result)
    agent.talk = lambda message: refiner['talk'](agent, message)
    group = [
        SimpleNamespace(name='Selector', talk=lambda msg: msg.update(send_to='Decomposer')),
        SimpleNamespace(name='Decomposer', talk=lambda msg: msg.update(send_to='Refiner', final_sql=first, fixed=False)),
        agent,
    ]
    manager = SimpleNamespace(chat_group=group)
    manager._chat_single_round = lambda msg: native['_chat_single_round'](manager, msg)
    expected = {'send_to': 'System'}
    native['start'](manager, expected)

    reply = 'unparseable' if outcome == 'parser_error' else f'```sql\n{first}\n```'
    model = MockLLM({'mac.decomposer': [reply], 'mac.refiner': [f'```sql\n{s}\n```' for s in queries[1:]]})
    db = MockBigQuery([RECORD], results={sql: Execution(('n',), tuple(data), True) for sql, data in rows.items()})
    output = MACSQL(model, db, value_evidence=lambda *_: '').run('Synthetic question')
    assert [sql for stage, sql in db.calls if stage == 'execute'] == expected_calls
    assert {key: output['message'][key] for key in expected} == expected
    assert output['message']['qa_pairs'] == reply
    assert output['status'] == {'success': 'executed', 'exhausted': 'corrected_unexecuted',
                                'parser_error': 'generation_failure'}[outcome]


def test_selector_source_drop_order_completion_and_descriptions():
    methods = source_methods('agents.py', 'Selector', {'_get_db_desc_str', '_build_bird_table_schema_list_str'},
                             {'deepcopy': deepcopy, 'List': list})
    cols = [(c, c, 'description' if c == 'h' else '') for c in 'abcdefgh']
    values = [(c, '') for c in 'abcdefgh']
    info = {'desc_dict': {'x': cols}, 'value_dict': {'x': values},
            'pk_dict': {'x': ['g']}, 'fk_dict': {'x': []}}
    native = SimpleNamespace(db2infos={'db': info})
    native._build_bird_table_schema_list_str = lambda *args: methods['_build_bird_table_schema_list_str'](native, *args)
    records = [{'table': 'x', 'primary_keys': ['g'], 'ddl': 'CREATE TABLE x (' +
                ', '.join(f'{c} INT64' for c in 'abcdefgh') + ')',
                'column_descriptions': {'h': {'description': 'description'}}}]
    schema = Schema.from_records(records, dialect='bigquery')
    for choice in ({}, {'x': 'drop_all'}, {'x': ['h']}):
        desc, _, chosen = methods['_get_db_desc_str'](native, 'db', choice)
        assert _bird_schema_text(schema, choice, records=records) == desc
        assert _chosen_columns(schema, choice, {'x': {'g'}}) == chosen


def test_sampler_with_real_sql_guard_and_synthetic_client():
    class Client:
        def dry_run(self, sql, **kwargs):
            return 0

        def execute(self, sql, **kwargs):
            column = sql.split('`')[1]
            data = {'label': ['example', None], 'age': list(range(11)),
                    'event_date': ['2024-01-01', '2024-02-01']}[column]
            assert 'GROUP BY' in sql
            if column == 'age':
                assert 'ORDER BY COUNT(*) DESC' in sql and sql.endswith('LIMIT 11')
            elif column == 'event_date':
                assert 'sample_value IS NULL DESC, frequency DESC' in sql
                assert sql.endswith('LIMIT 2')
            else:
                assert 'LIMIT' not in sql and 'REGEXP_CONTAINS' not in sql
            return {'columns': [column], 'rows': [(value,) for value in data], 'total_rows': len(data)}

    db = BigQueryAdapter(Client(), [RECORD], Limits(100, allow_data_execution=True),
                         allowed_datasets=('demo.hosp',))
    schema = Schema.from_records([RECORD], dialect='bigquery')
    assert sample_column_values(db, schema, {}) == {
        'x': {'label': "[None, 'example']", 'age': '', 'event_date': "['2024-01-01']"}}
    with pytest.raises(PermissionError, match='synthetic transports'):
        MACSQL(MockLLM({}), db, value_evidence=lambda *_: '', sample_synthetic_values=True)


def test_synthetic_samples_are_available_to_the_agent():
    db = MockBigQuery([RECORD])
    model = MockLLM({'mac.decomposer': ['```sql\nSELECT 1\n```']})
    MACSQL(model, db, value_evidence=lambda *_: '', sample_synthetic_values=True).run('Example')
    assert 'Value examples:' in model.calls[0]['prompt']
    assert 'x: `demo.hosp.x`' in model.calls[0]['prompt']
    assert not any('SELECT `id`' in sql for _, sql in db.calls)


def test_saved_sample_recovery_preserves_null_and_first_temporal_value():
    class Rows:
        total_rows = 1700000

        def __iter__(self):
            yield ('2024-02-01',)
            yield (None,)
            pytest.fail('Presence of NULL and first value already known')

    assert recover_examples(Rows(), 'DATETIME', max_rows=1_000_000) == "[None, '2024-02-01']"


def test_source_sampler_never_reuses_legacy_filtered_string_job():
    record = dict(RECORD, ddl='CREATE TABLE `demo.hosp.x` (label STRING)')
    schema = Schema.from_records([record], dialect='bigquery')
    legacy = next(column_sample_queries(schema, {}, legacy=True))[3]
    exact = next(column_sample_queries(schema, {}))[3]
    lookup = []

    def recover(sql, kind):
        lookup.append(sql)
        assert sql != legacy
        return "['fixture+tag@example.invalid']"

    assert sample_column_values(object(), schema, {}, recover=recover, recover_bounded=recover) == {
        'x': {'label': "['fixture+tag@example.invalid']"}}
    assert lookup == [exact]
    assert missing_sample_columns(schema, {}, {sha256(legacy.encode()).hexdigest()}) == [('x', 'label')]
    assert missing_sample_columns(schema, {}, {sha256(exact.encode()).hexdigest()}) == []


def test_sample_frequency_column_groups_input_and_reuses_exact_bounded_sql():
    record = dict(RECORD, ddl='CREATE TABLE `demo.hosp.x` (frequency STRING)')
    schema = Schema.from_records([record], dialect='bigquery')
    saved = []

    def recover(sql, kind):
        assert kind == 'STRING'
        assert 'GROUP BY `frequency` ORDER BY COUNT(*) DESC' in sql
        saved.append(sql)
        return "['synthetic']"

    assert 'GROUP BY 1)' in next(column_sample_queries(schema, {}, legacy=True))[3]
    assert sample_column_values(object(), schema, {}, recover_bounded=recover) == {
        'x': {'frequency': "['synthetic']"},
    }
    assert len(saved) == 1


@pytest.mark.parametrize('reply', ['bad JSON', '```json\n{"x": ["label"]}\n```'])
def test_selector_response_routing(reply):
    record = dict(RECORD, ddl=RECORD['ddl'][:-1] + ', a INT64, b INT64, c INT64)')
    db = MockBigQuery([record])
    model = MockLLM({'mac.selector': [reply], 'mac.decomposer': ['```sql\nSELECT 1\n```']})
    output = MACSQL(model, db, value_evidence=lambda *_: '').run('Example')
    assert output['message']['pruned']
    assert output['selector'] == ({} if reply == 'bad JSON' else {'x': ['label']})
    assert output['status'] == 'executed'


def test_fk_text_keeps_both_declared_icd_join_columns_only():
    records = [{'table': name, 'ddl': f'CREATE TABLE {name} (icd_code STRING, icd_version INT64, label STRING)'}
               for name in ('diagnoses_icd', 'd_icd_diagnoses', 'unrelated')]
    schema = Schema.from_records(records, dialect='bigquery')
    assert set(_fk_text(schema).splitlines()) == {
        f'diagnoses_icd.`{column}` = d_icd_diagnoses.`{column}`'
        for column in ('icd_code', 'icd_version')}
