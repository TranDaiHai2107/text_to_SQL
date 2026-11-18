"""Bounded GPT-5-mini Chat Completions transport for SDE n=9/n=3.

This transport is not called by the Phase C.1 runner. A future live SDE
runner must supply a method-scoped approval and a separate API ledger.
"""
from __future__ import annotations

import os
import hashlib
import json
import re
import time

from .openai_provider import (TRANSPORT_BACKOFF_SECONDS, _transient,
                              AmbiguousModelRequest, ModelGenerationFailure,
                              ModelUsageUnknown, GPT5_MINI_MAX_OUTPUT, OPENAI_API_BASE, request_receipt)
from .pilot_api_budget import PersistentAPIBudgetLedger
from .benchmark_model import BENCHMARK_LLM, ModelMismatch, require_benchmark_model
from .evidence_router import guard_mac_payload

MAC_MODEL_PARAMETER_ADAPTATION = 'MODEL_PARAMETER_COMPATIBILITY_ADAPTATION'


class OpenAIChatMultiProvider:
    def __init__(self, ledger: PersistentAPIBudgetLedger, *,
                 model_id: str = BENCHMARK_LLM,
                 max_completion_tokens: int | None = 4096,
                 timeout_seconds: float = 90,
                 reasoning_effort: str = 'medium', client=None, group_nine=False,
                 transport_retries: int = 0):
        require_benchmark_model(model_id)
        if not 0 <= transport_retries <= 3:
            raise ValueError('Transport retries must be between 0 and 3')
        self.transport_retries = transport_retries
        if (max_completion_tokens is not None and max_completion_tokens <= 0) or timeout_seconds <= 0:
            raise ValueError('Positive token and timeout caps required')
        if reasoning_effort not in {'low', 'medium', 'high'}:
            raise ValueError('Unsupported GPT-5-mini reasoning effort')
        self.ledger, self.model_id = ledger, model_id
        self.max_completion_tokens = max_completion_tokens
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort
        self.group_nine = group_nine
        if client is None:
            if not os.environ.get('OPENAI_API_KEY'):
                raise RuntimeError('OPENAI_API_KEY is not available in this process')
            from openai import OpenAI
            client = OpenAI(base_url=OPENAI_API_BASE, max_retries=0, timeout=timeout_seconds)
        self.client = client

    def generate(self, stage: str, prompt: str, *, n: int = 1) -> list[dict]:
        if n not in {1, 3, 9} or not isinstance(prompt, str) or not prompt:
            raise ValueError('Only nonempty SDE prompts with n=1,3,9 are supported')
        if n == 9 and self.group_nine:
            replies = []
            for _ in range(3):
                replies.extend(self._request(stage, prompt, 3))
            return replies
        return self._request(stage, prompt, n)

    def _payload(self, prompt, n):
        # Source connect_gpt uses one system and one user message. GPT-5-mini
        # rejects source temperature=0.3; omitting it is a documented adapter.
        messages = [{'role': 'system', 'content': 'You are a helpful SQL assistant.'},
                    {'role': 'user', 'content': prompt}]
        token_options = ({'max_completion_tokens': self.max_completion_tokens}
                         if self.max_completion_tokens is not None else {})
        return dict(model=self.model_id, messages=messages, **token_options,
                    reasoning_effort=self.reasoning_effort, n=n, store=False,
                    timeout=self.timeout_seconds)

    def _request(self, stage, prompt, n):
        require_benchmark_model(self.model_id)
        kwargs = self._payload(prompt, n)
        started = time.monotonic()
        retries = 0
        failure = None
        while True:
            # Same bounded transport retry as OpenAIModelProvider: a fresh
            # reservation per attempt; failed attempts stay charged at the cap.
            reservation = self.ledger.reserve(
                stage=stage, prompt=prompt,
                output_cap=n * (self.max_completion_tokens or GPT5_MINI_MAX_OUTPUT),
                transport=('openai.chat.completions', self.model_id),
                request_metadata=request_receipt('/chat/completions', kwargs, 'messages'))
            try:
                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as exc:
                if retries < self.transport_retries and _transient(exc):
                    time.sleep(TRANSPORT_BACKOFF_SECONDS[min(retries, len(TRANSPORT_BACKOFF_SECONDS) - 1)])
                    retries += 1
                    continue
                failure = exc
                break
        if failure is not None:
            exc = failure
            error = AmbiguousModelRequest(
                'Multi-choice request outcome unknown; inspect before resuming',
                cause_type=type(exc).__name__,
                http_status=getattr(exc, 'status_code', None),
                latency_seconds=time.monotonic() - started)
            body = getattr(exc, 'body', None)
            fields = body.get('error', body) if isinstance(body, dict) else {}
            if not isinstance(fields, dict):
                fields = {}
            error.provider_details = {
                key: value for key, value in {
                    'code': fields.get('code'), 'param': fields.get('param'),
                    'request_id': getattr(exc, 'request_id', None),
                }.items() if isinstance(value, str) and re.fullmatch(r'[\w.\[\]-]{1,100}', value)
            }
            if stage == 'sde.synthetic_transport' and prompt == 'Return exactly: SELECT 1':
                message = fields.get('message')
                if isinstance(message, str):
                    key = os.environ.get('OPENAI_API_KEY')
                    if key:
                        message = message.replace(key, '[redacted]')
                    error.provider_details['message'] = re.sub(r'sk-[\w-]+', '[redacted]', message)[:400]
            if (error.http_status == 400 and error.provider_details.get('code') == 'integer_above_max_value'
                and error.provider_details.get('param') == 'n' and error.provider_details.get('request_id')):
                self.ledger.reconcile(reservation, input_tokens=0, output_tokens=0)
                error.rejected_before_generation = True
            raise error from None
        usage = getattr(response, 'usage', None)
        input_tokens = getattr(usage, 'prompt_tokens', None)
        output_tokens = getattr(usage, 'completion_tokens', None)
        if not isinstance(input_tokens, int) or not isinstance(output_tokens, int):
            raise ModelUsageUnknown('Multi-choice response has no usable aggregate usage')
        choices = getattr(response, 'choices', None)
        response_hash = None
        if isinstance(choices, list):
            content = [getattr(getattr(choice, 'message', None), 'content', None) for choice in choices]
            if all(text is None or isinstance(text, str) for text in content):
                body = json.dumps(content, ensure_ascii=False).encode()
                response_hash = hashlib.sha256(body).hexdigest()
        self.ledger.reconcile(reservation, input_tokens=input_tokens,
                              output_tokens=output_tokens, response_sha256=response_hash)
        details = getattr(usage, 'completion_tokens_details', None)
        reasoning_tokens = getattr(details, 'reasoning_tokens', 0) or 0
        returned_model = getattr(response, 'model', None)
        response_id = getattr(response, 'id', None)
        if (not isinstance(response_id, str) or not response_id or
            not isinstance(reasoning_tokens, int) or
            not 0 <= reasoning_tokens <= output_tokens):
            raise ModelGenerationFailure('Multi-choice response metadata is incomplete',
                                         usage={'prompt_tokens': input_tokens,
                                                'completion_tokens': output_tokens},
                                         response_id=response_id, model=returned_model)
        if returned_model != self.model_id:
            raise ModelMismatch()
        if not isinstance(choices, list) or len(choices) != n:
            raise ModelGenerationFailure('Multi-choice response count differs from requested n',
                                         usage={'prompt_tokens': input_tokens,
                                                'completion_tokens': output_tokens},
                                         response_id=response_id, model=returned_model)
        sorted_choices = sorted(choices, key=lambda item: item.index)
        if [choice.index for choice in sorted_choices] != list(range(n)) or any(
            choice.finish_reason != 'stop' or
            not isinstance(choice.message.content, str) or
            not choice.message.content.strip() for choice in sorted_choices
        ):
            raise ModelGenerationFailure('Incomplete or empty multi-choice response',
                                         usage={'prompt_tokens': input_tokens,
                                                'completion_tokens': output_tokens},
                                         response_id=response_id, model=returned_model)
        aggregate = {'prompt_tokens': input_tokens,
                     'completion_tokens': output_tokens,
                     'reasoning_tokens': reasoning_tokens}
        return [{'content': choice.message.content,
                 'model': returned_model, 'model_snapshot': returned_model,
                 'response_id': response_id, 'choice_index': choice.index,
                 'usage': aggregate if choice.index == 0 else {},
                 'latency_seconds': time.monotonic() - started}
                for choice in sorted_choices]

    def complete(self, stage: str, prompt: str, *_args, **_kwargs) -> dict:
        return self.generate(stage, prompt, n=1)[0]


class MACSQLChatProvider(OpenAIChatMultiProvider):
    """The source's single user message with the pinned model's sampling defaults."""

    def __init__(self, ledger, *, model_id=BENCHMARK_LLM, timeout_seconds=180, client=None):
        super().__init__(ledger, model_id=model_id, timeout_seconds=timeout_seconds,
                         max_completion_tokens=None, client=client)

    def generate(self, stage, prompt, *, n=1):
        require_benchmark_model(self.model_id)
        if n != 1 or not isinstance(prompt, str) or not prompt:
            raise ValueError('MAC-SQL requires one user prompt and one reply')
        guard_mac_payload(stage, prompt)
        return self._request(stage, prompt, n)

    def _payload(self, prompt, n):
        return dict(model=self.model_id, messages=[{'role': 'user', 'content': prompt}],
                    n=n, store=False, timeout=self.timeout_seconds)
