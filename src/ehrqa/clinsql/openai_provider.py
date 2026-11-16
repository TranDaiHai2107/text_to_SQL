"""GPT-5-mini Responses transport matching the native CLINSQL user-message shape."""
from __future__ import annotations

import os
import hashlib
import json
import time

from .pilot_api_budget import PersistentAPIBudgetLedger
from .benchmark_model import BENCHMARK_LLM, ModelMismatch, require_benchmark_model

GPT5_MINI_MAX_OUTPUT = 128_000
OPENAI_API_BASE = 'https://api.openai.com/v1'


def request_receipt(path, payload, prompt_field):
    prompt = json.dumps(payload[prompt_field], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return {'endpoint': OPENAI_API_BASE + path,
            'parameters': {key: value for key, value in payload.items() if key != prompt_field},
            'wire_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest()}

class AmbiguousModelRequest(ConnectionError):
    """A request may have reached the API; never retry it automatically."""

    def __init__(self, message: str, *, cause_type: str | None = None,
                 http_status: int | None = None,
                 latency_seconds: float | None = None):
        super().__init__(message)
        self.cause_type = cause_type
        self.http_status = http_status
        self.latency_seconds = latency_seconds


class ModelGenerationFailure(RuntimeError):
    """The API returned a response without a completed text generation."""

    def __init__(self, message: str, *, usage: dict | None = None,
                 response_id: str | None = None, model: str | None = None,
                 latency_seconds: float | None = None,
                 incomplete_reason: str | None = None):
        super().__init__(message)
        self.usage = usage or {}
        self.response_id = response_id
        self.model = model
        self.latency_seconds = latency_seconds
        self.incomplete_reason = incomplete_reason


class ModelUsageUnknown(RuntimeError):
    """The API response cannot be reconciled to the approved token budget."""


class OpenAIModelProvider:
    def __init__(self, ledger: PersistentAPIBudgetLedger, *, model_id: str = BENCHMARK_LLM,
                 max_output_tokens: int | None = 2048, timeout_seconds: float = 60,
                 reasoning_effort: str | None = None, client=None):
        require_benchmark_model(model_id)
        if (max_output_tokens is not None and max_output_tokens <= 0) or timeout_seconds <= 0:
            raise ValueError('Positive output and timeout caps required')
        if reasoning_effort not in (None, 'low', 'medium', 'high'):
            raise ValueError('Unsupported locked GPT-5-mini reasoning effort')
        self.ledger, self.model_id = ledger, model_id
        self.max_output_tokens, self.timeout_seconds = max_output_tokens, timeout_seconds
        self.reasoning_effort = reasoning_effort
        if client is None:
            if not os.environ.get('OPENAI_API_KEY'):
                raise RuntimeError('OPENAI_API_KEY is not available in this process')
            from openai import OpenAI
            client = OpenAI(base_url=OPENAI_API_BASE, max_retries=0, timeout=timeout_seconds)
        self.client = client

    @staticmethod
    def serialize_prompt(prompt: str) -> list[dict]:
        if not isinstance(prompt, str) or not prompt:
            raise ValueError('Nonempty CLINSQL prompt required')
        return [{'role': 'user', 'content': [{'type': 'input_text', 'text': prompt}]}]

    def complete(self, stage: str, prompt: str, *_args, text_format=None, **_kwargs) -> dict:
        require_benchmark_model(self.model_id)
        serialized = self.serialize_prompt(prompt)
        kwargs = {'model': self.model_id, 'input': serialized, 'store': False,
                  'timeout': self.timeout_seconds}
        if self.max_output_tokens is not None:
            kwargs['max_output_tokens'] = self.max_output_tokens
        if self.reasoning_effort is not None:
            kwargs['reasoning'] = {'effort': self.reasoning_effort}
        if text_format is not None:
            kwargs['text'] = {'format': text_format}
        reservation = self.ledger.reserve(stage=stage, prompt=prompt,
                                          output_cap=self.max_output_tokens or GPT5_MINI_MAX_OUTPUT,
                                          transport=('openai.responses', self.model_id),
                                          request_metadata=request_receipt('/responses', kwargs, 'input'))
        started = time.monotonic()
        try:
            response = self.client.responses.create(**kwargs)
        except Exception as exc:
            # The server may have completed this request. Keep its full budget reserved.
            raise AmbiguousModelRequest(
                'OpenAI request outcome unknown; inspect before resuming',
                cause_type=type(exc).__name__,
                http_status=getattr(exc, 'status_code', None),
                latency_seconds=time.monotonic() - started) from None
        usage = getattr(response, 'usage', None)
        if usage is None:
            raise ModelUsageUnknown('OpenAI response has no usage; full reservation remains charged')
        input_tokens = getattr(usage, 'input_tokens', None)
        output_tokens = getattr(usage, 'output_tokens', None)
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            raise ModelUsageUnknown('OpenAI response usage is incomplete; stop pilot')
        content = getattr(response, 'output_text', None)
        self.ledger.reconcile(reservation, input_tokens=input_tokens, output_tokens=output_tokens,
                              response_sha256=hashlib.sha256(content.encode()).hexdigest()
                              if isinstance(content, str) else None)
        details = getattr(usage, 'output_tokens_details', None)
        reasoning_tokens = getattr(details, 'reasoning_tokens', None)
        if reasoning_tokens is not None and (not isinstance(reasoning_tokens, int) or
                                             not 0 <= reasoning_tokens <= output_tokens):
            raise ModelUsageUnknown('Invalid reasoning-token accounting')
        usage_record = {'prompt_tokens': input_tokens,
                        'completion_tokens': output_tokens,
                        'reasoning_tokens': reasoning_tokens or 0}
        response_id = getattr(response, 'id', None)
        returned_model = getattr(response, 'model', None)
        if returned_model != BENCHMARK_LLM:
            raise ModelMismatch()
        if getattr(response, 'status', None) != 'completed':
            incomplete = getattr(response, 'incomplete_details', None)
            raise ModelGenerationFailure('OpenAI response was not completed; stop pilot',
                                         usage=usage_record, response_id=response_id,
                                         model=returned_model,
                                         latency_seconds=time.monotonic() - started,
                                         incomplete_reason=getattr(incomplete, 'reason', None))
        if not isinstance(content, str) or not content.strip():
            raise ModelGenerationFailure('OpenAI response contains no output text',
                                         usage=usage_record, response_id=response_id,
                                         model=returned_model,
                                         latency_seconds=time.monotonic() - started)
        return {'content': content, 'model': returned_model,
                'model_snapshot': returned_model,
                'response_id': response_id,
                'usage': usage_record,
                'latency_seconds': time.monotonic() - started}

    def generate(self, stage: str, prompt: str, *, n: int = 1) -> list[dict]:
        if n != 1:
            raise NotImplementedError('Multi-candidate API fidelity must be approved before MAC/SDE pilot')
        return [self.complete(stage, prompt)]
