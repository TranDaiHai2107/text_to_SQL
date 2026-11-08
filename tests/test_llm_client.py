import json

import httpx
import pytest

import llm_client


@pytest.mark.parametrize("provider,host,token_field", [
    ("deepseek", "api.deepseek.com", "max_tokens"),
    ("openai", "api.openai.com", "max_completion_tokens"),
])
def test_provider_request_without_network(monkeypatch, provider, host, token_field):
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", provider)
    monkeypatch.setattr(llm_client, "LLM_MODEL", "test-model")
    monkeypatch.setenv(provider.upper() + "_API_KEY", "fake-test-key")
    monkeypatch.delenv("OPENAI_REASONING_EFFORT", raising=False)

    def handler(request):
        body = json.loads(request.content)
        assert request.url.host == host
        assert request.url.path == ("/v1/chat/completions" if provider == "openai" else "/chat/completions")
        assert body[token_field] == 123
        assert body["model"] == "test-model"
        if provider == "deepseek":
            assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json={"choices": [{"message": {"content": " SELECT 1 "}, "finish_reason": "stop"}]})

    assert llm_client.call_llm([], 123, transport=httpx.MockTransport(handler)) == "SELECT 1"


def test_auth_failure_not_retried_or_leaked(monkeypatch):
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_client, "LLM_MODEL", "test-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-test-key")
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(401, text="fake-test-key")

    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        llm_client.call_llm([], transport=httpx.MockTransport(handler))
    assert "fake-test-key" not in str(error.value)
    assert len(calls) == 1


def test_truncated_sql_is_not_accepted(monkeypatch):
    monkeypatch.setattr(llm_client, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(llm_client, "LLM_MODEL", "test-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fake-test-key")
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
        "choices": [{"message": {"content": "SELECT * FROM"}, "finish_reason": "length"}]}))
    with pytest.raises(RuntimeError, match="truncated"):
        llm_client.call_llm([], transport=transport)
