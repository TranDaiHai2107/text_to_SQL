from datetime import datetime, timedelta
from types import SimpleNamespace
import hashlib
import json

import pytest

from ehrqa.cli.four_method_pilot import ROOT, _budgets, _credit, _sample_count, _scope
from ehrqa.clinsql.task8_attestation import PREFIX, verify_task8_attestation


def test_draft_limits_pass_runner_budget_preflight(tmp_path):
    draft = json.loads((ROOT / 'docs/TASK8_COMBINED_APPROVAL_DRAFT.json').read_bytes())
    credit_file = ROOT / 'docs/TASK7_RESEARCH_CREDIT_VND.json'
    credit = json.loads(credit_file.read_bytes())
    _, pilot, manifest, index = _scope()
    assert draft['status'] == 'DRAFT_NOT_AUTHORIZED'
    assert draft['credit_sha256'] == hashlib.sha256(credit_file.read_bytes()).hexdigest()
    assert draft['schema_sha256'] == manifest['sha256']
    assert draft['index_sha256'] == index.index['sha256'] and draft['pilot_sha256'] == pilot['sha256']
    assert datetime.fromisoformat(draft['valid_until_utc']) <= datetime.fromisoformat(credit['credit_valid_until'])
    for name, scope in draft['scopes'].items():
        method = 'mac_sql' if name.startswith('mac_') else name
        sql_path = tmp_path / 'sql.json'
        api_path = tmp_path / 'api.json'
        sql = json.dumps(scope['sql_budget']).encode()
        api = json.dumps(scope.get('api_budget', {})).encode()
        sql_path.write_bytes(sql)
        api_path.write_bytes(api)
        approval = SimpleNamespace(method=method, variant='grouped_3x3' if method == 'sde_sql' else '',
                                   sql_budget_sha256=hashlib.sha256(sql).hexdigest(),
                                   api_budget_sha256=hashlib.sha256(api).hexdigest())
        _budgets(approval, api_path, sql_path,
                 sample_count=_sample_count(index) if name == 'mac_samples' else 0)


def test_runner_loads_pinned_task8_vnd_credit_envelope():
    draft = json.loads((ROOT / 'docs/TASK8_COMBINED_APPROVAL_DRAFT.json').read_bytes())
    args = SimpleNamespace(credit=ROOT / 'docs/TASK7_RESEARCH_CREDIT_VND.json')
    approval = SimpleNamespace(credit_sha256=draft['credit_sha256'])
    config = SimpleNamespace(project_id='kltn-text-to-sql', billing_project='kltn-text-to-sql')
    credit = _credit(args, approval, config, check_expiry=False)
    assert credit.currency == 'VND'
    assert credit.credit_valid_until == datetime.fromisoformat(draft['valid_until_utc'])


def test_task8_attestation_binds_method_evidence_window_and_bytes(tmp_path):
    _, pilot, _, _ = _scope()
    start = datetime.fromisoformat('2026-11-15T00:10:00+07:00')
    until = start + timedelta(days=7)
    case_ids = [row['case_id'] for row in pilot['cases']]
    evidence = {'A': 'question_and_schema', 'C': 'sql_and_sanitized_errors',
                'D': 'approved_column_samples', 'E': 'row_presence_and_null'}
    record = {'task': 'TASK_8_VALIDATION_PILOT_5', 'authorization_basis': 'USER_ATTESTATION',
              'authorization_status': 'USER_CONFIRMED_NOT_INDEPENDENTLY_VERIFIED',
              'confirmed_by': 'test lead', 'principal': 'reader', 'project': 'project', 'model': 'model',
              'location': 'US', 'retention_days': 7, 'iam_status': 'reader-risk', 'pilot_sha256': pilot['sha256'],
              'case_ids': case_ids, 'recorded_at_utc': start.isoformat(), 'valid_until': until.isoformat(),
              'methods': {'mac_sql': {'variant': 'column_samples', 'evidence': evidence}}}
    raw = json.dumps(record).encode()
    sha = hashlib.sha256(raw).hexdigest()
    directory = tmp_path / 'docs/attestations'
    directory.mkdir(parents=True)
    path = directory / f'{sha}.json'
    path.write_bytes(raw)
    approval = dict(policy_reference=PREFIX + sha, approver='test lead', principal='reader',
                    project_id='project', model_id='model', location='US', artifact_retention_days=7,
                    iam_status='reader-risk', pilot_manifest_sha256=pilot['sha256'], case_ids=case_ids,
                    method='mac_sql', variant='column_samples', evidence=evidence,
                    valid_from_utc=start, valid_until_utc=until)
    verify_task8_attestation(SimpleNamespace(**approval), tmp_path, pilot)
    for override in ({'method': 'ours'}, {'case_ids': case_ids[:-1]}, {'evidence': {}},
                     {'valid_until_utc': until + timedelta(seconds=1)}):
        with pytest.raises(PermissionError, match='exceeds'):
            verify_task8_attestation(SimpleNamespace(**(approval | override)), tmp_path, pilot)
    path.write_bytes(raw + b' ')
    with pytest.raises(PermissionError, match='hash mismatch'):
        verify_task8_attestation(SimpleNamespace(**approval), tmp_path, pilot)
