from datetime import datetime, timedelta
from types import SimpleNamespace
import hashlib
import json

import pytest

from ehrqa.cli.four_method_pilot import ROOT, _budgets, _credit, _scope
from ehrqa.clinsql.task8_attestation import PREFIX, verify_task8_attestation


def test_task8_attestation_binds_method_evidence_window_and_bytes(tmp_path):
    _, pilot, _, _ = _scope()
    start = datetime.fromisoformat('2026-11-15T00:10:00+07:00')
    until = start + timedelta(days=7)
    case_ids = [row['case_id'] for row in pilot['cases']]
    evidence = {'A': 'question_and_schema', 'C': 'sql_and_sanitized_errors',
                'E': 'probe_labels_and_column_names'}
    record = {'task': 'TASK_8_VALIDATION_PILOT_5', 'authorization_basis': 'USER_ATTESTATION',
              'authorization_status': 'USER_CONFIRMED_NOT_INDEPENDENTLY_VERIFIED',
              'confirmed_by': 'test lead', 'principal': 'reader', 'project': 'project', 'model': 'model',
              'location': 'US', 'retention_days': 7, 'iam_status': 'reader-risk', 'pilot_sha256': pilot['sha256'],
              'case_ids': case_ids, 'recorded_at_utc': start.isoformat(), 'valid_until': until.isoformat(),
              'methods': {'sde_sql': {'variant': 'probe_labels_only', 'evidence': evidence}}}
    raw = json.dumps(record).encode()
    sha = hashlib.sha256(raw).hexdigest()
    directory = tmp_path / 'docs/attestations'
    directory.mkdir(parents=True)
    path = directory / f'{sha}.json'
    path.write_bytes(raw)
    approval = dict(policy_reference=PREFIX + sha, approver='test lead', principal='reader',
                    project_id='project', model_id='model', location='US', artifact_retention_days=7,
                    iam_status='reader-risk', pilot_manifest_sha256=pilot['sha256'], case_ids=case_ids,
                    method='sde_sql', variant='probe_labels_only', evidence=evidence,
                    valid_from_utc=start, valid_until_utc=until)
    verify_task8_attestation(SimpleNamespace(**approval), tmp_path, pilot)
    for override in ({'method': 'ours'}, {'case_ids': case_ids[:-1]}, {'evidence': {}},
                     {'valid_until_utc': until + timedelta(seconds=1)}):
        with pytest.raises(PermissionError, match='exceeds'):
            verify_task8_attestation(SimpleNamespace(**(approval | override)), tmp_path, pilot)
    path.write_bytes(raw + b' ')
    with pytest.raises(PermissionError, match='hash mismatch'):
        verify_task8_attestation(SimpleNamespace(**approval), tmp_path, pilot)
