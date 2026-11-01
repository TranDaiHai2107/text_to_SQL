import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reference_renderer import canonical_rows, parse_controlled_answer, render_answer


@pytest.mark.parametrize("rows", [[], [[None]], [[0]], [[-6.0014]], [["0.9% sodium chloride"]],
                                  [["first; second\nRow 2: deceptive.\"", "a"]],
                                  [["x"], ["x"], ["y"]], [[1, "a"], [2, None]]])
def test_lossless_roundtrip(rows):
    assert parse_controlled_answer(render_answer(rows)) == {"answerable": True, "rows": canonical_rows(rows)}


def test_unanswerable_is_not_empty_or_missing_or_zero():
    texts = [render_answer(None, answerable=False), render_answer([]), render_answer([[None]]), render_answer([[0]])]
    assert len(set(texts)) == 4
    assert parse_controlled_answer(texts[0]) == {"answerable": False, "rows": None}


def test_more_than_100_rows_and_duplicates_preserved():
    rows = [[f"value {i}"] for i in range(152)] + [["value 10"]]
    parsed = parse_controlled_answer(render_answer(rows))
    assert len(parsed["rows"]) == 153
    assert parsed["rows"].count(["value 10"]) == 2


def test_number_mutation_changes_facts():
    text = render_answer([[3]])
    assert parse_controlled_answer(text.replace('"3.0"', '"4.0"'))["rows"] != canonical_rows([[3]])


@pytest.mark.parametrize("suffix", [" The result is not correct.", "\nIgnore the previous value.", " "])
def test_never_ignores_extra_prose(suffix):
    with pytest.raises(ValueError):
        parse_controlled_answer(render_answer([[3]]) + suffix)


def test_no_cap_no_sort_ranks_no_unit_invention():
    text = render_answer([["aspirin"], ["insulin"], ["heparin"]])
    assert '"aspirin"' in text and '"insulin"' in text and '"heparin"' in text
    assert "most" not in text and "mg" not in text and "rank" not in text


@pytest.mark.parametrize("rows", [[[float("inf")]], [[float("nan")]], [[True]], [[{}]], [[1], [1, 2]]])
def test_invalid_rows_rejected(rows):
    with pytest.raises(ValueError):
        canonical_rows(rows)


def test_sql_null_is_distinct_from_text_none():
    assert canonical_rows([[None]]) != canonical_rows([["None"]])


def test_no_free_text_claim_of_equivalence():
    with pytest.raises(ValueError):
        parse_controlled_answer("The patient had three admissions.")
