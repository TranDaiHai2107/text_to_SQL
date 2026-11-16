"""Phase C pilot approval, deliberately distinct from four-hash Phase A approval."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from .config import BigQueryConfig
from .execution_control import EXPECTED_DATASETS, EXPECTED_PROJECT, READER_PRINCIPAL
from .metadata import verify_schema_manifest


@dataclass(frozen=True)
class BenchmarkExecutionApproval:
    expected_phase = 'phase_c1_validation_pilot'

    def _valid_case_scope(self):
        return (len(set(self.case_ids)) == 5 and len(self.case_ids) == 5 and
                all(case_id and not case_id.startswith('test/') for case_id in self.case_ids))
    approval_id: str
    approver: str
    authority: str
    risk_acknowledged: bool
    iam_status: str
    valid_from_utc: datetime
    valid_until_utc: datetime
    principal: str
    project_id: str
    datasets: tuple[str, ...]
    location: str
    manifest_sha256: str
    pilot_manifest_sha256: str
    model_id: str
    case_ids: tuple[str, ...]
    max_bytes_billed_per_sql: int
    timeout_seconds: int
    max_rows: int
    max_result_bytes: int
    api_budget_sha256: str
    sql_budget_sha256: str
    result_storage_policy_reference: str
    artifact_retention_days: int
    phase: str = 'phase_c1_validation_pilot'

    @classmethod
    def from_file(cls, path: Path) -> 'BenchmarkExecutionApproval':
        payload = json.loads(Path(path).read_text(encoding='utf-8'))
        if set(payload) != set(cls.__dataclass_fields__):
            raise ValueError('Benchmark approval fields differ from required schema')
        for field in ('valid_from_utc', 'valid_until_utc'):
            payload[field] = datetime.fromisoformat(payload[field].replace('Z', '+00:00'))
        for field in ('datasets', 'case_ids'):
            payload[field] = tuple(payload[field])
        return cls(**payload)

    def __post_init__(self):
        if self.phase != self.expected_phase:
            raise ValueError('Approval phase cannot authorize this benchmark pilot')
        if self.iam_status != 'READ_ONLY_LIKELY_WITH_APPROVED_RISK' or not self.risk_acknowledged:
            raise ValueError('Inherited IAM risk acceptance must be explicit and truthful')
        if (self.principal != READER_PRINCIPAL or self.project_id != EXPECTED_PROJECT or
            set(self.datasets) != EXPECTED_DATASETS or self.location.upper() != 'US'):
            raise ValueError('Benchmark approval does not match reader and MIMIC scope')
        if not all((self.approval_id, self.approver, self.authority,
                    self.result_storage_policy_reference, self.api_budget_sha256,
                    self.sql_budget_sha256)):
            raise ValueError('Approval identity, budget hashes and storage policy are required')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', self.approval_id):
            raise ValueError('Unsafe approval identifier')
        if (self.valid_from_utc.tzinfo is None or self.valid_until_utc.tzinfo is None or
            self.valid_until_utc <= self.valid_from_utc):
            raise ValueError('Valid UTC approval window required')
        if not self._valid_case_scope():
            raise ValueError('Invalid approval case IDs')
        if min(self.max_bytes_billed_per_sql, self.timeout_seconds, self.max_rows,
               self.max_result_bytes,
               self.artifact_retention_days) <= 0 or self.max_rows == 1:
            raise ValueError('Positive benchmark limits and multi-row output required')
        for digest in (self.manifest_sha256, self.pilot_manifest_sha256,
                       self.api_budget_sha256, self.sql_budget_sha256):
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Approval requires SHA-256 digests')

    def verify_pilot(self, pilot_manifest: dict) -> None:
        if (pilot_manifest.get('sha256') != self.pilot_manifest_sha256 or
            tuple(row['case_id'] for row in pilot_manifest['cases']) != self.case_ids):
            raise PermissionError('Approval does not match the five pinned development cases')

    def verify_active(self, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self.valid_from_utc <= now <= self.valid_until_utc:
            raise PermissionError('Benchmark approval is outside its validity window')

    def authorize(self, *, case_id: str, sql: str, config: BigQueryConfig,
                  manifest: dict, max_bytes_billed: int, timeout_seconds: int,
                  max_rows: int, max_result_bytes: int | None = None,
                  now: datetime | None = None) -> None:
        self.verify_active(now)
        verify_schema_manifest(manifest)
        if (manifest['sha256'] != self.manifest_sha256 or
            config.project_id != self.project_id or config.location.upper() != self.location.upper() or
            set(config.allowed_datasets) != set(self.datasets)):
            raise PermissionError('Benchmark approval does not match BigQuery scope')
        if (case_id not in self.case_ids or not sql.strip() or
            max_bytes_billed > self.max_bytes_billed_per_sql or
            timeout_seconds > self.timeout_seconds or max_rows > self.max_rows + 1 or
            (max_result_bytes is not None and max_result_bytes > self.max_result_bytes)):
            raise PermissionError('SQL case or limits exceed approved pilot scope')
