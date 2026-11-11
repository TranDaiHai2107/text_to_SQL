import asyncio

import httpx
import pytest

from ehrqa.agentic.transport import post_json


def test_total_deadline_cancels_an_unfinished_request():
    cancelled=[]
    async def slow(request):
        try:
            await asyncio.sleep(5)
            return httpx.Response(200,json={'ok':True})
        finally:cancelled.append(True)
    with pytest.raises(TimeoutError):
        post_json('https://example.invalid',{}, {},timeout_s=.02,transport=httpx.MockTransport(slow))
    assert cancelled


def test_gateway_keeps_unknown_cost_and_does_not_retry_after_deadline(tmp_path,monkeypatch):
    from ehrqa.agentic.gateway import Gateway,ModelSettings,ModelError
    from ehrqa.agentic.budget import Budget
    monkeypatch.setenv('OPENAI_API_KEY','fake-test')
    calls=[]
    async def slow(request):
        calls.append(request)
        await asyncio.sleep(5)
    budget=Budget(tmp_path/'timeout.sqlite',1,.125,.5)
    gateway=Gateway(ModelSettings('openai','gpt-6-luna',request_timeout_s=.02),
                    transport=httpx.MockTransport(slow),budget=budget)
    with pytest.raises(ModelError,match='deadline'):gateway.complete('select',[],100)
    assert len(calls)==1
    summary=budget.summary()
    assert summary['upper_or_reserved_USD']>0
    assert summary['states']==[('reserved_unknown',1)]
