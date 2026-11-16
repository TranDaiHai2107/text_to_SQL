from datetime import datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256
from types import SimpleNamespace

import pytest

from ehrqa.clinsql.execution_budget import (BudgetedDatabase, PersistentSQLBudgetLedger,
    ResearchCreditEnvelope, SQLBudgetLimits)
from ehrqa.clinsql.execution_errors import ResourceBudgetBlocked, classify_execution_failure
from ehrqa.clinsql.interfaces import DryRun, Execution


GIB = 1 << 30


def envelope(limit):
    return ResearchCreditEnvelope('account', 'project', Decimal('10'), Decimal('2'),
                                  Decimal('6.25'), datetime.now(timezone.utc) + timedelta(days=1),
                                  limit, 'synthetic statement')


class Database:
    def __init__(self, estimate, *, fail=False):
        self.estimate, self.fail, self.jobs = estimate, fail, []

    def dry_run(self, sql):
        return DryRun(self.estimate, True)

    def execute(self, sql, *, max_bytes_billed, job_id):
        self.jobs.append((max_bytes_billed, job_id))
        if self.fail:
            raise TimeoutError('unknown outcome')
        return Execution(('n',), ((1,),), True, bytes_billed=self.estimate, job_id=job_id)


def test_dynamic_cap_handles_query_above_old_cap_and_reconciles(tmp_path):
    credit = envelope(50 * GIB)
    ledger = PersistentSQLBudgetLedger(tmp_path / 'sql.sqlite',
                SQLBudgetLimits(3, 0, 50*GIB, 50*GIB), method='ours', credit=credit)
    db = Database(20 * GIB)
    runner = BudgetedDatabase(db, ledger, question_id='case', max_bytes_billed=25*GIB)
    assert runner.execute('SELECT 1').bytes_billed == 20 * GIB
    assert db.jobs[0][0] == 21 * GIB
    assert ledger.snapshot()['charged_bytes'] == 20 * GIB


def test_shared_envelope_survives_unknown_outcome_and_reconciles_by_job(tmp_path):
    credit = envelope(25 * GIB)
    limits = SQLBudgetLimits(3, 0, 40*GIB, 40*GIB)
    path = tmp_path / 'sql.sqlite'
    mac = PersistentSQLBudgetLedger(path, limits, method='mac_sql', credit=credit)
    db = Database(20 * GIB, fail=True)
    with pytest.raises(TimeoutError):
        BudgetedDatabase(db, mac, question_id='case', max_bytes_billed=24*GIB).execute('SELECT 1')
    ours = PersistentSQLBudgetLedger(path, limits, method='ours', credit=credit)
    next_db = Database(5 * GIB)
    with pytest.raises(ResourceBudgetBlocked) as exc:
        BudgetedDatabase(next_db, ours, question_id='case', max_bytes_billed=24*GIB).execute('SELECT 2')
    assert classify_execution_failure(exc.value, stage='execute') == 'RESOURCE_BUDGET_BLOCKED'
    assert not next_db.jobs and ours.snapshot()['pending'] == 1
    job = SimpleNamespace(state='DONE', total_bytes_billed=20*GIB)
    client = SimpleNamespace(get_job=lambda *args, **kwargs: job)
    assert mac.reconcile_job(db.jobs[0][1], client=client, project='project', location='US') == 'RECONCILED'
    BudgetedDatabase(next_db, ours, question_id='case', max_bytes_billed=24*GIB).execute('SELECT 2')
    assert next_db.jobs[0][0] == 5 * GIB
    assert mac.snapshot()['actual_billed_bytes'] == 25 * GIB


def test_method_limit_is_independent_of_case_and_experiment_limits(tmp_path):
    credit = envelope(100 * GIB)
    ledger = PersistentSQLBudgetLedger(tmp_path / 'sql.sqlite',
               SQLBudgetLimits(3, 0, 50*GIB, 24*GIB), method='sde', credit=credit)
    for case in ('a', 'b'):
        db = Database(12 * GIB)
        BudgetedDatabase(db, ledger, question_id=case, max_bytes_billed=20*GIB).execute('SELECT 1')
    with pytest.raises(ResourceBudgetBlocked):
        BudgetedDatabase(Database(GIB), ledger, question_id='c', max_bytes_billed=20*GIB).execute('SELECT 1')


def test_mac_recovery_only_lists_settled_probes_within_case_scope(tmp_path):
    path = tmp_path / 'sql.sqlite'
    limits = SQLBudgetLimits(10, 10, 40 * GIB, 40 * GIB)
    credit = envelope(25 * GIB)
    mac = PersistentSQLBudgetLedger(path, limits, method='mac_sql', credit=credit)
    ours = PersistentSQLBudgetLedger(path, limits, method='ours', credit=credit)

    def reserve(ledger, case, sql, *, probe=True, settle=True):
        job, cap = ledger.reserve(case, is_probe=probe, max_bytes_billed=GIB, minimum_bytes=1, sql=sql)
        if settle:
            ledger.reconcile(case, reserved_bytes=cap, actual_bytes_billed=0, reservation_id=job)
        return job

    match = reserve(mac, 'pinned', 'SELECT 1')
    reserve(mac, 'outside', 'SELECT 1')
    reserve(mac, 'pinned', 'SELECT 2', settle=False)
    reserve(mac, 'pinned', 'SELECT 3', probe=False)
    reserve(ours, 'pinned', 'SELECT 4')

    assert mac.settled_mac_probes(('pinned',)) == {sha256(b'SELECT 1').hexdigest(): ('pinned', match)}
    assert mac.remaining_probe_slots('pinned') == 7
    assert mac.remaining_probe_slots('outside') == 9

    from ehrqa.clinsql.execution_budget import DATABASE_PREPROCESSING_BUDGET as spare
    remaining = mac.remaining_research_bytes(spare)
    assert mac.remaining_probe_slots(spare) == 10
    new = reserve(mac, spare, 'SELECT 5')
    assert mac.remaining_probe_slots(spare) == 9
    assert mac.remaining_probe_slots('pinned') == 7
    assert mac.remaining_research_bytes(spare) == remaining
    assert mac.settled_mac_probes(('pinned',))[sha256(b'SELECT 5').hexdigest()] == (spare, new)
    with pytest.raises(PermissionError, match='by job ID'):
        reserve(mac, spare, 'SELECT 5')
    with pytest.raises(PermissionError, match='only MAC samples'):
        reserve(mac, spare, 'SELECT 6', probe=False)
    with pytest.raises(PermissionError):
        ours.settled_mac_probes(('pinned',))


def test_vnd_credit_reserve_and_same_currency_price():
    args = ('account', 'project', Decimal('7736289.17'), Decimal('500000'),
            Decimal('125000'), datetime.now(timezone.utc) + timedelta(days=1),
            9 << 40, 'synthetic VND pricing')
    price = dict(price_reference='synthetic Google SKU',
                 price_valid_until=datetime.now(timezone.utc) + timedelta(hours=1))
    assert ResearchCreditEnvelope(*args, currency='VND', reserve=Decimal('1000000'), **price).ceiling == 4 << 40
    with pytest.raises(ValueError):
        ResearchCreditEnvelope(*args, currency='VND')
    with pytest.raises(ValueError):
        ResearchCreditEnvelope(*args, currency='VND', reserve=Decimal('7300000'), **price)


@pytest.mark.parametrize('expired_field', ['expires_at', 'price_valid_until'])
def test_vnd_envelope_blocks_expired_evidence(expired_field):
    from dataclasses import replace

    credit = replace(envelope(10 * GIB), currency='VND', reserve=Decimal('1'),
                     price_reference='synthetic SKU',
                     price_valid_until=datetime.now(timezone.utc) + timedelta(days=1))
    expired = replace(credit, **{expired_field: datetime.now(timezone.utc) - timedelta(seconds=1)})
    with pytest.raises(ResourceBudgetBlocked, match='expired'):
        _ = expired.ceiling
