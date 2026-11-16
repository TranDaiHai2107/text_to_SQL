"""Explicit CLINSQL Chat Completions backends. Construction is offline."""
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import json
import os
import re
import time


NATIVE = 'CLINSQL_NATIVE_AZURE_JUDGE'
ADAPTED = 'CLINSQL_ADAPTED_JUDGE'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class JudgeIncomplete(RuntimeError):
    """Sanitized operational failure. No rubric grade is available."""


def parse_grade(text):
    match = re.fullmatch(r'Score:[ \t]*([01])[ \t]*\r?\nExplanation:[ \t]*(\S[^\r\n]*)',
                         text.strip() if isinstance(text, str) else '')
    if not match:
        raise JudgeIncomplete('INVALID_JUDGE_RESPONSE')
    return int(match[1]), match[2].strip()


def parse_adapted_grade(text):
    """Recover unambiguous grades when the model formats the native instructions."""
    if not isinstance(text, str):
        raise JudgeIncomplete('INVALID_JUDGE_RESPONSE')
    body = text.strip()
    fenced = re.fullmatch(r'```(?:json|text)?\s*\n(.*?)\n```', body, re.S | re.I)
    if fenced:
        body = fenced[1].strip()
    if body.startswith('{'):
        try:
            try:
                value = json.loads(body, object_pairs_hook=list)
            except json.JSONDecodeError:
                # The source asks for JSON on two lines and names one field per line.
                lines = body.splitlines()
                if len(lines) != 2 or not all(line.lstrip().startswith('{') for line in lines):
                    raise
                one, two = (json.loads(line, object_pairs_hook=list) for line in lines)
                if len(one) != 1 or len(two) != 1:
                    raise
                value = one + two
            fields = {key.lower(): item for key, item in value}
            score, explanation = fields['score'], fields['explanation']
            if isinstance(score, str) and re.fullmatch(r'[01](?:\.0+)?', score.strip()):
                score = float(score)
            if (len(value) == len(fields) == 2 and type(score) in (int, float)
                    and score in (0, 1) and isinstance(explanation, str) and explanation.strip()):
                return int(score), explanation.strip()
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
    normalized = re.sub(r'(?im)^\s*[-*]\s+(?=(?:\*\*)?(?:score|explanation)\b)', '', body)
    normalized = re.sub(r'(?im)^\*\*(score|explanation)\*\*:', r'\1:', normalized)
    normalized = re.sub(r'(?im)^\*\*(score|explanation):\*\*', r'\1:', normalized)
    normalized = re.sub(r'(?im)^\*\*((?:score|explanation):[^\n]*)\*\*$', r'\1', normalized)
    match = re.fullmatch(r'Score:[ \t]*([01](?:\.0+)?)[ \t]*\r?\n\s*Explanation:[ \t]*(\S.*)',
                         normalized, re.S | re.I)
    if not match or re.search(r'(?im)^\s*(?:\*\*)?score\s*:', match[2]):
        raise JudgeIncomplete('INVALID_JUDGE_RESPONSE')
    return int(float(match[1])), match[2].strip()


@dataclass(frozen=True)
class JudgeConfig:
    mode: str
    model: str
    endpoint: str
    response_model: str
    input_usd_per_million: str
    output_usd_per_million: str
    pricing_reference: str
    azure_token_parameter: str = 'max_completion_tokens'
    temperature: float | None = None
    cached_input_usd_per_million: str | None = None
    adapted_max_completion_tokens: int | None = 1024

    def parameters(self):
        params = {self.azure_token_parameter: 1024}
        if self.mode == NATIVE:
            params['temperature'] = 0.2
        else:
            if self.adapted_max_completion_tokens is None:
                params.pop(self.azure_token_parameter)
            else:
                params[self.azure_token_parameter] = self.adapted_max_completion_tokens
            params['store'] = False
            if self.temperature is not None:
                params['temperature'] = self.temperature
        return params

    def validate(self):
        if self.mode == NATIVE:
            if (self.model != 'gpt-5-chat' or not self.response_model.startswith('gpt-5-chat')
                    or not re.fullmatch(r'https://[a-z0-9-]+\.openai\.azure\.com/?', self.endpoint)
                    or self.azure_token_parameter not in {'max_completion_tokens', 'max_tokens'}
                    or self.temperature is not None):
                raise ValueError('Native Azure deployment/configuration differs from source')
        elif self.mode == ADAPTED:
            if (not re.fullmatch(r'.+-\d{4}-\d{2}-\d{2}', self.model)
                    or self.model != self.response_model or self.endpoint != 'https://api.openai.com/v1'
                    or self.azure_token_parameter != 'max_completion_tokens'
                    or (self.adapted_max_completion_tokens is not None and
                        self.adapted_max_completion_tokens <= 0)
                    or (self.temperature is not None and not 0 <= self.temperature <= 2)):
                raise ValueError('Adapted judge requires a pinned OpenAI snapshot and supported parameters')
        else:
            raise ValueError('Unknown judge mode')
        prices = [self.input_usd_per_million, self.output_usd_per_million]
        if self.cached_input_usd_per_million is not None:
            prices.append(self.cached_input_usd_per_million)
        if not self.pricing_reference or any(not Decimal(p).is_finite() or Decimal(p) < 0 for p in prices):
            raise ValueError('Judge requires explicit, sourced prices')

    @property
    def sha256(self):
        config = asdict(self)
        if self.adapted_max_completion_tokens == 1024:
            config.pop('adapted_max_completion_tokens')
        return digest({'config': config, 'parameters': self.parameters(),
                       'api_version': '2024-12-01-preview' if self.mode == NATIVE else 'v1'})


class ChatJudge:
    def __init__(self, config, client=None):
        config.validate()
        self.config = config
        self.client = client
        self.verified = False
        self.next_call = 0.0

    def _client(self):
        if self.client is None:
            from openai import AzureOpenAI, OpenAI
            if self.config.mode == NATIVE:
                self.client = AzureOpenAI(api_version='2024-12-01-preview',
                                          azure_endpoint=self.config.endpoint,
                                          api_key=os.environ['AZURE_OPENAI_API_KEY'],
                                          timeout=60.0, max_retries=0)
            else:
                self.client = OpenAI(base_url=self.config.endpoint, timeout=60.0, max_retries=0)
        return self.client

    def verify(self):
        """Explicit synthetic Chat Completions preflight. May incur judge charges."""
        self.verified = False
        if self.config.mode == ADAPTED and self._client().models.retrieve(self.config.model).id != self.config.model:
            raise JudgeIncomplete('MODEL_SNAPSHOT_UNVERIFIED')
        grade, usage = self._request('Return exactly these two lines:\nScore: 1\nExplanation: synthetic preflight')
        if parse_grade(grade)[0] != 1:
            raise JudgeIncomplete('JUDGE_PREFLIGHT_GRADE_MISMATCH')
        self.verified = True
        return usage

    def __call__(self, prompt):
        if not self.verified:
            raise JudgeIncomplete('JUDGE_PREFLIGHT_REQUIRED')
        return self._request(prompt)

    def _request(self, prompt):
        time.sleep(max(0, self.next_call - time.monotonic()))
        start = time.monotonic()
        try:
            response = self._client().chat.completions.create(
                model=self.config.model, messages=[{'role': 'user', 'content': prompt}],
                **self.config.parameters())
        finally:
            self.next_call = time.monotonic() + 0.8
        usage = response.usage
        details = getattr(usage, 'prompt_tokens_details', None)
        cached = getattr(details, 'cached_tokens', None) or 0
        input_tokens = getattr(usage, 'prompt_tokens', None)
        output_tokens = getattr(usage, 'completion_tokens', None)
        amount = None
        if input_tokens is not None and output_tokens is not None:
            rate = self.config.cached_input_usd_per_million or self.config.input_usd_per_million
            amount = ((input_tokens - cached) * Decimal(self.config.input_usd_per_million)
                      + cached * Decimal(rate)
                      + output_tokens * Decimal(self.config.output_usd_per_million)) / 1_000_000
        metadata = {'returned_model': response.model, 'response_id': response.id,
                    'input_tokens': input_tokens, 'cached_tokens': cached, 'output_tokens': output_tokens,
                    'estimated_cost_usd': str(amount) if amount is not None else None,
                    'latency_seconds': time.monotonic() - start,
                    'finish_reason': response.choices[0].finish_reason if len(response.choices) == 1 else None}
        text = None
        if (response.model == self.config.response_model and len(response.choices) == 1
                and response.choices[0].finish_reason == 'stop'
                and not getattr(response.choices[0].message, 'refusal', None)
                and amount is not None):
            text = response.choices[0].message.content
        return text, metadata
