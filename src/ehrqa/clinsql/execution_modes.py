"""Explicit row-limit profiles; benchmark execution remains approval-gated."""
from __future__ import annotations

from dataclasses import dataclass

from .bigquery_adapter import Limits
from .execution_control import PHASE_A_MAX_BYTES


@dataclass(frozen=True)
class SmokeExecutionConfig:
    case_id: str

    def limits(self) -> Limits:
        if self.case_id not in PHASE_A_MAX_BYTES:
            raise ValueError('Unknown Phase A smoke case')
        return Limits(PHASE_A_MAX_BYTES[self.case_id], timeout_seconds=30,
                      max_rows=1, allow_data_execution=True, case_id=self.case_id)


@dataclass(frozen=True)
class BenchmarkExecutionConfig:
    max_bytes_billed: int
    timeout_seconds: int
    max_rows: int
    max_result_bytes: int = 8_388_608

    def __post_init__(self):
        if (self.max_bytes_billed <= 0 or self.timeout_seconds <= 0 or
            self.max_rows <= 1 or self.max_result_bytes <= 0):
            raise ValueError('Benchmark output cap must exceed the one-row smoke limit')

    def limits(self, *, case_id: str, allow_data_execution: bool = False) -> Limits:
        if not case_id:
            raise ValueError('Benchmark case ID required')
        # The transport still requires its own future-scoped approval.
        return Limits(self.max_bytes_billed, timeout_seconds=self.timeout_seconds,
                      max_rows=self.max_rows, max_result_bytes=self.max_result_bytes,
                      allow_data_execution=allow_data_execution, case_id=case_id)
