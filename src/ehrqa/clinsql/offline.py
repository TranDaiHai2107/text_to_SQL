"""Deterministic mock transports for cost-free workflow tests."""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
import json
from typing import ClassVar

from .interfaces import DryRun, Execution


@dataclass
class MockBigQuery:
    is_synthetic_mock: ClassVar[bool] = True
    records: list[dict]
    results: dict[str, Execution] = field(default_factory=dict)
    failures: dict[str, str] = field(default_factory=dict)
    estimated_bytes: int = 0
    calls: list[tuple[str, str]] = field(default_factory=list)

    def schema_metadata(self):
        return self.records

    def dry_run(self, sql, **_kwargs):
        self.calls.append(('dry_run', sql))
        if sql in self.failures:
            raise ValueError(self.failures[sql])
        return DryRun(self.estimated_bytes, True)

    def execute(self, sql, **_kwargs):
        self.calls.append(('execute', sql))
        if sql in self.failures:
            raise ValueError(self.failures[sql])
        return self.results.get(sql, Execution(('count',), ((1,),), True))

    def probe(self, sql, **_kwargs):
        self.calls.append(('probe', sql))
        return self.execute(sql)


class MockLLM:
    """Stage-keyed scripted responses; no SDK or network imports."""

    def __init__(self, responses: dict[str, list], *, model_id='gpt-5-mini'):
        self.responses = defaultdict(deque, {key: deque(value) for key, value in responses.items()})
        self.calls: list[dict] = []
        self.model_id = model_id
        self._request_counter = 0

    def complete(self, stage, prompt, *_args, **_kwargs):
        self.calls.append({'stage': stage, 'prompt': prompt})
        if not self.responses[stage]:
            raise AssertionError(f'No mock LLM response for {stage}')
        value = self.responses[stage].popleft()
        content = value if isinstance(value, str) else json.dumps(value)
        return {'content': content, 'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
                'model': self.model_id}

    def generate(self, stage, prompt, *, n=1):
        replies = [self.complete(stage, prompt) for _ in range(n)]
        if n > 1:
            # Mirror one Chat Completions request with n choices. Keep the
            # per-choice call trace for workflow assertions.
            self._request_counter += 1
            request_id = f'mock-multi-{self._request_counter}'
            for reply in replies:
                reply['response_id'] = request_id
                reply['usage'] = {}
            replies[0]['usage'] = {'prompt_tokens': 10,
                                   'completion_tokens': 5 * n}
        return replies
