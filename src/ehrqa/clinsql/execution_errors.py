"""Stable, redacted execution failures for research accounting."""
from __future__ import annotations


class SecurityRejected(PermissionError):
    """SQL was blocked by the application guard before a query job."""


class BudgetExceeded(PermissionError):
    """The dry run or BigQuery job exceeds an approved bytes cap."""

    def __init__(self, message: str, *, estimated_bytes: int | None = None,
                 cap_bytes: int | None = None):
        super().__init__(message)
        self.estimated_bytes = estimated_bytes
        self.cap_bytes = cap_bytes


class IncompleteResultError(RuntimeError):
    """A row or byte cap stopped result retrieval; never score this output."""


class ResourceBudgetBlocked(BudgetExceeded):
    """The approved research credit envelope cannot cover this query."""


def classify_execution_failure(exc: BaseException, *, stage: str) -> str:
    """Classify failures without inspecting or persisting raw database error text."""
    if isinstance(exc, SecurityRejected):
        return 'SECURITY_REJECTED'
    if isinstance(exc, ResourceBudgetBlocked):
        return 'RESOURCE_BUDGET_BLOCKED'
    if isinstance(exc, BudgetExceeded):
        return 'BUDGET_EXCEEDED'
    if isinstance(exc, IncompleteResultError):
        return 'INCOMPLETE_RESULT'
    if isinstance(exc, TimeoutError):
        return 'TIMEOUT'
    if isinstance(exc, PermissionError):
        return 'PERMISSION_DENIED'
    if isinstance(exc, ConnectionError):
        return 'INFRASTRUCTURE_ERROR'
    if isinstance(exc, ValueError):
        return 'SQL_SYNTAX_ERROR' if stage == 'dry_run' else 'SQL_EXECUTION_ERROR'
    return 'INFRASTRUCTURE_ERROR'


def translate_bigquery_exception(exc: Exception) -> Exception:
    """Map SDK errors to non-SQL failures where appropriate; redact messages."""
    try:
        from google.api_core import exceptions as api_errors
    except ImportError:
        api_errors = None
    if api_errors is not None:
        if isinstance(exc, (api_errors.Forbidden, api_errors.Unauthorized)):
            return PermissionError('BigQuery permission denied; details withheld')
        if isinstance(exc, api_errors.DeadlineExceeded):
            return TimeoutError('BigQuery timeout; details withheld')
        if isinstance(exc, (api_errors.ServiceUnavailable, api_errors.TooManyRequests,
                            api_errors.InternalServerError)):
            return ConnectionError('BigQuery service error; details withheld')
        if isinstance(exc, api_errors.BadRequest):
            reasons = {item.get('reason') for item in (getattr(exc, 'errors', None) or ())
                       if isinstance(item, dict)}
            if 'bytesBilledLimitExceeded' in reasons:
                return BudgetExceeded('BigQuery bytes cap exceeded; details withheld')
            if 'accessDenied' in reasons:
                return PermissionError('BigQuery permission denied; details withheld')
            if 'invalidQuery' in reasons:
                return ValueError('BigQuery SQL error; details withheld')
            return ConnectionError('BigQuery job rejected; details withheld')
    if isinstance(exc, BudgetExceeded):
        return BudgetExceeded('BigQuery bytes cap exceeded; details withheld')
    if isinstance(exc, SecurityRejected):
        return SecurityRejected('SQL security guard rejected query')
    if isinstance(exc, PermissionError):
        return PermissionError('BigQuery permission denied; details withheld')
    if isinstance(exc, TimeoutError):
        return TimeoutError('BigQuery timeout; details withheld')
    if isinstance(exc, ConnectionError):
        return ConnectionError('BigQuery connection error; details withheld')
    if isinstance(exc, ValueError):
        return ValueError('BigQuery SQL error; details withheld')
    return ConnectionError('BigQuery infrastructure error; details withheld')
