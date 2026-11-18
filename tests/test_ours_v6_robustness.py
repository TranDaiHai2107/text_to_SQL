"""Ours v6 robustness: deterministic linker normalization and bounded transport retries."""
import json
from types import SimpleNamespace

import pytest

from ehrqa.agentic import contracts
from ehrqa.clinsql import openai_provider
from ehrqa.clinsql.openai_provider import AmbiguousModelRequest, OpenAIModelProvider
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import build_pipeline
from ehrqa.clinsql.benchmark_model import BENCHMARK_LLM

RECORDS = [{'table': name, 'ddl': ddl} for name, ddl in (
    ('patients', 'CREATE TABLE `d.h.patients` (subject_id INT64, gender STRING, anchor_age INT64)'),
    ('admissions', 'CREATE TABLE `d.h.admissions` (subject_id INT64, hadm_id INT64)'),
)]
Q = 'For an 87-year-old woman: among female patients aged 82-92, how many admissions?'


def schema():
    return build_pipeline(MockBigQuery(RECORDS), MockLLM({})).db.schema


def linker_output(**extra):
    obj = {'requirements': [
        {'id': 'r1', 'kind': 'population', 'span': 'female patients aged 82-92', 'description': 'cohort'},
        {'id': 'r2', 'kind': 'output', 'span': 'how many admissions?', 'description': 'count'}],
        'links': [], 'joins': [], 'ambiguities': []}
    obj.update(extra)
    return obj


def test_reference_patient_literal_is_covered_by_a_verbatim_requirement():
    s = schema()
    with pytest.raises(contracts.StageError, match='Uncovered question literal: 87'):
        contracts.linking(Q, linker_output(), s, [])
    obj, warnings = contracts.normalize_linking(Q, linker_output(), s, [])
    contracts.linking(Q, obj, s, [])
    added = obj['requirements'][-1]
    assert added['span'] == 'For an 87-year-old woman' and added['span'] in Q and added['id'] == 'r3'
    assert warnings and '87' in warnings[0]
    comma = 'For my 55-year-old male patient, among men aged 50-60, how many admissions?'
    out = linker_output()
    out['requirements'][0]['span'] = 'men aged 50-60'
    obj, _ = contracts.normalize_linking(comma, out, s, [])
    contracts.linking(comma, obj, s, [])


def test_non_preamble_literals_are_not_auto_covered():
    s = schema()
    obj, warnings = contracts.normalize_linking('How many admissions after 2150?', {
        'requirements': [{'id': 'r1', 'kind': 'output', 'span': 'How many admissions', 'description': 'n'}],
        'links': [], 'joins': [], 'ambiguities': []}, s, [])
    assert not warnings
    with pytest.raises(contracts.StageError, match='2150'):
        contracts.linking('How many admissions after 2150?', obj, s, [])


def test_qualified_names_empty_links_and_unsupported_joins_are_normalized():
    s = schema()
    out = linker_output(
        links=[{'requirement_id': 'r1', 'span': 'female', 'table': 'kltn-text-to-sql.mimiciv_3_1_hosp.patients',
                'column': 'gender', 'role': 'sex filter', 'catalog_id': 'missing'},
               {'requirement_id': 'r2', 'span': 'admissions', 'table': '', 'column': '', 'role': 'x'}],
        joins=[{'left': '`kltn-text-to-sql.mimiciv_3_1_hosp.admissions`.subject_id', 'right': 'patients.subject_id'},
               {'left': 'admissions.hadm_id', 'right': 'patients.anchor_age'}])
    obj, warnings = contracts.normalize_linking(Q, out, s, [])
    assert obj['links'][0]['table'] == 'patients' and obj['links'][0]['catalog_id'] is None
    assert len(obj['links']) == 1 and len(obj['joins']) == 1
    assert obj['joins'][0]['left'] == 'admissions.subject_id'
    assert any('dropped join' in w for w in warnings)


class _Flaky:
    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **_kwargs):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5, output_tokens_details=None),
                               output_text='{"ok":1}', id='resp_1', model=BENCHMARK_LLM, status='completed')


class _Ledger:
    def __init__(self):
        self.reserved, self.reconciled = 0, 0

    def reserve(self, **_kwargs):
        self.reserved += 1
        return f'r{self.reserved}'

    def reconcile(self, *_args, **_kwargs):
        self.reconciled += 1


def _http_error(cls, status):
    """An SDK exception instance without building an HTTP response object."""
    error = cls.__new__(cls)
    Exception.__init__(error, 'boom')
    error.status_code = status
    return error


def test_transient_errors_are_retried_with_a_new_reservation(monkeypatch):
    openai = pytest.importorskip('openai')
    monkeypatch.setattr(openai_provider, 'TRANSPORT_BACKOFF_SECONDS', (0,))
    client = _Flaky([_http_error(openai.RateLimitError, 429), _http_error(openai.InternalServerError, 503)])
    ledger = _Ledger()
    provider = OpenAIModelProvider(ledger, model_id=BENCHMARK_LLM, client=client, transport_retries=2)
    result = provider.complete('link', 'prompt')
    assert result['transport_retries'] == 2 and client.calls == 3
    # Failed attempts keep their reservations pending (charged at the cap).
    assert ledger.reserved == 3 and ledger.reconciled == 1


def test_request_errors_and_default_provider_never_retry(monkeypatch):
    openai = pytest.importorskip('openai')
    monkeypatch.setattr(openai_provider, 'TRANSPORT_BACKOFF_SECONDS', (0,))
    client = _Flaky([_http_error(openai.BadRequestError, 400)])
    with pytest.raises(AmbiguousModelRequest):
        OpenAIModelProvider(_Ledger(), model_id=BENCHMARK_LLM, client=client, transport_retries=2).complete('x', 'p')
    assert client.calls == 1
    client = _Flaky([_http_error(openai.RateLimitError, 429)])
    with pytest.raises(AmbiguousModelRequest):
        OpenAIModelProvider(_Ledger(), model_id=BENCHMARK_LLM, client=client).complete('x', 'p')
    assert client.calls == 1
