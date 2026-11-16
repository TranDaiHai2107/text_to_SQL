"""Common contracts; no CLINSQL, MIMIC, provider or SQL dialect dependency."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class DryRun:
    estimated_bytes: int
    valid: bool
    redacted_error: str | None = None


@dataclass(frozen=True)
class Execution:
    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    complete: bool
    bytes_billed: int | None = None
    column_types: tuple[str, ...] = ()
    job_id: str | None = None
    bytes_processed: int | None = None
    latency_seconds: float | None = None


@dataclass(frozen=True)
class ProbePresence:
    total_rows: int
    job_id: str | None = None
    bytes_billed: int | None = None
    bytes_processed: int | None = None
    latency_seconds: float | None = None

    @property
    def has_rows(self) -> bool:
        return self.total_rows > 0


class DatabaseInterface(Protocol):
    def schema_metadata(self) -> list[dict]: ...
    def dry_run(self, sql: str) -> DryRun: ...
    def probe(self, sql: str) -> Execution: ...
    def execute(self, sql: str) -> Execution: ...


class EvaluationInterface(Protocol):
    def evaluate_saved_predictions(self, prediction_dir: str, *, split: str) -> dict: ...
