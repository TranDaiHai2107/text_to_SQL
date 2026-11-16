"""SDE transport contract tests with a fake Chat Completions client."""
from decimal import Decimal
import hashlib
import json
import sqlite3
from types import SimpleNamespace as NS

import pytest

from ehrqa.clinsql.chat_multi_provider import OpenAIChatMultiProvider
from ehrqa.clinsql.openai_provider import AmbiguousModelRequest, ModelGenerationFailure
from ehrqa.clinsql.pilot_api_budget import PersistentAPIBudgetLedger, PilotAPIBudget
from ehrqa.text2sql.logging import MeteredModel, Pricing, RunLog


MODEL = 'gpt-5-mini-2025-08-07'


def _ledger(tmp_path):
    budget = PilotAPIBudget(3, 10000, 2000, Decimal('1'),
                            Decimal('0.25'), Decimal('2'))
    return PersistentAPIBudgetLedger(tmp_path / 'sde_api.sqlite', budget)


class FakeChatClient:
    def __init__(self, *, failure=False, finish_reason='stop'):
        self.calls = []
        self.failure = failure
        self.finish_reason = finish_reason
        self.chat = NS(completions=NS(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise TimeoutError('synthetic transport failure')
        n = kwargs['n']
        return NS(id='chatcmpl-synthetic', model=MODEL,
                  usage=NS(prompt_tokens=20, completion_tokens=10 * n,
                           completion_tokens_details=NS(reasoning_tokens=n)),
                  choices=[NS(index=i, finish_reason=self.finish_reason,
                              message=NS(content=f'SELECT {i}')) for i in range(n)])


@pytest.mark.parametrize('n', [3, 9])
def test_sde_multi_choice_single_request_single_usage_event(tmp_path, n):
    ledger = _ledger(tmp_path)
    client = FakeChatClient()
    provider = OpenAIChatMultiProvider(ledger, client=client,
                                      max_completion_tokens=64)
    log = RunLog('synthetic', 'sde', Pricing(0.25, 2))
    replies = MeteredModel(provider, log).generate('sde.generate', 'Synthetic SQL prompt', n=n)

    assert [item['content'] for item in replies] == [f'SELECT {i}' for i in range(n)]
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request['n'] == n and request['store'] is False
    assert request['model'] == MODEL and request['reasoning_effort'] == 'medium'
    assert request['messages'][0]['content'] == 'You are a helpful SQL assistant.'
    assert 'temperature' not in request and 'top_p' not in request
    assert ledger.snapshot()['calls'] == 1 and ledger.snapshot()['pending'] == 0
    summary = log.summary()
    assert summary['api_calls'] == 1
    assert summary['input_tokens'] == 20 and summary['output_tokens'] == 10 * n
    assert summary['reasoning_tokens'] == n
    assert log.events[0]['choices'] == n
    with sqlite3.connect(ledger.path) as db:
        stage, route, model, raw_receipt, response_hash = db.execute(
            'SELECT stage,provider,model_id,metadata,response_sha256 FROM api_calls '
            'JOIN request_transport USING(id) JOIN request_receipt USING(id)').fetchone()
    receipt = json.loads(raw_receipt)
    assert (stage, route, model) == ('sde.generate', 'openai.chat.completions', MODEL)
    assert receipt['endpoint'] == 'https://api.openai.com/v1/chat/completions'
    assert receipt['parameters']['n'] == n
    assert 'messages' not in receipt['parameters']
    assert response_hash == hashlib.sha256(json.dumps(
        [item['content'] for item in replies], ensure_ascii=False).encode()).hexdigest()


def test_transport_exception_keeps_pending_budget_without_retry(tmp_path):
    ledger = _ledger(tmp_path)
    client = FakeChatClient(failure=True)
    provider = OpenAIChatMultiProvider(ledger, client=client,
                                      max_completion_tokens=64)
    with pytest.raises(AmbiguousModelRequest):
        provider.generate('sde.judge', 'Synthetic prompt', n=3)
    assert len(client.calls) == 1
    assert ledger.snapshot()['calls'] == 1 and ledger.snapshot()['pending'] == 1


def test_incomplete_choices_fail_after_accounting_for_usage(tmp_path):
    ledger = _ledger(tmp_path)
    client = FakeChatClient(finish_reason='length')
    provider = OpenAIChatMultiProvider(ledger, client=client,
                                      max_completion_tokens=64)
    with pytest.raises(ModelGenerationFailure, match='Incomplete'):
        provider.generate('sde.generate', 'Synthetic prompt', n=9)
    assert ledger.snapshot()['calls'] == 1 and ledger.snapshot()['pending'] == 0


def test_unlimited_research_omits_request_token_cap_and_keeps_request_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(PilotAPIBudget, 'verify_active', lambda self: None)
    budget = PilotAPIBudget(1, None, None, None, Decimal('0.25'), Decimal('2'),
                            'UNLIMITED_RESEARCH_NOV_2026')
    ledger = PersistentAPIBudgetLedger(tmp_path / 'uncapped.sqlite', budget)
    client = FakeChatClient()
    provider = OpenAIChatMultiProvider(ledger, client=client, max_completion_tokens=None)
    provider.generate('sde.explore1', 'Synthetic prompt')
    assert 'max_completion_tokens' not in client.calls[0]
    assert ledger.snapshot()['output_charged_tokens'] == 10
    with pytest.raises(PermissionError, match='budget exceeded'):
        provider.generate('sde.explore1', 'Synthetic prompt')


def test_metered_model_rejects_empty_choice_list():
    model = NS(generate=lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match='no choices'):
        MeteredModel(model, RunLog('synthetic', 'sde')).generate('sde.generate', 'p', n=9)


def test_grouped_nine_uses_three_requests_and_preserves_choice_order(tmp_path):
    class GroupedClient(FakeChatClient):
        def create(self, **kwargs):
            response = super().create(**kwargs)
            response.id += str(len(self.calls))
            return response

    client = GroupedClient()
    ledger = _ledger(tmp_path)
    provider = OpenAIChatMultiProvider(ledger, client=client,
                                     max_completion_tokens=64, group_nine=True)
    log = RunLog('synthetic', 'sde')
    choices = MeteredModel(provider, log).generate('sde.generate', 'example', n=9)
    assert [call['n'] for call in client.calls] == [3, 3, 3]
    assert [row['choice_index'] for row in choices] == [0, 1, 2] * 3
    assert log.summary()['api_calls'] == ledger.snapshot()['calls'] == 3
    assert log.summary()['output_tokens'] == 90
