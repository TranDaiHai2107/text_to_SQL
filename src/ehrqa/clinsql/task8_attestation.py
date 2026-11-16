"""Verify a Task 8 user attestation independently of delivery and billing gates."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re


PREFIX = 'task8-user-attestation:'
BASIS = 'USER_ATTESTATION'
STATUS = 'USER_CONFIRMED_NOT_INDEPENDENTLY_VERIFIED'


def verify_task8_attestation(approval, root: Path, pilot: dict) -> None:
    reference = approval.policy_reference
    if not reference.startswith(PREFIX):
        return
    expected = reference.removeprefix(PREFIX)
    if not re.fullmatch(r'[a-f0-9]{64}', expected):
        raise PermissionError('Invalid Task 8 attestation hash')
    directory = root / 'docs/attestations'
    path = (directory / f'{expected}.json').resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise PermissionError('Task 8 attestation record missing')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise PermissionError('Task 8 attestation hash mismatch')
    record = json.loads(raw)
    scope = record['methods'].get(approval.method, {})
    if (record.get('task') != 'TASK_8_VALIDATION_PILOT_5'
            or record.get('authorization_basis') != BASIS or record.get('authorization_status') != STATUS
            or record.get('confirmed_by') != approval.approver or record.get('principal') != approval.principal
            or record.get('project') != approval.project_id or record.get('model') != approval.model_id
            or record.get('location') != approval.location or record.get('retention_days') != approval.artifact_retention_days
            or record.get('iam_status') != approval.iam_status
            or record.get('pilot_sha256') != pilot['sha256'] or approval.pilot_manifest_sha256 != pilot['sha256']
            or record.get('case_ids') != [row['case_id'] for row in pilot['cases']]
            or (approval.method != 'catalog_export' and list(approval.case_ids) != record['case_ids'])
            or scope.get('variant') != approval.variant or scope.get('evidence') != approval.evidence
            or approval.valid_from_utc < datetime.fromisoformat(record['recorded_at_utc'])
            or approval.valid_until_utc > datetime.fromisoformat(record['valid_until'])):
        raise PermissionError('Method approval exceeds the recorded Task 8 attestation')
