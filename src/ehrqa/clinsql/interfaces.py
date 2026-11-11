"""Common interfaces for method comparison; execution requires an injected adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Any


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


class DatabaseInterface(Protocol):
    def schema_metadata(self) -> list[dict]: ...
    def dry_run(self, sql: str) -> DryRun: ...
    def probe(self, sql: str) -> Execution: ...
    def execute(self, sql: str) -> Execution: ...


class EvaluationInterface(Protocol):
    def evaluate_saved_predictions(self, prediction_dir: str, *, split: str) -> dict: ...
