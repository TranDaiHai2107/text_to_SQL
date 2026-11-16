"""Manual, ACL-checked deletion of expired Phase A scalar artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from .execution_control import PHASE_A_MAX_BYTES
from .result_artifacts import verify_windows_private_acl


def _write_summary(path: Path, summary: dict) -> None:
    temporary = path.with_name(path.name + '.tmp')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump(summary, stream, indent=2)
    os.replace(temporary, path)


def expire_phase_a_artifacts(root: Path, *, now: datetime | None = None,
                             delete_expired: bool = False,
                             verify_acl=verify_windows_private_acl) -> list[dict]:
    root = Path(root)
    if not verify_acl(root):
        raise PermissionError('Verified restricted directory ACL required')
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('UTC-aware cleanup time required')
    outcomes = []
    for summary_path in sorted(root.glob('*.summary.json')):
        if summary_path.is_symlink() or summary_path.resolve().parent != root.resolve():
            raise PermissionError('Unsafe summary path')
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        if summary.get('phase') != 'phase_a_smoke' or summary.get('status') != 'COMPLETE':
            continue
        case_id = summary.get('case_id')
        artifact_id = summary.get('artifact_id', '')
        if (case_id not in PHASE_A_MAX_BYTES or not isinstance(artifact_id, str) or
                not artifact_id.replace('_', '').replace('-', '').isalnum() or
                not artifact_id.endswith('_' + case_id)):
            raise ValueError('Invalid Phase A retention summary')
        expires = datetime.fromisoformat(summary['artifact_expires_at_utc'])
        if expires.tzinfo is None:
            raise ValueError('Artifact expiry must be timezone-aware')
        artifact_path = root / f'{artifact_id}.json'
        if artifact_path.is_symlink() or artifact_path.resolve().parent != root.resolve():
            raise PermissionError('Unsafe artifact path')
        if summary.get('artifact_deleted_at_utc'):
            outcomes.append({'case_id': case_id, 'status': 'ALREADY_DELETED'})
            continue
        if not artifact_path.is_file() and summary.get('artifact_deletion_started_at_utc'):
            summary['artifact_deleted_at_utc'] = now.isoformat()
            if delete_expired:
                _write_summary(summary_path, summary)
            outcomes.append({'case_id': case_id,
                             'status': 'DELETION_AUDIT_PENDING' if not delete_expired else 'DELETED'})
            continue
        if not artifact_path.is_file():
            raise FileNotFoundError('Artifact missing without deletion audit')
        if hashlib.sha256(artifact_path.read_bytes()).hexdigest() != summary['artifact_sha256']:
            raise ValueError('Artifact hash mismatch; stop cleanup for audit')
        if now < expires:
            outcomes.append({'case_id': case_id, 'status': 'NOT_DUE',
                             'expires_at_utc': expires.isoformat()})
            continue
        if not delete_expired:
            outcomes.append({'case_id': case_id, 'status': 'DUE_MANUAL_DELETION',
                             'expires_at_utc': expires.isoformat()})
            continue
        summary['artifact_deletion_started_at_utc'] = now.isoformat()
        _write_summary(summary_path, summary)
        artifact_path.unlink()
        summary['artifact_deleted_at_utc'] = now.isoformat()
        _write_summary(summary_path, summary)
        outcomes.append({'case_id': case_id, 'status': 'DELETED',
                         'deleted_at_utc': now.isoformat()})
    return outcomes
