"""Separate restricted result artifacts; never place patient rows in run logs."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import date, datetime, time
from decimal import Decimal
import base64
import math

from ehrqa.text2sql.interfaces import Execution


def _encode(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return {'type': 'float', 'value': repr(value)} if not math.isfinite(value) else value
    if isinstance(value, Decimal):
        return {'type': 'decimal', 'value': str(value)}
    if isinstance(value, datetime):
        return {'type': 'datetime', 'value': value.isoformat()}
    if isinstance(value, date):
        return {'type': 'date', 'value': value.isoformat()}
    if isinstance(value, time):
        return {'type': 'time', 'value': value.isoformat()}
    if isinstance(value, bytes):
        return {'type': 'bytes', 'value': base64.b64encode(value).decode('ascii')}
    if isinstance(value, (list, tuple)):
        return {'type': 'array', 'value': [_encode(item) for item in value]}
    if isinstance(value, dict) or hasattr(value, 'items'):
        return {'type': 'struct', 'value': {str(k): _encode(v) for k, v in value.items()}}
    raise TypeError(f'Unsupported BigQuery result type: {type(value).__name__}')


def _decode(value):
    if not isinstance(value, dict):
        return value
    kind, item = value['type'], value['value']
    if kind == 'decimal':
        return Decimal(item)
    if kind == 'datetime':
        return datetime.fromisoformat(item)
    if kind == 'date':
        return date.fromisoformat(item)
    if kind == 'time':
        return time.fromisoformat(item)
    if kind == 'bytes':
        return base64.b64decode(item, validate=True)
    if kind == 'float':
        return float(item)
    if kind == 'array':
        return [_decode(v) for v in item]
    if kind == 'struct':
        return {k: _decode(v) for k, v in item.items()}
    raise ValueError('Unknown result artifact type')


def verify_windows_private_acl(path: Path, *, allow_safe_inherited=False) -> bool:
    """Require a protected Windows directory ACL limited to owner/SYSTEM/Admins."""
    path = Path(path)
    if os.name != 'nt' or not path.is_dir() or path.is_symlink():
        return False
    script = Path(__file__).resolve().parents[3] / 'scripts' / 'verify_result_acl.ps1'
    completed = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy',
         'Bypass', '-File', str(script), str(path)] + (['-AllowSafeInherited'] if allow_safe_inherited else []),
        capture_output=True, text=True, timeout=15, check=False)
    if completed.returncode != 0:
        return False
    try:
        return json.loads(completed.stdout)['safe'] is True
    except (ValueError, KeyError, TypeError):
        return False


class ResultArtifactStore:
    def __init__(self, root: Path, *, verify_private_acl=None):
        self.root = Path(root)
        self.verify_private_acl = verify_private_acl or verify_windows_private_acl

    def save(self, artifact_id: str, result: Execution) -> dict:
        if not artifact_id or not artifact_id.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Unsafe artifact ID')
        if not result.complete:
            raise ValueError('Truncated result cannot be stored for evaluation')
        if self.verify_private_acl is None or not self.verify_private_acl(self.root):
            raise PermissionError('Verified private ACL required before storing MIMIC results')
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f'{artifact_id}.json'
        payload = {'format_version': 2, 'columns': list(result.columns),
                   'column_types': list(result.column_types),
                   'rows': [[_encode(value) for value in row] for row in result.rows],
                   'job_id': result.job_id, 'complete': result.complete}
        data = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                          separators=(',', ':')).encode('utf-8')
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, 'O_BINARY', 0)
        descriptor = os.open(path, flags, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return {'artifact_id': artifact_id, 'sha256': hashlib.sha256(data).hexdigest(),
                'row_count': len(result.rows), 'job_id': result.job_id}

    def load(self, artifact_id: str, *, expected_sha256: str) -> Execution:
        if not artifact_id or not artifact_id.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Unsafe artifact ID')
        if self.verify_private_acl is None or not self.verify_private_acl(self.root):
            raise PermissionError('Verified private ACL required before reading MIMIC results')
        data = (self.root / f'{artifact_id}.json').read_bytes()
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise ValueError('Result artifact hash mismatch')
        payload = json.loads(data)
        if payload.get('format_version') not in {1, 2} or not payload.get('complete'):
            raise ValueError('Invalid result artifact')
        rows = payload['rows'] if payload['format_version'] == 1 else [
            [_decode(value) for value in row] for row in payload['rows']]
        return Execution(tuple(payload['columns']), tuple(tuple(r) for r in rows),
                         True, column_types=tuple(payload['column_types']),
                         job_id=payload.get('job_id'))
