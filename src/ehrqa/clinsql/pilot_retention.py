"""Manual expiry enforcement for restricted Phase C.1 result artifacts."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .result_artifacts import verify_windows_private_acl


def inspect_or_delete_expired(run_root: Path, restricted_root: Path, *,
                              delete_expired: bool = False,
                              now: datetime | None = None,
                              verify_acl=verify_windows_private_acl) -> list[dict]:
    run_root, restricted_root = Path(run_root), Path(restricted_root)
    if not verify_acl(restricted_root):
        raise PermissionError('Restricted root ACL must pass before retention action')
    now = now or datetime.now(timezone.utc)
    output = []
    for log_path in sorted(run_root.glob('*.json')):
        saved = json.loads(log_path.read_text(encoding='utf-8'))
        for event in (e for e in saved.get('events', []) if e.get('stage') == 'result_artifact'):
            artifact_id = event['artifact_id']
            if not artifact_id.replace('_', '').replace('-', '').isalnum():
                raise ValueError('Unsafe artifact ID in run log')
            expiry = datetime.fromisoformat(event['artifact_expires_at_utc'])
            if expiry.tzinfo is None:
                raise ValueError('Artifact expiry must be timezone aware')
            artifact = restricted_root / f'{artifact_id}.json'
            tombstone = restricted_root / f'{artifact_id}.retention.json'
            if tombstone.exists():
                status = 'ALREADY_DELETED'
            elif not artifact.exists():
                raise FileNotFoundError('Restricted artifact missing without retention tombstone')
            elif now < expiry:
                status = 'NOT_DUE'
            elif not delete_expired:
                status = 'DUE_MANUAL_DELETION'
            else:
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != event['sha256']:
                    raise ValueError('Artifact hash mismatch; cannot delete')
                artifact.unlink()
                tombstone.write_text(json.dumps({
                    'artifact_id': artifact_id, 'sha256': event['sha256'],
                    'deleted_at_utc': now.isoformat(),
                    'source_log': log_path.name}, indent=2) + '\n', encoding='utf-8')
                status = 'DELETED'
            output.append({'artifact_id': artifact_id, 'status': status,
                           'expires_at_utc': expiry.isoformat()})
    return output
