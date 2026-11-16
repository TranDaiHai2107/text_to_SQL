import json
from types import SimpleNamespace as NS

import pytest

from ehrqa.agentic.contracts import StageError
from ehrqa.clinsql.benchmark_model import BENCHMARK_LLM, ModelMismatch
from ehrqa.clinsql.chat_multi_provider import MACSQLChatProvider, OpenAIChatMultiProvider
from ehrqa.clinsql.evidence_router import EvidenceRouter, RestrictedEvidenceEgress, classify_ours_catalog
from ehrqa.clinsql.linking_format import LINK_SCHEMA, validate_link_format
from ehrqa.clinsql.openai_provider import OpenAIModelProvider
from ehrqa.clinsql.proposed_runner import ProposedModelProvider


@pytest.mark.parametrize('provider', [OpenAIModelProvider, MACSQLChatProvider,
                                      OpenAIChatMultiProvider, ProposedModelProvider])
def test_benchmark_provider_rejects_fallback_before_inference(provider):
    with pytest.raises(ModelMismatch, match='MODEL_MISMATCH'):
        provider(None, client=object(), model_id='qwen')
    assert provider(None, client=object()).model_id == BENCHMARK_LLM


def test_retired_router_and_restricted_requests_fail_before_reserving_tokens():
    with pytest.raises(ModelMismatch):
        EvidenceRouter('ours', NS(model_id=BENCHMARK_LLM), NS(model_id='qwen'))
    with pytest.raises(RestrictedEvidenceEgress, match='column-value samples'):
        MACSQLChatProvider(None, client=object()).complete('mac.selector', 'Column. Value examples: [x]')
    with pytest.raises(RestrictedEvidenceEgress, match='clinical dictionary'):
        ProposedModelProvider(None, client=object()).complete(
            'link', [{'role': 'user', 'content': '{"catalog": [{"id": "fixture"}]}'}], None)


def test_mac_source_chat_retains_native_single_user_message():
    requests = []
    usage = NS(prompt_tokens=8, completion_tokens=6)
    response = NS(model=BENCHMARK_LLM, id='fixture', usage=usage, choices=[
        NS(index=0, finish_reason='stop', message=NS(content='SELECT 1'))])

    def create(**kwargs):
        requests.append(kwargs)
        return response

    ledger = NS(reserve=lambda **_: 'request', reconcile=lambda *_, **__: None)
    client = NS(chat=NS(completions=NS(create=create)))
    provider = MACSQLChatProvider(ledger, client=client)
    assert provider.generate('mac.transport_synthetic', 'Return exactly: SELECT 1')[0]['content'] == 'SELECT 1'
    payload, = requests
    assert payload['messages'] == [{'role': 'user', 'content': 'Return exactly: SELECT 1'}]
    assert payload['model'] == BENCHMARK_LLM and payload['n'] == 1
    assert not {'temperature', 'top_p', 'reasoning_effort', 'max_completion_tokens'} & payload.keys()


def test_ours_classifies_static_dictionary_separately_from_observations():
    item = {'table': 'd_icd_diagnoses', 'code': 'synthetic', 'label': 'fixture',
            'code_column': 'icd_code', 'column': 'long_title', 'match': 'lexical_candidate'}
    assert classify_ours_catalog([item]) == 'MIMIC-IV static clinical dictionary records'
    assert classify_ours_catalog([{**item, 'subject_id': 0}]) == 'patient-specific observations'
    assert classify_ours_catalog([{**item, 'unknown': 'fixture'}]) == 'unverified clinical dictionary payload'


def test_schema_link_requests_strict_json_and_keeps_ordinary_payload_eligible():
    calls = []
    valid = {'requirements': [], 'links': [], 'joins': [], 'ambiguities': []}

    class Ledger:
        def reserve(self, **kwargs):
            assert kwargs['transport'] == ('openai.responses', BENCHMARK_LLM)
            return 'fixture'

        def reconcile(self, *args, **kwargs):
            pass

    def create(**kwargs):
        calls.append(kwargs)
        return NS(model=BENCHMARK_LLM, status='completed', output_text=json.dumps(valid),
                  usage=NS(input_tokens=8, output_tokens=6))

    provider = ProposedModelProvider(Ledger(), client=NS(responses=NS(create=create)))
    result = provider.complete('link', [{'role': 'user', 'content': '{"catalog": []}'}], None)
    validate_link_format(json.loads(result['content']))
    fmt = calls[0]['text']['format']
    assert fmt['strict'] and fmt['schema'] == LINK_SCHEMA and calls[0]['model'] == BENCHMARK_LLM
    with pytest.raises(StageError, match='Link JSON format'):
        validate_link_format({**valid, 'links': 'patient.admission'})
    with pytest.raises(StageError, match='Link JSON format'):
        validate_link_format({k: v for k, v in valid.items() if k != 'joins'})
