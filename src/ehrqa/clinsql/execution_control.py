"""Fail-closed approval record for controlled BigQuery SELECT execution.

Loading an approval is explicit. This module never creates one or grants IAM rights.
An approval record is local evidence of a human decision, not an IAM attestation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .config import BigQueryConfig
from .metadata import verify_schema_manifest


READER_PRINCIPAL = 'kltn-sql-reader@kltn-text-to-sql.iam.gserviceaccount.com'
EXPECTED_PROJECT = 'kltn-text-to-sql'
EXPECTED_DATASETS = frozenset({f'{EXPECTED_PROJECT}.mimiciv_3_1_hosp',
                               f'{EXPECTED_PROJECT}.mimiciv_3_1_icu'})
PHASE_A_SQL_SHA256 = {
    'hosp_patients_count': 'e1288e2c90973fb125119f2e1952ce807b2128c5986b63526a8c6d71d791262f',
    'icu_icustays_count': '17dbee9fba2cc499105ac5d42ce8c694bbd97bd19d2c00cc2f2fc1568832863b',
    'icu_hosp_join': 'c380a6fabd58b6e850081a45deebf39b786e00a990b7af75ce9bcb3e53d5a985',
    'clinsql_validation_043': '2a8ffc1c1c57c6eaf52de47e2ab4621d417b8c8cf1d7e3d5e1a3fea061eb0fb7',
}
PHASE_A_MAX_BYTES = {'hosp_patients_count': 10_485_760,
                     'icu_icustays_count': 10_485_760,
                     'icu_hosp_join': 20_971_520,
                     'clinsql_validation_043': 24_117_248}


@dataclass(frozen=True)
class ExecutionApproval:
    approval_id: str
    approver: str
    authority: str
    organization_policy_clearance_reference: str
    iam_status: str
    risk_acknowledged: bool
    valid_from_utc: datetime
    valid_until_utc: datetime
    principal: str
    project_id: str
    datasets: tuple[str, ...]
    location: str
    manifest_sha256: str
    phase: str
    sql_sha256_by_case: dict[str, str]
    max_bytes_billed_by_case: dict[str, int]
    timeout_seconds: int
    max_rows: int
    result_storage_policy_reference: str
    artifact_retention_days: int = 7

    @classmethod
    def from_file(cls, path: Path) -> 'ExecutionApproval':
        return cls.from_json_bytes(Path(path).read_bytes())

    @classmethod
    def from_json_bytes(cls, raw: bytes) -> 'ExecutionApproval':
        data = json.loads(raw.decode('utf-8'))
        required = {field for field in cls.__dataclass_fields__}
        if set(data) != required:
            raise ValueError('Approval record fields differ from the required schema')
        for name in ('valid_from_utc', 'valid_until_utc'):
            data[name] = datetime.fromisoformat(data[name].replace('Z', '+00:00'))
        data['datasets'] = tuple(data['datasets'])
        return cls(**data)

    def __post_init__(self):
        if self.iam_status not in {'VERIFIED_READ_ONLY', 'READ_ONLY_LIKELY_WITH_APPROVED_RISK'}:
            raise ValueError('Unsupported IAM execution mode')
        if self.iam_status.endswith('APPROVED_RISK') and not self.risk_acknowledged:
            raise ValueError('Unverified inherited IAM requires explicit risk acceptance')
        if self.phase != 'phase_a_smoke':
            raise ValueError('Only Phase A has an implemented execution approval gate')
        if not all((self.approval_id, self.approver, self.authority,
                    self.result_storage_policy_reference)):
            raise ValueError('Approval identity, authority and storage decision are required')
        if (self.iam_status == 'VERIFIED_READ_ONLY' and
                not self.organization_policy_clearance_reference):
            raise ValueError('Verified read-only mode requires Organization policy evidence')
        if (self.valid_from_utc.tzinfo is None or self.valid_until_utc.tzinfo is None or
                self.valid_until_utc <= self.valid_from_utc):
            raise ValueError('Approval requires an ordered UTC time window')
        if self.principal != READER_PRINCIPAL:
            raise ValueError('Approval must name the reader service account')
        if (self.project_id != EXPECTED_PROJECT or set(self.datasets) != EXPECTED_DATASETS or
                self.location.upper() != 'US'):
            raise ValueError('Approval must match the two authorized MIMIC-IV datasets in US')
        if (not self.sql_sha256_by_case or
                self.sql_sha256_by_case.keys() != self.max_bytes_billed_by_case.keys() or
                any(PHASE_A_SQL_SHA256.get(case_id) != digest
                    for case_id, digest in self.sql_sha256_by_case.items()) or
                any(value <= 0 for value in self.max_bytes_billed_by_case.values()) or
                any(value > PHASE_A_MAX_BYTES.get(case_id, 0)
                    for case_id, value in self.max_bytes_billed_by_case.items()) or
                not 0 < self.timeout_seconds <= 30 or not 0 < self.max_rows <= 2):
            raise ValueError('Approval must match the four fixed Phase A SQL hashes and caps')
        if not isinstance(self.artifact_retention_days, int) or not 1 <= self.artifact_retention_days <= 30:
            raise ValueError('Phase A artifact retention must be between 1 and 30 days')

    def authorize(self, *, case_id: str, sql: str, config: BigQueryConfig,
                  manifest: dict, max_bytes_billed: int, timeout_seconds: int,
                  max_rows: int, now: datetime | None = None) -> None:
        now = now or datetime.now(timezone.utc)
        if not self.valid_from_utc <= now <= self.valid_until_utc:
            raise PermissionError('Execution approval is not currently valid')
        verify_schema_manifest(manifest)
        if (config.project_id != self.project_id or config.location.upper() != self.location.upper() or
                set(config.allowed_datasets) != set(self.datasets) or
                manifest['sha256'] != self.manifest_sha256 or
                manifest['project_id'] != self.project_id or
                set(f"{self.project_id}.{name}" for name in manifest['datasets'].values()) != set(self.datasets)):
            raise PermissionError('Execution approval does not match the verified BigQuery scope')
        digest = hashlib.sha256(sql.encode('utf-8')).hexdigest()
        if case_id not in self.sql_sha256_by_case or digest != self.sql_sha256_by_case[case_id]:
            raise PermissionError('SQL is not in the approved Phase A set')
        if (max_bytes_billed > self.max_bytes_billed_by_case[case_id] or
                timeout_seconds > self.timeout_seconds or max_rows > self.max_rows):
            raise PermissionError('Query limits exceed the approved Phase A bounds')


def verify_reader_credentials(credentials) -> None:
    """Check the credential object that will submit a BigQuery query job."""
    from google.auth import impersonated_credentials
    if (not isinstance(credentials, impersonated_credentials.Credentials) or
            credentials.service_account_email != READER_PRINCIPAL):
        raise PermissionError('Query client is not using reader impersonation credentials')


def verify_reader_adc(*, scopes: list[str] | None = None):
    """Check ADC type and target without printing or refreshing a token."""
    import os
    import google.auth

    credentials, _ = (google.auth.default(scopes=scopes) if scopes else google.auth.default())
    if os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        raise PermissionError('Expected reader ADC impersonation is not active')
    verify_reader_credentials(credentials)
    return credentials
