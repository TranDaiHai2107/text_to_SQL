"""Chat Completions transport for Ours on BIRD: the same pinned snapshot as the baseline.

Temperature 0 (the baseline's greedy decoding), JSON-object responses (every Ours stage
returns JSON). A shared, thread-safe spend cap stops new requests once reached.
"""
from __future__ import annotations

import threading
import time

# USD per 1M tokens (OpenAI pricing for gpt-4o-mini-2024-07-18): input, cached input, output.
PRICES = {'gpt-4o-mini-2024-07-18': (0.15, 0.075, 0.60), 'gpt-4o-2024-11-20': (2.50, 1.25, 10.00)}


class BudgetExceeded(RuntimeError):
    pass


class SpendTracker:
    def __init__(self, cap_usd: float, spent_usd: float = 0.0):
        self.cap, self.spent = cap_usd, spent_usd
        self.lock = threading.Lock()

    def check(self) -> None:
        with self.lock:
            if self.spent >= self.cap:
                raise BudgetExceeded(f'Spend cap reached: ${self.spent:.4f} of ${self.cap:.2f}')

    def add(self, usd: float) -> None:
        with self.lock:
            self.spent += usd


class ChatModel:
    def __init__(self, model: str, tracker: SpendTracker, *, client=None, temperature: float = 0.0):
        if model not in PRICES:
            raise ValueError(f'Unpinned model {model}')
        self.model, self.tracker, self.temperature = model, tracker, temperature
        if client is None:
            from openai import OpenAI
            client = OpenAI(timeout=180, max_retries=4)
        self.client = client

    def cost(self, usage: dict) -> float:
        price_in, price_cached, price_out = PRICES[self.model]
        cached = usage.get('cached_tokens', 0)
        return ((usage['prompt_tokens'] - cached) * price_in + cached * price_cached
                + usage['completion_tokens'] * price_out) / 1e6

    def sample(self, stage: str, messages: list[dict], tokens: int, *, n: int, temperature: float) -> dict:
        """n completions from one request (prompt billed once), like the baseline's majority mode."""
        self.tracker.check()
        started = time.monotonic()
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, n=n,
            max_tokens=min(int(tokens), 16_384), response_format={'type': 'json_object'})
        if response.model != self.model:
            raise RuntimeError(f'Served model {response.model} differs from pinned {self.model}')
        details = getattr(response.usage, 'prompt_tokens_details', None)
        usage = {'prompt_tokens': response.usage.prompt_tokens,
                 'completion_tokens': response.usage.completion_tokens,
                 'cached_tokens': getattr(details, 'cached_tokens', 0) or 0}
        usd = self.cost(usage)
        self.tracker.add(usd)
        return {'contents': [c.message.content or '' for c in response.choices], 'model': response.model,
                'usage': usage, 'usd': usd, 'finish_reasons': [c.finish_reason for c in response.choices],
                'system_fingerprint': response.system_fingerprint,
                'latency_seconds': round(time.monotonic() - started, 3)}

    def complete(self, stage: str, messages: list[dict], tokens: int) -> dict:
        self.tracker.check()
        started = time.monotonic()
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=self.temperature,
            max_tokens=min(int(tokens), 16_384), response_format={'type': 'json_object'})
        if response.model != self.model:
            raise RuntimeError(f'Served model {response.model} differs from pinned {self.model}')
        choice = response.choices[0]
        details = getattr(response.usage, 'prompt_tokens_details', None)
        usage = {'prompt_tokens': response.usage.prompt_tokens,
                 'completion_tokens': response.usage.completion_tokens,
                 'cached_tokens': getattr(details, 'cached_tokens', 0) or 0}
        usd = self.cost(usage)
        self.tracker.add(usd)
        return {'content': choice.message.content or '', 'model': response.model, 'usage': usage,
                'usd': usd, 'finish_reason': choice.finish_reason,
                'system_fingerprint': response.system_fingerprint,
                'latency_seconds': round(time.monotonic() - started, 3)}

    def _text(self, messages: list[dict], tokens: int, n: int, temperature: float) -> dict:
        """Plain-text completions (no JSON mode), the baseline's request shape."""
        self.tracker.check()
        started = time.monotonic()
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, n=n, max_tokens=min(int(tokens), 16_384))
        if response.model != self.model:
            raise RuntimeError(f'Served model {response.model} differs from pinned {self.model}')
        details = getattr(response.usage, 'prompt_tokens_details', None)
        usage = {'prompt_tokens': response.usage.prompt_tokens,
                 'completion_tokens': response.usage.completion_tokens,
                 'cached_tokens': getattr(details, 'cached_tokens', 0) or 0}
        usd = self.cost(usage)
        self.tracker.add(usd)
        return {'contents': [c.message.content or '' for c in response.choices], 'model': response.model,
                'usage': usage, 'usd': usd, 'finish_reasons': [c.finish_reason for c in response.choices],
                'system_fingerprint': response.system_fingerprint,
                'latency_seconds': round(time.monotonic() - started, 3)}

    def complete_text(self, stage: str, messages: list[dict], tokens: int) -> dict:
        result = self._text(messages, tokens, 1, self.temperature)
        result['content'] = result.pop('contents')[0]
        return result

    def sample_text(self, stage: str, messages: list[dict], tokens: int, *, n: int, temperature: float) -> dict:
        return self._text(messages, tokens, n, temperature)
