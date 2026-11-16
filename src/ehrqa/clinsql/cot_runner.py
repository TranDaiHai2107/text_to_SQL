"""CLINSQL CoT and at most two execution-error refinements.

Model and database are injected. This module does not open API or BigQuery connections.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time

from .cot import generation_prompt, refinement_prompt, extract_sql
from .execution_errors import IncompleteResultError, SecurityRejected


@dataclass(frozen=True)
class Attempt:
    stage: str
    sql: str | None
    usage: dict
    latency_seconds: float
    redacted_error: str | None = None


@dataclass(frozen=True)
class Prediction:
    query_id: str
    sql: str | None
    status: str
    attempts: tuple[Attempt, ...]
    execution_attempts: int


class ClinSQLCoT:
    def __init__(self, model, database, schema_text: str, *, max_refinements: int = 2,
                 refine_guard_rejections: bool = True):
        if max_refinements != 2:
            raise ValueError('CLINSQL CoT reproduction requires two refinement opportunities')
        self.model = model
        self.db = database
        self.schema_text = schema_text
        self.refine_guard_rejections = refine_guard_rejections

    def run(self, query_id: str, question: str) -> Prediction:
        attempts = []
        prompt = generation_prompt(question, self.schema_text)
        execution_attempts = 0
        for index in range(3):
            stage = 'generate' if index == 0 else f'refine_{index}'
            started = time.monotonic()
            response = self.model.complete(stage, prompt)
            latency = time.monotonic() - started
            usage = response.get('usage', {})
            sql = extract_sql(response['content'])
            if not sql:
                attempts.append(Attempt(stage, None, usage, latency, 'Empty model SQL'))
                return Prediction(query_id, None, 'generation_failure', tuple(attempts), execution_attempts)
            try:
                self.db.dry_run(sql)
                execution_attempts += 1
                result = self.db.execute(sql)
                if result is not None and not result.complete:
                    raise IncompleteResultError('Incomplete BigQuery result; do not score as model failure')
                attempts.append(Attempt(stage, sql, usage, latency))
                return Prediction(query_id, sql, 'executed', tuple(attempts), execution_attempts)
            except (PermissionError, ConnectionError, TimeoutError) as exc:
                if isinstance(exc, SecurityRejected) and self.refine_guard_rejections:
                    error = ('Use one read-only SELECT with fully qualified tables '
                             'from the supplied schema only')
                    attempts.append(Attempt(stage, sql, usage, latency, error))
                    if index == 2:
                        return Prediction(query_id, sql, 'sql_error',
                                          tuple(attempts), execution_attempts)
                    prompt = refinement_prompt(question, self.schema_text, sql, error)
                    continue
                # Infrastructure and policy failures are not SQL failures.
                raise
            except ValueError as exc:
                # Never send arbitrary DB error text to the model.
                raw = str(exc)
                match = re.search(r'(?i)\b(unrecognized name|syntax error)\b', raw)
                error = match.group(1) if match else 'BigQuery SQL error; details withheld'
                attempts.append(Attempt(stage, sql, usage, latency, error))
                if index == 2:
                    return Prediction(query_id, sql, 'sql_error', tuple(attempts), execution_attempts)
                prompt = refinement_prompt(question, self.schema_text, sql, error)
        raise AssertionError('Unreachable')
