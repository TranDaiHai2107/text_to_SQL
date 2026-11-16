from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
from types import SimpleNamespace

import pytest

from ehrqa.clinsql.official_scorer_source import load_verified_native_scorer
from ehrqa.clinsql.dataset import Question
from ehrqa.clinsql.evaluator import prepare_official_sample
from ehrqa.clinsql.rubric_evaluation import LeafLedger, check_approval, create_scorer, evaluate_split
from ehrqa.clinsql.rubric_judge import ADAPTED, NATIVE, ChatJudge, JudgeConfig, JudgeIncomplete, parse_adapted_grade
from ehrqa.text2sql.interfaces import Execution


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'external/clinsql_official'
LOCK = ROOT / 'PAPER_SOURCE_LOCK.json'


def config(mode=ADAPTED):
    if mode == NATIVE:
        return JudgeConfig(mode, 'gpt-5-chat', 'https://test.openai.azure.com',
                           'gpt-5-chat', '1', '2', 'synthetic')
    return JudgeConfig(mode, 'synthetic-2026-01-01', 'https://api.openai.com/v1',
                       'synthetic-2026-01-01', '1', '2', 'synthetic')


def node(name, *children, **kwargs):
    return {'id': name, 'requirements': f'<{name}>', 'sub_tasks': list(children), **kwargs}


def sample(tmp_path, rubric):
    path = tmp_path / 'validation/domain/easy_level_queries/001'
    path.mkdir(parents=True)
    files = {'query_001.txt': 'Synthetic question', 'sql_001.sql': 'SELECT 1',
             'result_001.csv': 'value\n1\n1\n', 'sql_rubric_tree.json': json.dumps(rubric),
             'results_rubric_tree.json': json.dumps(rubric)}
    for name, body in files.items():
        (path / name).write_text(body, encoding='utf-8')
    return path


def adapter(tmp_path, callback, max_calls=100):
    callback.config = config()
    ledger = LeafLedger(tmp_path / 'attempts.sqlite', max_calls=max_calls)
    return create_scorer(SOURCE, LOCK, callback, ledger, scope='ours', authorize=lambda: None)


@pytest.mark.parametrize(('rubric', 'grades', 'expected'), [
    (node('root', node('a', critical=True), node('b')), {'a': 1, 'b': 1}, 1),
    (node('root', node('a', critical=True), node('b')), {'a': 0, 'b': 1}, 0),
    (node('root', node('a', critical=True), node('b', weight=2), node('c')), {'a': 1, 'b': 0, 'c': 1}, 1/3),
    (node('root', node('a'), node('b', critical=True, weight=3), node('c'), sequential=True),
     {'a': 1, 'b': 0, 'c': 1}, 1/4),
    (node('root', node('a', node('b'), node('c', weight=3), weight=2), node('d')),
     {'b': 1, 'c': 0, 'd': 1}, 1/2),
])
def test_native_parity_and_resume(tmp_path, rubric, grades, expected):
    path = sample(tmp_path, rubric)
    prompts, native_prompts = [], []

    def response(prompt):
        grade, = (grade for name, grade in grades.items() if f'<{name}>' in prompt)
        return f'Score: {grade}\nExplanation: synthetic'

    def transport(prompt):
        prompts.append(prompt)
        return response(prompt), {'input_tokens': 10}

    def azure(prompt):
        native_prompts.append(prompt)
        return response(prompt)

    native = object.__new__(load_verified_native_scorer(SOURCE, LOCK))
    native._call_azure = azure
    reference = native.score_sample(path)
    scorer, module = adapter(tmp_path, transport)
    result = scorer.score_sample(path)
    assert reference == result
    assert result.sql_score == result.results_score == expected
    assert prompts == native_prompts and len(prompts) == 2 * len(grades)

    @contextmanager
    def staged():
        yield path

    scorer, module = adapter(tmp_path, transport)
    report = evaluate_split(scorer, module, {'domain/easy_level_queries/001': staged},
                            method='ours', split='validation', judge_config=transport.config)
    assert len(prompts) == 2 * len(grades)
    assert report['score_labels'][1] == 'ADAPTED_CLINSQL_EXECUTION_SCORE'
    assert report['summary']['average_sql_score'] == round(expected, 6)
    assert report['summary']['difficulty_breakdown']['easy']['total_samples'] == 1
    assert report['domains'][0]['average_results_score'] == round(expected, 6)


def test_sql_only_grade_uses_native_tree_without_any_result_cells(tmp_path):
    path = sample(tmp_path, node('root', node('critical', critical=True), node('other')))
    (path / 'result_001.csv').write_text('column\nprivate-result-sentinel\n', encoding='utf-8')
    prompts = []

    def transport(prompt):
        prompts.append(prompt)
        return 'Score: 1\nExplanation: synthetic', {}

    scorer, _ = adapter(tmp_path, transport)
    assert scorer.score_sql_without_results(path) == 1
    assert len(prompts) == 2
    assert all('Evaluation target: sql' in prompt and 'SELECT 1' in prompt for prompt in prompts)
    assert all('results rows' not in prompt and 'private-result-sentinel' not in prompt for prompt in prompts)
    assert scorer.score_sql_without_results(path) == 1
    assert len(prompts) == 2


def test_adapted_judge_can_omit_output_cap_without_changing_native_defaults():
    original = config()
    uncapped = replace(original, adapted_max_completion_tokens=None)
    assert uncapped.parameters() == {'store': False}
    assert original.sha256 != uncapped.sha256
    assert config(NATIVE).parameters() == {'max_completion_tokens': 1024, 'temperature': 0.2}


@pytest.mark.parametrize('response', [
    'Score: 1.0\nExplanation: first line\nsecond line',
    '**Score:** 1\n**Explanation:** synthetic',
    '```json\n{"score":1,"explanation":"synthetic"}\n```',
    '{"Score": 1}\n{"Explanation": "synthetic"}',
])
def test_adapted_judge_parses_explicit_formatted_grade(response):
    assert parse_adapted_grade(response)[0] == 1


@pytest.mark.parametrize('response', [
    'failure code 1', 'Score: 1\nExplanation: ambiguous\nScore: 0',
    '{"score":0,"score":1,"explanation":"ambiguous"}',
])
def test_adapted_judge_rejects_ambiguous_grade(response):
    with pytest.raises(JudgeIncomplete):
        parse_adapted_grade(response)


def test_reparse_saved_invalid_response_without_submitting_a_new_request(tmp_path):
    path = tmp_path / 'attempts.sqlite'
    ledger = LeafLedger(path, max_calls=1, retry_limit=1, retain_invalid_response=True)

    def authorize():
        pass

    with pytest.raises(JudgeIncomplete):
        ledger.grade('leaf', {}, 'prompt', lambda _: ('{"Score": 1}\n{"Explanation": "synthetic"}', {}),
                     authorize=authorize)

    def no_request(_):
        pytest.fail('A saved judge response can be parsed locally')

    replay = LeafLedger(path, max_calls=1, retry_limit=1, retain_invalid_response=True,
                        grade_parser=parse_adapted_grade)
    assert replay.grade('leaf', {}, 'prompt', no_request, authorize=authorize) == (1, 'synthetic')


@pytest.mark.parametrize('invalid', [None, '', 'error 1', 'Score: 2\nExplanation: invalid',
                                     'Score: 1\nExplanation:', RuntimeError('network')])
def test_invalid_judge_never_becomes_score(tmp_path, invalid):
    path = sample(tmp_path, node('root'))

    def transport(prompt):
        if isinstance(invalid, Exception):
            raise invalid
        return invalid, {'input_tokens': 10}

    scorer, module = adapter(tmp_path, transport)
    with pytest.raises(JudgeIncomplete):
        scorer.score_sample(path)
    with pytest.raises(JudgeIncomplete, match='UNRESOLVED_OR_TERMINAL'):
        scorer.score_sample(path)
    with sqlite3.connect(tmp_path / 'attempts.sqlite') as db:
        assert db.execute('SELECT score FROM attempts').fetchall() == [(None,)]


@pytest.mark.parametrize('missing', ['sql_001.sql', 'result_001.csv'])
def test_missing_artifact_fails_before_judging(tmp_path, missing):
    path = sample(tmp_path, node('root'))
    (path / missing).unlink()
    scorer, _ = adapter(tmp_path, lambda prompt: pytest.fail('judge called'))
    with pytest.raises(JudgeIncomplete, match='MISSING_OR_AMBIGUOUS'):
        scorer.score_sample(path)


def test_bounded_429_retry_and_budget(tmp_path, monkeypatch):
    monkeypatch.setattr('ehrqa.clinsql.rubric_evaluation.time.sleep', lambda _: None)
    calls = []

    class RateLimit(Exception):
        status_code = 429

    def transport(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            raise RateLimit
        return 'Score: 1\nExplanation: valid', {}

    scorer, _ = adapter(tmp_path, transport, max_calls=2)
    with pytest.raises(JudgeIncomplete, match='BUDGET_EXHAUSTED'):
        scorer.score_sample(sample(tmp_path, node('root')))
    assert len(calls) == 2


@pytest.mark.parametrize('mode', [NATIVE, ADAPTED])
def test_transport_parameters_and_preflight(mode):
    cfg = config(mode)
    payloads = []

    def completion(**kwargs):
        payloads.append(kwargs)
        choice = SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content='Score: 1\nExplanation: ok'))
        return SimpleNamespace(model=cfg.response_model, id='mock', choices=[choice],
                               usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3))

    client = SimpleNamespace(models=SimpleNamespace(retrieve=lambda model: SimpleNamespace(id=model)),
                             chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    judge = ChatJudge(cfg, client=client)
    with pytest.raises(JudgeIncomplete, match='PREFLIGHT_REQUIRED'):
        judge('synthetic')
    assert judge.verify()['estimated_cost_usd'] == '0.000008'
    assert payloads[0]['model'] == cfg.model and payloads[0]['max_completion_tokens'] == 1024
    assert payloads[0].get('temperature') == (0.2 if mode == NATIVE else None)
    if mode == ADAPTED:
        assert payloads[0]['store'] is False


def test_native_csv_types_and_duplicates(tmp_path):
    case_id = 'domain/easy_level_queries/001'
    benchmark = tmp_path / 'benchmark'
    sample(benchmark / 'data/splits', node('root'))
    columns = ('label', 'missing', 'amount', 'array', 'structure')
    row = ('x', None, Decimal('1234567890.123456789'), [1, 2], {'a': 1})
    question = Question(case_id, 'validation', 'domain', 'easy_level_queries', 'Synthetic')
    target = prepare_official_sample(tmp_path / 'stage', benchmark, question, 'SELECT 1',
                                     Execution(columns, (row, row), True))
    csv = (target / 'result_001.csv').read_text()
    assert str(row[2]) in csv
    native = object.__new__(load_verified_native_scorer(SOURCE, LOCK))
    first, second = native._load_sample_files(target)['test_results']
    assert tuple(first) == columns
    assert first['missing'] != first['missing']  # pandas NaN
    assert first['array'] == second['array'] == '[1, 2]'
    assert first['structure'] == second['structure'] == "{'a': 1}"
    assert first['amount'] == second['amount'] and str(first['amount']) != str(row[2])


def test_missing_case_does_not_publish_aggregate_or_zero(tmp_path):
    path = sample(tmp_path, node('root'))
    scorer, module = adapter(tmp_path, lambda prompt: ('Score: 0\nExplanation: synthetic failure', {}))

    @contextmanager
    def staged():
        yield path

    @contextmanager
    def missing():
        raise FileNotFoundError
        yield

    report = evaluate_split(scorer, module, {'domain/easy_level_queries/001': staged,
                                            'domain/easy_level_queries/002': missing},
                            method='ours', split='validation', judge_config=config())
    assert report['status'] == 'INCOMPLETE' and report['summary'] is None
    assert report['cases']['domain/easy_level_queries/001']['ADAPTED_CLINSQL_SQL_SCORE'] == 0
    assert report['cases']['domain/easy_level_queries/002'] == {'status': 'INCOMPLETE',
                                                              'reason': 'STAGING_UNAVAILABLE'}


def test_approval_requires_exact_bound_scope():
    cfg = config()
    approval = {'judge_config_sha256': cfg.sha256, 'manifest_sha256': 'manifest', 'source_sha256': 'source',
                'send_complete_result_rows': True, 'max_leaf_requests': 110, 'approved_by': 'synthetic',
                'policy_reference': 'synthetic', 'expires_at_utc': '2099-01-01T00:00:00+00:00'}
    check_approval(approval, config=cfg, manifest_hash='manifest', source_hash='source')
    with pytest.raises(JudgeIncomplete):
        check_approval(approval, config=cfg, manifest_hash='different', source_hash='source')
