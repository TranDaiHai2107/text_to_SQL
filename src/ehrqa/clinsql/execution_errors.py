"""Stable, redacted execution failures for research accounting."""
from __future__ import annotations
import re


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


# Whitelisted, value-free BigQuery error classes. Only the class label leaves
# the database layer; identifiers, literals and row content never do. The first
# two are exactly the classes the CLINSQL CoT baseline forwards to refinement.
SQL_ERROR_CLASSES = (
    ('unrecognized name', r'unrecognized name'),
    ('syntax error', r'syntax error'),
    ('no matching signature', r'no matching signature'),
    ('function not found', r'function not found'),
    ('table not found', r'not found: table|table .* was not found'),
    ('ambiguous column', r'ambiguous'),
    ('grouping error', r'neither grouped nor aggregated|cannot be grouped'),
    ('type mismatch', r'cannot coerce|incompatible types|cannot be compared|operator .* for argument types'),
    ('invalid date/time', r'invalid (?:date|timestamp|datetime|interval)'),
)
_CLASS_MARKER = 'sql error class: '


def redacted_sql_error_class(message: str) -> str:
    """Return a whitelisted class label from a (possibly translated) error."""
    text = (message or '').lower()
    if _CLASS_MARKER in text:
        text = text.split(_CLASS_MARKER, 1)[1]
    for label, pattern in SQL_ERROR_CLASSES:
        if re.search(pattern, text):
            return label
    return 'details withheld'


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
                label = redacted_sql_error_class(str(exc))
                if label == 'details withheld':
                    return ValueError('BigQuery SQL error; details withheld')
                return ValueError(f'BigQuery SQL error; {_CLASS_MARKER}{label}; details withheld')
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
