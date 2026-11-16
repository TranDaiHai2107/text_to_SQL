"""Pure port of SDE refine_new.is_need_refine's result-shape decision."""
from __future__ import annotations


def native_refinement_reason(rows, *, try_times: int, max_try_times: int) -> str | None:
    """Return native reason without inspecting or exporting actual cell values."""
    if try_times >= max_try_times:
        return None
    if rows is None:
        return 'execution_error'
    if len(rows) == 0:
        return 'no data selected'
    if len(rows) == 1:
        return None
    has_null = any(value is None for row in rows for value in row)
    has_non_null = any(value is not None for row in rows for value in row)
    if has_null and has_non_null:
        return 'exist None value, you can add `IS NOT NULL` for the query targets in SQL'
    return None
