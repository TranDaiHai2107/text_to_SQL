"""Local llama.cpp transport for the Task 8 comparison variants."""
import json
import re
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .openai_provider import ModelGenerationFailure


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _object(**fields):
    return {'type': 'object', 'properties': fields, 'required': list(fields),
            'additionalProperties': False}


def _array(items):
    return {'type': 'array', 'items': items}


def _stage_schema(stage, payload=None):
    string = {'type': 'string'}
    nonempty = {'type': 'string', 'minLength': 1}
    nullable_string = {'type': ['string', 'null']}
    if stage == 'link':
        from ehrqa.agentic.contracts import KINDS
        catalog_ids = [row['id'] for row in (payload or {}).get('catalog', ())]
        requirements = _array(_object(id=nonempty, kind={'enum': sorted(KINDS)},
                                      span=nonempty, description=nonempty))
        requirements['minItems'] = 1
        return _object(requirements=requirements,
                       links=_array(_object(requirement_id=string, span=nonempty, table=string,
                                            column=string, role=string,
                                            catalog_id={'enum': [None, *catalog_ids]})),
                       joins=_array(_object(left=string, right=string)), ambiguities=_array(string))
    if stage == 'decompose':
        operation = {'enum': ['filter', 'join', 'select_event', 'aggregate', 'rank', 'project']}
        return _object(steps=_array(_object(id=string, operation=operation, depends_on=_array(string),
                                            requirement_ids=_array(string), tables=_array(string),
                                            description=string)), output_step=string)
    if stage in {'generate', 'repair'}:
        return _object(sql=nullable_string, unresolved=_array(string))
    if stage in {'verify', 'select'}:
        check = _object(requirement_id=string, status={'enum': ['satisfied', 'contradicted', 'unknown']},
                        sql_evidence_ids=_array(string), schema_refs=_array(string),
                        missing_schema_refs=_array(string), evidence=string)
        check['required'].remove('missing_schema_refs')
        coverage = _object(status={'enum': ['complete', 'incomplete', 'unknown']},
                           uncovered_spans=_array(string),
                           extra_constraints=_array(_object(sql_evidence_ids=_array(string), evidence=string)))
        review = dict(checks=_array(check), verdict={'enum': ['supported', 'contradicted', 'unknown']},
                      question_coverage=coverage)
        if stage == 'select':
            return _object(selected_id=nullable_string, reason=string,
                           assessments=_array(_object(candidate_id=string, **review)))
        return _object(**review)


def _structured_instruction(stage, messages):
    instruction = (
        'Where an example field lists options separated by |, output exactly one '
        'permitted option. Copy spans character for character from original_question. '
        'Use bare table names in JSON links/plans and fully qualified names in SQL.'
    )
    if stage == 'link':
        from ehrqa.agentic.contracts import quoted_literals
        question = json.loads(messages[-1]['content'])['original_question']
        literals = re.findall(r'\b\d+(?:\.\d+)?\b', question) + quoted_literals(question)
        if literals:
            instruction += (' The requirement spans must collectively contain each of these literal substrings: '
                            + json.dumps(list(dict.fromkeys(literals)), ensure_ascii=False) + '.')
        instruction += (' Leave catalog_id null for general schema links. When citing a catalog ID, '
                        'use its exact source table and label or code column.')
    return instruction


class LocalModel:
    def __init__(self, ledger, *, model_id, port=18082, output_cap=4096):
        if not 1 <= port <= 65535 or not model_id or output_cap <= 0:
            raise ValueError('Invalid local provider configuration')
        self.ledger, self.model_id, self.output_cap = ledger, model_id, output_cap
        self.endpoint = f'http://127.0.0.1:{port}/v1'
        self.http = build_opener(ProxyHandler({}), NoRedirect())

    def verify(self):
        with self.http.open(self.endpoint + '/models', timeout=10) as stream:
            models = json.load(stream)['data']
        if [item['id'] for item in models] != [self.model_id]:
            raise PermissionError('Local server model differs from run configuration')

    def complete(self, stage, prompt, tokens=None):
        messages = [{'role': 'user', 'content': prompt}] if isinstance(prompt, str) else prompt
        cap = min(tokens or self.output_cap, self.output_cap)
        body = {'model': self.model_id, 'messages': messages, 'max_tokens': cap, 'temperature': 0.2}
        if not isinstance(prompt, str):
            body['response_format'] = {'type': 'json_object'}
            payload = json.loads(messages[-1]['content'])
            schema = _stage_schema(stage, payload)
            if schema is not None:
                body['response_format']['schema'] = schema
            # Small local models copy the pipe-delimited examples literally.
            # Clarify the output encoding while keeping the stage validators.
            instruction = _structured_instruction(stage, messages)
            if messages[0]['role'] == 'system':
                first = {**messages[0], 'content': messages[0]['content'] + '\n' + instruction}
                body['messages'] = [first, *messages[1:]]
            else:
                body['messages'] = [{'role': 'system', 'content': instruction}, *messages]
        request = Request(self.endpoint + '/chat/completions', json.dumps(body).encode(),
                          {'Content-Type': 'application/json'})
        reservation = self.ledger.reserve(stage=stage, prompt=json.dumps(body['messages']), output_cap=cap)
        with self.http.open(request, timeout=300) as stream:
            response = json.load(stream)
        usage = response['usage']
        self.ledger.reconcile(reservation, input_tokens=usage['prompt_tokens'],
                              output_tokens=usage['completion_tokens'])
        choice, = response['choices']
        content = choice['message']['content']
        if choice['finish_reason'] != 'stop' or not content or response['model'] != self.model_id:
            raise ModelGenerationFailure('Local model returned an incomplete or mismatched response', usage=usage)
        return {'content': content, 'model': self.model_id, 'model_snapshot': self.model_id,
                'response_id': response['id'], 'usage': usage, 'inference_backend': 'local'}

    def generate(self, stage, prompt, *, n=1):
        return [self.complete(stage, prompt) for _ in range(n)]
