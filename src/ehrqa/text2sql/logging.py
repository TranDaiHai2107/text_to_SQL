"""Model/SQL event accounting with caller-supplied prices; no provider access."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import time


@dataclass(frozen=True)
class Pricing:
    input_per_million_usd: float
    output_per_million_usd: float

    def estimate(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input_per_million_usd +
                output_tokens * self.output_per_million_usd) / 1_000_000


@dataclass
class RunLog:
    query_id: str
    method: str
    pricing: Pricing | None = None
    events: list[dict] = field(default_factory=list)
    started_monotonic: float = field(default_factory=time.monotonic)

    def add(self, stage: str, **values):
        self.events.append({'stage': stage, **values})

    def summary(self):
        llm = [e for e in self.events if e['stage'] in
               {'llm', 'llm_failure', 'llm_transport_error'}]
        inputs = sum(int(e.get('input_tokens', 0)) for e in llm)
        outputs = sum(int(e.get('output_tokens', 0)) for e in llm)
        return {'query_id': self.query_id, 'method': self.method,
                'api_calls': len(llm), 'input_tokens': inputs,
                'api_usage_unknown_calls': sum(
                    e['stage'] == 'llm_transport_error' for e in llm),
                'output_tokens': outputs,
                'reasoning_tokens': sum(int(e.get('reasoning_tokens', 0)) for e in llm),
                'latency_seconds': sum(float(e.get('latency_seconds', 0)) for e in llm),
                'total_latency_seconds': time.monotonic() - self.started_monotonic,
                'execution_attempts': sum(e['stage'] == 'execute' for e in self.events),
                'probe_attempts': sum(e['stage'] == 'probe' for e in self.events),
                'retry_calls': sum(any(word in str(e.get('operation', '')).lower()
                                       for word in ('repair', 'refine', 'refiner')) for e in llm),
                'estimated_inference_cost_usd': self.pricing.estimate(inputs, outputs)
                if self.pricing else None, 'evaluation_cost_usd': None}

    def save(self, path: Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError('Run record exists; resume without recalling the model')
        path.write_text(json.dumps({'summary': self.summary(), 'events': self.events},
                                   ensure_ascii=False, indent=2, default=str), encoding='utf-8')
        return path


class MeteredModel:
    def __init__(self, model, log: RunLog):
        self.model, self.log = model, log

    def generate(self, stage, prompt, *, n=1):
        started = time.monotonic()
        responses = self.model.generate(stage, prompt, n=n)
        elapsed = time.monotonic() - started
        if not responses:
            raise ValueError('Model returned no choices')
        groups = {}
        for index, response in enumerate(responses):
            groups.setdefault(response.get('response_id') or index, []).append(response)
        for group in groups.values():
            self._record(stage, group[0], elapsed / len(groups), prompt, choices=len(group))
        return responses

    def complete(self, stage, prompt, *args, **kwargs):
        started = time.monotonic()
        response = self.model.complete(stage, prompt, *args, **kwargs)
        self._record(stage, response, time.monotonic() - started, prompt)
        return response

    def _record(self, stage, response, elapsed, prompt, *, choices=1):
        usage = response.get('usage', {})
        self.log.add('llm', operation=stage, model=response.get('model'),
                     inference_backend=response.get('inference_backend', 'openai'),
                     model_snapshot=response.get('model_snapshot'),
                     response_id=response.get('response_id'),
                     prompt_sha256=hashlib.sha256((prompt if isinstance(prompt, str) else
                         json.dumps(prompt, sort_keys=True, ensure_ascii=False,
                                    default=str)).encode('utf-8')).hexdigest(),
                     input_tokens=usage.get('prompt_tokens', 0),
                     output_tokens=usage.get('completion_tokens', 0),
                     reasoning_tokens=usage.get('reasoning_tokens', 0),
                     latency_seconds=elapsed, choices=choices)


class MeteredDatabase:
    def __init__(self, database, log: RunLog, *, capture_rows=False):
        if capture_rows and not getattr(database, 'is_synthetic_mock', False):
            raise PermissionError('Raw result logging is allowed only for synthetic mock databases')
        self.database, self.log, self.capture_rows = database, log, capture_rows

    def schema_metadata(self):
        return self.database.schema_metadata()

    def dry_run(self, sql, **kwargs):
        try:
            result = self.database.dry_run(sql, **kwargs)
        except Exception as exc:
            self.log.add('dry_run', sql=sql, error_type=type(exc).__name__,
                         error='Database error; details withheld',
                         estimated_bytes=getattr(exc, 'estimated_bytes', None),
                         cap_bytes=getattr(exc, 'cap_bytes', None))
            raise
        self.log.add('dry_run', sql=sql, estimated_bytes=result.estimated_bytes)
        return result

    def _call(self, stage, sql, **kwargs):
        try:
            result = getattr(self.database, stage)(sql, **kwargs)
        except Exception as exc:
            self.log.add(stage, sql=sql, error_type=type(exc).__name__,
                         error='Database error; details withheld')
            raise
        self.log.add(stage, sql=sql, columns=list(result.columns), row_count=len(result.rows),
                     rows=result.rows if self.capture_rows else None,
                     column_types=list(result.column_types), complete=result.complete,
                     bytes_billed=result.bytes_billed, bytes_processed=result.bytes_processed,
                     job_id=result.job_id, latency_seconds=result.latency_seconds,
                     status='complete')
        return result

    def execute(self, sql, **kwargs):
        return self._call('execute', sql, **kwargs)

    def probe(self, sql, **kwargs):
        return self._call('probe', sql, **kwargs)

    def probe_presence(self, sql):
        from .interfaces import ProbePresence
        operation = getattr(self.database, 'probe_presence', None)
        if operation is None:
            result = self.probe(sql)
            if not result.complete:
                from ehrqa.clinsql.execution_errors import IncompleteResultError
                raise IncompleteResultError('No complete result available for probe presence')
            return ProbePresence(len(result.rows), result.job_id, result.bytes_billed)
        try:
            result = operation(sql)
        except Exception as exc:
            self.log.add('probe', sql=sql, summary_only=True, error_type=type(exc).__name__,
                         error='Database error; details withheld')
            raise
        self.log.add('probe', sql=sql, summary_only=True, total_rows=result.total_rows,
                     has_rows=result.has_rows, job_id=result.job_id, bytes_billed=result.bytes_billed,
                     bytes_processed=result.bytes_processed, latency_seconds=result.latency_seconds)
        return result
