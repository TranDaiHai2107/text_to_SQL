import io
import json

import pytest

from ehrqa.clinsql.local_model import LocalModel, _stage_schema, _structured_instruction


def test_local_transport_only_uses_loopback_and_preserves_prompt(monkeypatch):
    requests, usage = [], []

    class Ledger:
        def reserve(self, **entry):
            return entry['stage']

        def reconcile(self, reservation, **counts):
            usage.append((reservation, counts))

    class HTTP:
        def open(self, request, **kwargs):
            requests.append(request)
            if isinstance(request, str):
                payload = {'data': [{'id': 'fixture'}]}
            else:
                payload = {'model': 'fixture', 'id': str(len(requests)),
                           'usage': {'prompt_tokens': 12, 'completion_tokens': 3},
                           'choices': [{'finish_reason': 'stop',
                                        'message': {'content': 'SELECT 1'}}]}
            return io.BytesIO(json.dumps(payload).encode())

    monkeypatch.setenv('HTTP_PROXY', 'http://example.invalid')
    model = LocalModel(Ledger(), model_id='fixture')
    assert model.http.handlers and all(getattr(handler, 'proxies', {}) == {} for handler in model.http.handlers)
    model.http = HTTP()
    model.verify()
    assert len(model.generate('probe', 'synthetic sample', n=3)) == 3
    assert requests[0] == 'http://127.0.0.1:18082/v1/models'
    assert all(item.full_url == 'http://127.0.0.1:18082/v1/chat/completions' and
               json.loads(item.data)['messages'][0]['content'] == 'synthetic sample' for item in requests[1:])
    assert usage == [('probe', {'input_tokens': 12, 'output_tokens': 3})] * 3
    model.model_id = 'different'
    with pytest.raises(PermissionError, match='differs'):
        model.verify()


def test_local_grammar_keeps_grounding_and_review_interfaces():
    question = 'Compare "test event" for subject 71 across 2 visits.'
    prompt = [{'role': 'user', 'content': json.dumps({'original_question': question})}]
    assert '["71", "2", "\\"test event\\""]' in _structured_instruction('link', prompt)
    verify = _stage_schema('verify')['properties']
    assessments = _stage_schema('select')['properties']['assessments']['items']['properties']
    assert all(assessments[field] == schema for field, schema in verify.items())
    assert 'unknown' in verify['verdict']['enum']
    link = _stage_schema('link', {'catalog': [{'id': 'fixture-catalog:42'}]})['properties']
    assert link['requirements']['items']['properties']['span']['minLength'] == 1
    assert link['links']['items']['properties']['catalog_id']['enum'] == [None, 'fixture-catalog:42']
