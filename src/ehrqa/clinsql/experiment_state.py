"""Pre-freeze experiment scope and durable, fail-closed phase checkpoints."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3

from .dataset import load_official_questions, validation_partition
from .pilot_cases import SEED, verify_pilot_cases


PHASES = ('PILOT_5', 'FIDELITY_COMPLETION', 'DEVELOPMENT_152',
          'INTERNAL_CHECK_38', 'CONFIG_FREEZE', 'TEST_443',
          'OFFICIAL_EVALUATION', 'FINAL_REPORT')
METHODS = ('clinsql_cot', 'sde_sql', 'ours')
HISTORICAL_METHODS = ('clinsql_cot', 'mac_sql', 'sde_sql', 'ours')


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(raw).hexdigest()


def build_pre_freeze_manifest(benchmark_root: Path, pilot_path: Path, *,
                              schema_sha256: str, schema_index_sha256: str,
                              model_id: str) -> dict:
    """Read validation question text only; test IDs stay sealed until freeze."""
    if model_id != 'gpt-5-mini-2025-08-07':
        raise ValueError('Research model snapshot differs from locked configuration')
    questions, source_hash = load_official_questions(benchmark_root, split='validation')
    partition = validation_partition(questions, seed=SEED)
    pilot = verify_pilot_cases(pilot_path, benchmark_root)
    if (len(partition['development']), len(partition['internal_check'])) != (152, 38):
        raise ValueError('Validation split differs from approved 152/38 partition')
    if any(row['case_id'] not in partition['development'] for row in pilot['cases']):
        raise ValueError('Pilot contains a validation holdout case')
    if any(len(value) != 64 for value in (schema_sha256, schema_index_sha256)):
        raise ValueError('Pinned schema and index digests required')
    payload = {'version': 2, 'phase_order': list(PHASES),
               'methods': list(METHODS), 'model_id': model_id,
               'schema_sha256': schema_sha256,
               'schema_index_sha256': schema_index_sha256,
               'validation_question_tree_sha256': source_hash,
               'pilot_manifest_sha256': pilot['sha256'],
               'pilot_case_ids': [row['case_id'] for row in pilot['cases']],
               'development_case_ids': sorted(partition['development']),
               'internal_check_case_ids': sorted(partition['internal_check']),
               'test_expected_count': 443,
               'test_scope': 'LOCKED_UNTIL_CONFIG_FREEZE',
               'test_question_tree_sha256': None}
    return {**payload, 'sha256': _digest(payload)}


def verify_pre_freeze_manifest(manifest: dict) -> None:
    content = {key: value for key, value in manifest.items() if key != 'sha256'}
    methods = {1: HISTORICAL_METHODS, 2: METHODS}.get(manifest.get('version'), ())
    if (manifest.get('sha256') != _digest(content) or
        manifest.get('phase_order') != list(PHASES) or
        not methods or manifest.get('methods') != list(methods) or
        manifest.get('model_id') != 'gpt-5-mini-2025-08-07' or
        any(len(str(manifest.get(key, ''))) != 64 for key in
            ('schema_sha256', 'schema_index_sha256',
             'validation_question_tree_sha256', 'pilot_manifest_sha256')) or
        manifest.get('test_scope') != 'LOCKED_UNTIL_CONFIG_FREEZE' or
        manifest.get('test_question_tree_sha256') is not None or
        len(manifest.get('pilot_case_ids', [])) != 5 or
        len(manifest.get('development_case_ids', [])) != 152 or
        len(manifest.get('internal_check_case_ids', [])) != 38 or
        set(manifest['development_case_ids']) & set(manifest['internal_check_case_ids']) or
        not set(manifest['pilot_case_ids']).issubset(manifest['development_case_ids'])):
        raise ValueError('Invalid or modified pre-freeze experiment manifest')


@dataclass(frozen=True)
class CaseCheckpoint:
    phase: str
    method: str
    case_id: str
    status: str
    artifact_sha256: str | None


class ExperimentState:
    """Exactly-once claims; interrupted claims need manual reconciliation."""

    def __init__(self, path: Path, manifest: dict):
        verify_pre_freeze_manifest(manifest)
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE IF NOT EXISTS scope_lock ('
                       'id INTEGER PRIMARY KEY CHECK(id=1), sha256 TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS case_runs ('
                       'phase TEXT NOT NULL, method TEXT NOT NULL, case_id TEXT NOT NULL, '
                       'status TEXT NOT NULL, artifact_sha256 TEXT, '
                       'PRIMARY KEY (phase,method,case_id))')
            locked = db.execute('SELECT sha256 FROM scope_lock WHERE id=1').fetchone()
            if locked is None:
                db.execute('INSERT INTO scope_lock VALUES (1, ?)', (manifest['sha256'],))
            elif locked[0] != manifest['sha256']:
                raise PermissionError('Experiment state scope differs from pinned manifest')
        self.manifest = manifest

    def _allowed(self, phase: str, method: str, case_id: str) -> bool:
        if phase == 'PILOT_5':
            return method == 'clinsql_cot' and case_id in self.manifest['pilot_case_ids']
        if phase == 'FOUR_METHOD_PILOT_5':
            return method in METHODS and case_id in self.manifest['pilot_case_ids']
        if phase == 'DEVELOPMENT_152':
            return method in METHODS and case_id in self.manifest['development_case_ids']
        if phase == 'INTERNAL_CHECK_38':
            return method in METHODS and case_id in self.manifest['internal_check_case_ids']
        return False  # Test and later phases require a frozen manifest and separate gate.

    def claim(self, phase: str, method: str, case_id: str) -> None:
        if not self._allowed(phase, method, case_id):
            raise PermissionError('Case is outside the pre-freeze phase scope')
        with sqlite3.connect(self.path, timeout=30, isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                db.execute('INSERT INTO case_runs VALUES (?,?,?,?,?)',
                           (phase, method, case_id, 'STARTED', None))
                db.execute('COMMIT')
            except sqlite3.IntegrityError as exc:
                db.execute('ROLLBACK')
                raise FileExistsError('Case already claimed; inspect checkpoint before rerun') from exc

    def finish(self, phase: str, method: str, case_id: str, *,
               status: str, artifact_sha256: str) -> None:
        if status not in {'EXECUTED', 'MODEL_SQL_ERROR', 'MODEL_GENERATION_FAILURE',
                          'INFRASTRUCTURE_BLOCKED'}:
            raise ValueError('Unknown experiment terminal status')
        if len(artifact_sha256) != 64:
            raise ValueError('Final artifact SHA-256 required')
        with sqlite3.connect(self.path, timeout=30, isolation_level=None) as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT status FROM case_runs WHERE phase=? AND method=? AND case_id=?',
                             (phase, method, case_id)).fetchone()
            if row is None or row[0] != 'STARTED':
                db.execute('ROLLBACK')
                raise PermissionError('Case was not claimed or has already finished')
            db.execute('UPDATE case_runs SET status=?,artifact_sha256=? '
                       'WHERE phase=? AND method=? AND case_id=?',
                       (status, artifact_sha256, phase, method, case_id))
            db.execute('COMMIT')

    def checkpoints(self, phase: str) -> list[CaseCheckpoint]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute('SELECT phase,method,case_id,status,artifact_sha256 '
                              'FROM case_runs WHERE phase=? ORDER BY method,case_id',
                              (phase,)).fetchall()
        return [CaseCheckpoint(*row) for row in rows]
