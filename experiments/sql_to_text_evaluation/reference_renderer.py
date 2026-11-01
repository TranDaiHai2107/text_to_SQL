"""Lossless controlled-English rendering of query results, never clinical inference.

This is a NEW answer format, not an official EHRSQL English reference.
Only statements about returned values/rows are made: no guessed units, ranks,
yes/no interpretations, patient attributes, or explanations of SQL semantics.
"""
from __future__ import annotations

import json
import math
import re

RENDERER_VERSION = "controlled_english_values_v1"
ABSTENTION_TEXT = "This question cannot be answered using the available database."
EXECUTION_ERROR_TEXT = "The system could not execute the query."
EMPTY_TEXT = "The query returned no rows."


def canonical_cell(value):
    if value is None:
        return None  # Missing SQL value is NOT an unanswerable question.
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        raise ValueError("Unsupported SQLite cell type")
    try:
        numeric = float(value)
    except (ValueError, TypeError):
        return str(value)
    if not math.isfinite(numeric):
        raise ValueError("Non-finite numeric cell cannot be silently rendered")
    return str(round(numeric, 3))


def canonical_rows(rows):
    """Numeric3, unordered rows, preserving column order, duplicates and SQL NULL.

    Unlike the official scorer there is NO 100-row cap. This is explicitly a
    different full-result representation. Numeric-looking strings follow the
    existing official numeric3 equivalence, including numeric identifiers.
    """
    if not isinstance(rows, (list, tuple)):
        raise ValueError("Rows must be a sequence")
    result = []
    width = None
    for row in rows:
        if not isinstance(row, (list, tuple)) or not row:
            raise ValueError("Each result row must contain at least one cell")
        if width is None:
            width = len(row)
        if len(row) != width:
            raise ValueError("Inconsistent result row widths")
        result.append([canonical_cell(cell) for cell in row])
    return sorted(result, key=lambda row: tuple(("None" if v is None else v, v is not None) for v in row))


def render_answer(rows=None, *, answerable=True):
    if not answerable:
        if rows is not None:
            raise ValueError("Unanswerable questions must not carry result rows")
        return ABSTENTION_TEXT
    result = canonical_rows(rows)
    if not result:
        return EMPTY_TEXT
    if len(result) == 1 and len(result[0]) == 1:
        return "The returned value is " + json.dumps(result[0][0], ensure_ascii=False) + "."
    lines = [f"The query returned {len(result)} rows."]
    lines.extend(f"Row {i}: {json.dumps(row, ensure_ascii=False)}." for i, row in enumerate(result, 1))
    return "\n".join(lines)


def parse_controlled_answer(text):
    """Strictly extract facts FROM TEXT. Additional prose is never ignored.

    Unparseable ordinary English is not necessarily false; it simply cannot be
    automatically certified by this restricted parser. Report parse coverage.
    """
    if not isinstance(text, str):
        raise ValueError("Answer must be text")
    if text == ABSTENTION_TEXT:
        return {"answerable": False, "rows": None}
    if text == EMPTY_TEXT:
        return {"answerable": True, "rows": []}
    prefix = "The returned value is "
    if text.startswith(prefix) and text.endswith("."):
        cell = json.loads(text[len(prefix):-1])
        if cell is not None and not isinstance(cell, str):
            raise ValueError("Cells must be canonical strings or null")
        rows = canonical_rows([[cell]])
    else:
        lines = text.splitlines()
        match = re.fullmatch(r"The query returned ([1-9][0-9]*) rows\.", lines[0] if lines else "")
        if not match or len(lines) != int(match[1]) + 1:
            raise ValueError("Unsupported answer format or row count")
        decoded = []
        for index, line in enumerate(lines[1:], 1):
            row_prefix = f"Row {index}: "
            if not line.startswith(row_prefix) or not line.endswith("."):
                raise ValueError("Malformed row")
            row = json.loads(line[len(row_prefix):-1])
            if not isinstance(row, list) or any(cell is not None and not isinstance(cell, str) for cell in row):
                raise ValueError("Cells must be canonical strings or null")
            decoded.append(row)
        rows = canonical_rows(decoded)
    # Canonical grammar is deliberate: cannot append contradictory claims,
    # manipulate row ordering, or smuggle a partial parse and still pass.
    if render_answer(rows) != text:
        raise ValueError("Noncanonical controlled answer")
    return {"answerable": True, "rows": rows}
