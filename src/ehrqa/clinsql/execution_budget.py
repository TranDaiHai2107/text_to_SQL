"""Conservative SQL budget reservation shared by all CLINSQL methods."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256

from .execution_errors import BudgetExceeded, ResourceBudgetBlocked

RESEARCH_CREDIT_AWARE = 'RESEARCH_CREDIT_AWARE'
DATABASE_PREPROCESSING_BUDGET = 'DATABASE_PREPROCESSING_BUDGET'


@dataclass(frozen=True)
class ResearchCreditEnvelope:
    billing_account: str
    project: str
    verified_credit: Decimal
    approved_spend: Decimal
    price_per_tib: Decimal
    expires_at: datetime
    experiment_byte_limit: int
    evidence_reference: str
    currency: str = 'USD'
    reserve: Decimal = Decimal('0')
    price_reference: str | None = None
    price_valid_until: datetime | None = None
    credit_observed_at: datetime | None = None
    credit_valid_until: datetime | None = None

    def __post_init__(self):
        values = (self.verified_credit, self.approved_spend, self.price_per_tib)
        if (any(not value.is_finite() or value <= 0 for value in values)
            or self.currency not in {'USD', 'VND'} or not self.reserve.is_finite() or self.reserve < 0
            or (self.currency == 'VND' and self.reserve <= 0)
            or self.approved_spend + self.reserve > self.verified_credit or self.experiment_byte_limit <= 0
            or self.expires_at.utcoffset() is None or not self.evidence_reference.strip()):
            raise ValueError('Verified credit and finite approved spend are required')
        if self.currency == 'VND' and (
            not self.price_reference or not self.price_reference.strip() or
            self.price_valid_until is None or self.price_valid_until.utcoffset() is None
        ):
            raise ValueError('VND pricing requires a source and timezone-aware validity deadline')
        if (self.credit_observed_at is None) != (self.credit_valid_until is None) or (
            self.credit_observed_at is not None and
            (self.credit_observed_at.utcoffset() is None or self.credit_valid_until.utcoffset() is None or
             self.credit_valid_until <= self.credit_observed_at)
        ):
            raise ValueError('Credit snapshot requires an ordered timezone-aware observation and deadline')

    @property
    def ceiling(self):
        now = datetime.now(timezone.utc)
        if now >= self.expires_at:
            raise ResourceBudgetBlocked('Approved billing credit evidence has expired')
        if self.credit_valid_until is not None and not self.credit_observed_at <= now < self.credit_valid_until:
            raise ResourceBudgetBlocked('Billing credit snapshot is outside its validity window')
        if self.price_valid_until is not None and now >= self.price_valid_until:
            raise ResourceBudgetBlocked('Approved BigQuery price evidence has expired')
        return min(self.experiment_byte_limit, int(self.approved_spend * (1 << 40) / self.price_per_tib))


def research_query_cap(estimate, ceiling, *, minimum_billed=10 * (1 << 20)):
    floor = max(estimate, minimum_billed)
    if estimate < 0 or floor > ceiling:
        raise ResourceBudgetBlocked('Dry run exceeds approved query ceiling', estimated_bytes=estimate, cap_bytes=ceiling)
    mib = 1 << 20
    margin = min(1 << 30, max(16 * mib, (estimate + 7) // 8))
    return min(ceiling, max(floor, ((estimate + margin + mib - 1) // mib) * mib))


@dataclass(frozen=True)
class SQLBudgetLimits:
    max_calls_per_question: int
    max_probes_per_question: int
    max_bytes_per_question: int
    max_bytes_per_experiment: int

    def __post_init__(self):
        if min(self.max_calls_per_question, self.max_bytes_per_question,
               self.max_bytes_per_experiment) <= 0 or self.max_probes_per_question < 0:
            raise ValueError('SQL budget limits must be positive; probes may be zero')


class SQLBudgetLedger:
    def __init__(self, limits: SQLBudgetLimits):
        self.limits = limits
        self.calls_by_question: dict[str, int] = {}
        self.probes_by_question: dict[str, int] = {}
        self.bytes_by_question: dict[str, int] = {}
        self.experiment_bytes = 0

    def reserve(self, question_id: str, *, is_probe: bool, max_bytes_billed: int) -> None:
        if not question_id or max_bytes_billed <= 0:
            raise ValueError('Question ID and per-SQL bytes cap required')
        calls = self.calls_by_question.get(question_id, 0)
        probes = self.probes_by_question.get(question_id, 0)
        used = self.bytes_by_question.get(question_id, 0)
        if (calls + 1 > self.limits.max_calls_per_question or
                probes + int(is_probe) > self.limits.max_probes_per_question or
                used + max_bytes_billed > self.limits.max_bytes_per_question or
                self.experiment_bytes + max_bytes_billed > self.limits.max_bytes_per_experiment):
            raise PermissionError('SQL execution budget exceeded; stop and request a new budget')
        self.calls_by_question[question_id] = calls + 1
        self.probes_by_question[question_id] = probes + int(is_probe)
        self.bytes_by_question[question_id] = used + max_bytes_billed
        self.experiment_bytes += max_bytes_billed

    def reconcile(self, question_id: str, *, reserved_bytes: int, actual_bytes_billed: int | None,
                  reservation_id: str | None = None) -> None:
        # Unknown billing is conservatively charged at the full reserved cap.
        if actual_bytes_billed is None:
            return
        if actual_bytes_billed < 0 or actual_bytes_billed > reserved_bytes:
            raise ValueError('Actual bytes billed are inconsistent with the job cap')
        refund = reserved_bytes - actual_bytes_billed
        self.bytes_by_question[question_id] -= refund
        self.experiment_bytes -= refund


class PersistentSQLBudgetLedger:
    """SQLite reservations survive crashes; unknown billing keeps the full cap charged.

    A reservation is committed before a query starts. A pending reservation is never
    automatically retried or refunded because a query job may already exist.
    """

    def __init__(self, path: Path, limits: SQLBudgetLimits, *, method=None, credit=None):
        self.path, self.limits = Path(path), limits
        self.method, self.credit = method, credit
        if (method is None) != (credit is None):
            raise ValueError('Research ledger requires method and verified credit')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reservations ('
                       'id TEXT PRIMARY KEY, question_id TEXT NOT NULL, '
                       'is_probe INTEGER NOT NULL, reserved_bytes INTEGER NOT NULL, '
                       'actual_bytes INTEGER, status TEXT NOT NULL)')
            if credit is not None:
                db.execute('CREATE TABLE IF NOT EXISTS research_jobs ('
                           'id TEXT PRIMARY KEY, method TEXT NOT NULL, sql_sha256 TEXT NOT NULL)')
                db.execute('CREATE TABLE IF NOT EXISTS credit_lock (id INTEGER PRIMARY KEY, pin TEXT NOT NULL)')
                pin = sha256(repr(credit).encode()).hexdigest()
                db.execute('INSERT OR IGNORE INTO credit_lock VALUES (1,?)', (pin,))
                if db.execute('SELECT pin FROM credit_lock WHERE id=1').fetchone()[0] != pin:
                    raise PermissionError('Shared research credit envelope differs from ledger')

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.execute('PRAGMA busy_timeout=30000')
        try:
            yield db
        finally:
            db.close()

    def reserve(self, question_id: str, *, is_probe: bool, max_bytes_billed: int,
                minimum_bytes=None, sql=None) -> str:
        if self.credit is not None:
            return self._reserve_research(question_id, is_probe, max_bytes_billed, minimum_bytes, sql)
        if not question_id or max_bytes_billed <= 0:
            raise ValueError('Question ID and per-SQL bytes cap required')
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                calls, probes, used = db.execute(
                    'SELECT count(*), coalesce(sum(is_probe),0), '
                    'coalesce(sum(coalesce(actual_bytes,reserved_bytes)),0) '
                    'FROM reservations WHERE question_id=?', (question_id,)).fetchone()
                experiment = db.execute(
                    'SELECT coalesce(sum(coalesce(actual_bytes,reserved_bytes)),0) '
                    'FROM reservations').fetchone()[0]
                if (calls + 1 > self.limits.max_calls_per_question or
                    probes + int(is_probe) > self.limits.max_probes_per_question or
                    used + max_bytes_billed > self.limits.max_bytes_per_question or
                    experiment + max_bytes_billed > self.limits.max_bytes_per_experiment):
                    raise PermissionError('SQL execution budget exceeded; stop and request a new budget')
                reservation_id = uuid.uuid4().hex
                db.execute('INSERT INTO reservations VALUES (?,?,?,?,?,?)',
                           (reservation_id, question_id, int(is_probe), max_bytes_billed,
                            None, 'pending'))
                db.execute('COMMIT')
                return reservation_id
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def _reserve_research(self, question_id, is_probe, desired, minimum, sql):
        if not question_id or not sql or minimum is None or not 0 < minimum <= desired:
            raise ValueError('Research reservation needs a bounded query estimate')
        case_key = f'{self.method}:{question_id}'
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if question_id == DATABASE_PREPROCESSING_BUDGET:
                if self.method != 'mac_sql' or not is_probe:
                    raise PermissionError('Database preprocessing budget permits only MAC samples')
                duplicate = db.execute(
                    'SELECT 1 FROM reservations JOIN research_jobs USING(id) '
                    'WHERE method=? AND is_probe=1 AND sql_sha256=?',
                    (self.method, sha256(sql.encode()).hexdigest())).fetchone()
                if duplicate:
                    raise PermissionError('Existing MAC sample reservation must be recovered by job ID')
            calls, probes, used = db.execute(
                'SELECT count(*), coalesce(sum(is_probe),0), '
                'coalesce(sum(coalesce(actual_bytes,reserved_bytes)),0) '
                'FROM reservations WHERE question_id=?', (case_key,)).fetchone()
            method_used = db.execute(
                'SELECT coalesce(sum(coalesce(actual_bytes,reserved_bytes)),0) FROM reservations '
                'JOIN research_jobs USING(id) WHERE method=?', (self.method,)).fetchone()[0]
            total = db.execute('SELECT coalesce(sum(coalesce(actual_bytes,reserved_bytes)),0) '
                               'FROM reservations').fetchone()[0]
            cap = min(desired, self.limits.max_bytes_per_question - used,
                      self.limits.max_bytes_per_experiment - method_used, self.credit.ceiling - total)
            if (cap < minimum or calls >= self.limits.max_calls_per_question
                or probes + int(is_probe) > self.limits.max_probes_per_question):
                raise ResourceBudgetBlocked('Approved case, method or experiment budget exhausted',
                                            estimated_bytes=minimum, cap_bytes=max(0, cap))
            identifier = 'clinsql_' + uuid.uuid4().hex
            db.execute('INSERT INTO reservations VALUES (?,?,?,?,?,?)',
                       (identifier, case_key, int(is_probe), cap, None, 'pending'))
            db.execute('INSERT INTO research_jobs VALUES (?,?,?)',
                       (identifier, self.method, sha256(sql.encode()).hexdigest()))
            db.execute('COMMIT')
            return identifier, cap

    def reconcile(self, question_id: str, *, reserved_bytes: int,
                  actual_bytes_billed: int | None, reservation_id: str | None = None) -> None:
        if reservation_id is None:
            raise ValueError('Persistent ledger requires a reservation ID')
        if actual_bytes_billed is not None and not 0 <= actual_bytes_billed <= reserved_bytes:
            raise ValueError('Actual bytes billed are inconsistent with the job cap')
        if self.method is not None:
            question_id = f'{self.method}:{question_id}'
        with self._connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                row = db.execute('SELECT question_id,reserved_bytes,status FROM reservations WHERE id=?',
                                 (reservation_id,)).fetchone()
                if row != (question_id, reserved_bytes, 'pending'):
                    raise ValueError('Unknown, mismatched or already reconciled reservation')
                db.execute('UPDATE reservations SET actual_bytes=?,status=? WHERE id=?',
                           (actual_bytes_billed, 'reconciled' if actual_bytes_billed is not None
                            else 'unknown_billing', reservation_id))
                db.execute('COMMIT')
            except BaseException:
                db.execute('ROLLBACK')
                raise

    def reconcile_job(self, job_id, *, client, project, location):
        """Read a known job without resubmitting. Unknown billing keeps its reservation."""
        if self.credit is None:
            raise ValueError('Job reconciliation is for the research ledger')
        with self._connect() as db:
            row = db.execute('SELECT question_id,reserved_bytes,status FROM reservations '
                             'JOIN research_jobs USING(id) WHERE id=? AND method=?',
                             (job_id, self.method)).fetchone()
        if row is None or row[2] not in {'pending', 'unknown_billing'}:
            raise ValueError('Unknown or settled research job')
        job = client.get_job(job_id, project=project, location=location)
        if job.state != 'DONE' or job.total_bytes_billed is None:
            return 'UNKNOWN_BILLING'
        actual = int(job.total_bytes_billed)
        if not 0 <= actual <= row[1]:
            raise ValueError('Reported bytes exceed the original reservation')
        with self._connect() as db:
            updated = db.execute("UPDATE reservations SET actual_bytes=?,status='reconciled' "
                                 "WHERE id=? AND status IN ('pending','unknown_billing')", (actual, job_id))
        return 'RECONCILED' if updated.rowcount else 'ALREADY_RECONCILED'

    def pending_jobs(self):
        with self._connect() as db:
            return [row[0] for row in db.execute(
                "SELECT id FROM reservations JOIN research_jobs USING(id) WHERE method=? "
                "AND status IN ('pending','unknown_billing') ORDER BY id", (self.method,))]

    def settled_mac_probes(self, case_ids):
        if self.method != 'mac_sql':
            raise PermissionError('Only MAC-SQL may recover column samples')
        allowed = {f'{self.method}:{case_id}': case_id for case_id in case_ids}
        allowed[f'{self.method}:{DATABASE_PREPROCESSING_BUDGET}'] = DATABASE_PREPROCESSING_BUDGET
        with self._connect() as db:
            rows = db.execute(
                "SELECT sql_sha256, question_id, id FROM reservations JOIN research_jobs USING(id) "
                "WHERE method=? AND is_probe=1 AND status='reconciled' ORDER BY reservations.rowid",
                (self.method,)).fetchall()
        return {sql_hash: (allowed[case], job) for sql_hash, case, job in rows if case in allowed}

    def remaining_probe_slots(self, question_id):
        case_key = f'{self.method}:{question_id}' if self.method else question_id
        with self._connect() as db:
            calls, probes = db.execute(
                'SELECT count(*),coalesce(sum(is_probe),0) FROM reservations WHERE question_id=?',
                (case_key,)).fetchone()
        return max(0, min(self.limits.max_calls_per_question - calls,
                          self.limits.max_probes_per_question - probes))

    def remaining_research_bytes(self, question_id):
        if self.credit is None:
            raise ValueError('Research credit is required')
        with self._connect() as db:
            used, method_used, total = db.execute(
                'SELECT coalesce(sum(CASE WHEN question_id=? THEN bytes ELSE 0 END),0), '
                'coalesce(sum(CASE WHEN method=? THEN bytes ELSE 0 END),0), coalesce(sum(bytes),0) '
                'FROM (SELECT question_id,method,coalesce(actual_bytes,reserved_bytes) AS bytes '
                'FROM reservations LEFT JOIN research_jobs USING(id))',
                (f'{self.method}:{question_id}', self.method)).fetchone()
        return max(0, min(self.limits.max_bytes_per_question - used,
                          self.limits.max_bytes_per_experiment - method_used,
                          self.credit.ceiling - total))

    def snapshot(self) -> dict:
        with self._connect() as db:
            rows = db.execute('SELECT question_id,is_probe,reserved_bytes,actual_bytes,status '
                              'FROM reservations').fetchall()
        report = {'calls': len(rows), 'probes': sum(r[1] for r in rows),
                'charged_bytes': sum(r[3] if r[3] is not None else r[2] for r in rows),
                'pending': sum(r[4] == 'pending' for r in rows)}
        if self.credit is not None:
            report['actual_billed_bytes'] = sum(r[3] or 0 for r in rows)
        return report


class BudgetedDatabase:
    def __init__(self, database, ledger: SQLBudgetLedger, *, question_id: str,
                 max_bytes_billed: int):
        if not question_id or max_bytes_billed <= 0:
            raise ValueError('Question ID and SQL cap required')
        self.database, self.ledger = database, ledger
        self.question_id, self.max_bytes_billed = question_id, max_bytes_billed

    def schema_metadata(self):
        return self.database.schema_metadata()

    def dry_run(self, sql, **kwargs):
        try:
            return self.database.dry_run(sql, **kwargs)
        except BudgetExceeded as exc:
            if getattr(self.ledger, 'credit', None) is not None:
                raise ResourceBudgetBlocked('Dry run exceeds approved query ceiling',
                                            estimated_bytes=exc.estimated_bytes, cap_bytes=exc.cap_bytes) from None
            raise

    def _run(self, operation: str, sql, **kwargs):
        # A dry run is required before accounting or creating a query job.
        dry_run = self.dry_run(sql)
        if getattr(self.ledger, 'credit', None) is not None:
            desired, minimum = self.research_quote(sql, dry_run)
            job_id, cap = self.ledger.reserve(self.question_id, is_probe=operation in {'probe', 'probe_presence'},
                                               max_bytes_billed=desired, minimum_bytes=minimum, sql=sql)
            try:
                result = getattr(self.database, operation)(sql, max_bytes_billed=cap, job_id=job_id, **kwargs)
            except BudgetExceeded:
                raise ResourceBudgetBlocked('BigQuery rejected the approved dynamic cap') from None
            self.ledger.reconcile(self.question_id, reserved_bytes=cap,
                                  actual_bytes_billed=result.bytes_billed, reservation_id=job_id)
            return result
        reservation_id = self.ledger.reserve(self.question_id, is_probe=operation == 'probe',
                                             max_bytes_billed=self.max_bytes_billed)
        result = getattr(self.database, operation)(sql, **kwargs)
        self.ledger.reconcile(self.question_id, reserved_bytes=self.max_bytes_billed,
                              actual_bytes_billed=result.bytes_billed, reservation_id=reservation_id)
        return result

    def research_quote(self, sql, dry_run):
        if not dry_run.valid:
            raise ValueError('BigQuery dry run did not validate SQL')
        from sqlglot import exp, parse_one
        refs = {table.sql() for table in parse_one(sql, read='bigquery').find_all(exp.Table)
                if table.catalog and table.db}
        mib = 1 << 20
        minimum_billed = max(1, len(refs)) * 10 * mib
        rounded = (dry_run.estimated_bytes + mib - 1) // mib * mib
        return (research_query_cap(rounded, self.max_bytes_billed, minimum_billed=minimum_billed),
                max(minimum_billed, rounded))

    def execute(self, sql, **kwargs):
        return self._run('execute', sql, **kwargs)

    def probe(self, sql, **kwargs):
        return self._run('probe', sql, **kwargs)

    def probe_presence(self, sql):
        if self.ledger.credit is None:
            raise PermissionError('SDE presence probes require the research SQL ledger')
        return self._run('probe_presence', sql)

    def recover_probe_presence(self, sql, job_id):
        if self.ledger.method != 'sde_sql':
            raise PermissionError('Only SDE may recover a presence probe')
        cap, billed = self._settled_probe(sql, job_id)
        value = self.database.saved_probe_presence(sql, job_id, max_bytes_billed=cap)
        if value.bytes_billed != billed:
            raise ValueError('Saved probe billed bytes differ from the SQL ledger')
        return value

    def recover_sample(self, sql, job_id, kind):
        if self.ledger.method != 'mac_sql':
            raise PermissionError('Only MAC-SQL may recover column samples')
        cap, billed = self._settled_probe(sql, job_id)
        return self.database.saved_sample(sql, job_id, cap=cap, billed=billed, kind=kind)

    def _settled_probe(self, sql, job_id):
        with self.ledger._connect() as db:
            row = db.execute('SELECT reserved_bytes,actual_bytes FROM reservations JOIN research_jobs USING(id) '
                             'WHERE id=? AND method=? AND question_id=? AND sql_sha256=? '
                             'AND is_probe=1 AND status=?',
                             (job_id, self.ledger.method, f'{self.ledger.method}:{self.question_id}',
                              sha256(sql.encode()).hexdigest(), 'reconciled')).fetchone()
        if row is None:
            raise PermissionError('No reconciled reservation for the saved probe')
        return row
