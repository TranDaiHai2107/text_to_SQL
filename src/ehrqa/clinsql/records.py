"""Atomic, protocol-pinned prediction records; no model or database calls."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from .cot_runner import Prediction


class RunRecorder:
    def __init__(self, root: Path, protocol: dict):
        self.root = Path(root)
        self.protocol = protocol
        self.protocol_hash = hashlib.sha256(json.dumps(protocol, sort_keys=True).encode()).hexdigest()

    def _path(self, query_id: str) -> Path:
        if not query_id or any(part in {'.', '..', ''} for part in query_id.replace('\\', '/').split('/')):
            raise ValueError('Invalid query ID')
        if not all(c.isalnum() or c in '_-/' for c in query_id):
            raise ValueError('Unsafe query ID')
        return self.root / (query_id.replace('/', '__') + '.json')

    def save(self, prediction: Prediction):
        path = self._path(prediction.query_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {'protocol_hash': self.protocol_hash, 'prediction': asdict(prediction),
                   'inference_usage': {
                       'calls': len(prediction.attempts),
                       'input_tokens': sum(a.usage.get('prompt_tokens', 0) for a in prediction.attempts),
                       'output_tokens': sum(a.usage.get('completion_tokens', 0) for a in prediction.attempts),
                       'execution_attempts': prediction.execution_attempts,
                       'model_latency_seconds': sum(a.latency_seconds for a in prediction.attempts),
                   }, 'evaluation_cost': None}
        if path.exists():
            old = json.loads(path.read_text(encoding='utf-8'))
            if old['protocol_hash'] != self.protocol_hash:
                raise ValueError('Protocol changed; use a different run directory')
            if old != json.loads(json.dumps(payload)):
                raise ValueError('Prediction already recorded; do not overwrite or call the model again')
            return path
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temporary.replace(path)
        return path
