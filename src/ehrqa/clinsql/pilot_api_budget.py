"""Crash-safe, conservative GPT inference budget; no secrets or prompts stored."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
import hashlib
import json
import sqlite3
import uuid


@dataclass(frozen=True)
class PilotAPIBudget:
    max_calls: int
    max_input_tokens: int | None
    max_output_tokens: int | None
    max_cost_usd: Decimal | None
    input_per_million_usd: Decimal
    output_per_million_usd: Decimal
    policy: str = 'CAPPED'

    def __post_init__(self):
        caps = (self.max_input_tokens, self.max_output_tokens)
        if self.max_calls <= 0 or any(cap is not None and cap <= 0 for cap in caps):
            raise ValueError('Positive API calls and token budgets required')
        if min(self.input_per_million_usd, self.output_per_million_usd) <= 0:
            raise ValueError('Verified positive API prices required')
        if self.policy == 'CAPPED':
            if self.max_cost_usd is None or self.max_cost_usd <= 0 or None in caps:
                raise ValueError('CAPPED API policy requires a positive USD cap')
        elif self.policy == 'UNLIMITED_RESEARCH_NOV_2026':
            if self.max_cost_usd is not None:
                raise ValueError('November research policy must not set a USD hard cap')
        else:
            raise ValueError('Unknown API budget policy')

    def verify_active(self, now: datetime | None = None) -> None:
        if self.policy != 'UNLIMITED_RESEARCH_NOV_2026':
            return
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError('Timezone-aware timestamp required')
        local = now.astimezone(timezone(timedelta(hours=7)))
        if (local.year, local.month) != (2026, 11):
            raise PermissionError('Unlimited November 2026 API policy has expired')

    def cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        return (self.input_per_million_usd * input_tokens +
                self.output_per_million_usd * output_tokens) / Decimal(1_000_000)


class PersistentAPIBudgetLedger:
    def __init__(self, path: Path, budget: PilotAPIBudget):
        self.path, self.budget = Path(path), budget
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS api_calls ('
                       'id TEXT PRIMARY KEY, stage TEXT NOT NULL, input_reserved INTEGER NOT NULL, '
                       'output_reserved INTEGER NOT NULL, input_actual INTEGER, output_actual INTEGER, '
                       'status TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS budget_lock ('
                       'id INTEGER PRIMARY KEY CHECK(id=1), sha256 TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS request_transport ('
                       'id TEXT PRIMARY KEY, provider TEXT NOT NULL, model_id TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS request_receipt ('
                       'id TEXT PRIMARY KEY, metadata TEXT NOT NULL, response_sha256 TEXT)')
            payload = {name: str(getattr(budget, name))
                       for name in budget.__dataclass_fields__}
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            locked = db.execute('SELECT sha256 FROM budget_lock WHERE id=1').fetchone()
            if locked is None:
                if db.execute('SELECT 1 FROM api_calls LIMIT 1').fetchone():
                    raise PermissionError('Existing API calls lack a pinned budget lock')
                db.execute('INSERT INTO budget_lock VALUES (1, ?)', (digest,))
            elif locked[0] != digest:
                raise PermissionError('API budget differs from persistent ledger lock')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute('PRAGMA busy_timeout=30000')
        try:
            yield db
        finally:
            db.close()

    def reserve(self, *, stage: str, prompt: str, output_cap: int, transport=None,
                request_metadata=None) -> str:
        self.budget.verify_active()
        if not stage or not prompt or output_cap <= 0:
            raise ValueError('Stage, prompt and output cap required')
        # UTF-8 bytes bound text tokens conservatively; 128 covers one user-message envelope.
        input_upper = len(prompt.encode('utf-8')) + 128
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                rows = db.execute('SELECT input_reserved,output_reserved,input_actual,output_actual '
                                  'FROM api_calls').fetchall()
                used_input = sum(r[2] if r[2] is not None else r[0] for r in rows)
                used_output = sum(r[3] if r[3] is not None else r[1] for r in rows)
                if (len(rows) + 1 > self.budget.max_calls or
                    (self.budget.max_input_tokens is not None and
                     used_input + input_upper > self.budget.max_input_tokens) or
                    (self.budget.max_output_tokens is not None and
                     used_output + output_cap > self.budget.max_output_tokens) or
                    (self.budget.max_cost_usd is not None and
                     self.budget.cost(used_input + input_upper, used_output + output_cap) >
                     self.budget.max_cost_usd)):
                    raise PermissionError('API pilot budget exceeded before request submission')
                reservation_id = uuid.uuid4().hex
                db.execute('INSERT INTO api_calls VALUES (?,?,?,?,?,?,?)',
                           (reservation_id, stage, input_upper, output_cap, None, None, 'pending'))
                if transport is not None:
                    db.execute('INSERT INTO request_transport VALUES (?,?,?)', (reservation_id, *transport))
                if request_metadata is not None:
                    db.execute('INSERT INTO request_receipt VALUES (?,?,NULL)',
                               (reservation_id, json.dumps(request_metadata, sort_keys=True)))
                db.execute('COMMIT')
                return reservation_id
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def reconcile(self, reservation_id: str, *, input_tokens: int, output_tokens: int,
                  response_sha256=None) -> None:
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT input_reserved,output_reserved,status FROM api_calls WHERE id=?',
                                 (reservation_id,)).fetchone()
                if row is None or row[2] != 'pending':
                    raise ValueError('Unknown or already reconciled API reservation')
                if not 0 <= input_tokens <= row[0] or not 0 <= output_tokens <= row[1]:
                    raise ValueError('API usage exceeds reserved upper bound; stop pilot')
                db.execute('UPDATE api_calls SET input_actual=?,output_actual=?,status=? WHERE id=?',
                           (input_tokens, output_tokens, 'reconciled', reservation_id))
                if response_sha256 is not None:
                    db.execute('UPDATE request_receipt SET response_sha256=? WHERE id=?',
                               (response_sha256, reservation_id))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def snapshot(self) -> dict:
        with self._connect() as db:
            rows = db.execute('SELECT input_reserved,output_reserved,input_actual,output_actual,status '
                              'FROM api_calls').fetchall()
        input_tokens = sum(r[2] if r[2] is not None else r[0] for r in rows)
        output_tokens = sum(r[3] if r[3] is not None else r[1] for r in rows)
        return {'calls': len(rows), 'input_charged_tokens': input_tokens,
                'output_charged_tokens': output_tokens,
                'estimated_charged_usd': str(self.budget.cost(input_tokens, output_tokens)),
                'policy': self.budget.policy,
                'pending': sum(r[4] == 'pending' for r in rows)}
