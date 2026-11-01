"""Regressions for the independently reproduced audit findings of 2026-11-01."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from english_metrics import load_records, score_records
from reference_renderer import ABSTENTION_TEXT, render_answer


@pytest.mark.parametrize("name,contents", [
    ("ids.json", '{"q":"wrong answer","q":"right answer"}'),
    ("fields.jsonl", '{"id":"q","output_text":"wrong","output_text":"right"}\n'),
    ("ids.jsonl", '{"id":"q","id":"another","output_text":"right"}\n'),
    ("nested.json", '{"q":{"output_text":"wrong","output_text":"right"}}'),
])
def test_duplicate_keys_rejected_before_json_can_erase_them(tmp_path, name, contents):
    file = tmp_path / name
    file.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate JSON key"):
        load_records(file)


@pytest.mark.parametrize("text,answerable,rows", [
    (render_answer([[4]]), True, [[3]]),
    (ABSTENTION_TEXT, True, [[3]]),
    (render_answer([[3]]), False, None),
    ("Three is the answer.", True, [[3]]),
])
def test_inconsistent_or_noncontrolled_reference_fails_instead_of_grading(tmp_path, text, answerable, rows):
    refs = [{"id": "q", "output_text": text, "answerable": answerable, "result_rows": rows}]
    with pytest.raises(ValueError, match="Invalid controlled reference"):
        score_records(refs, {"q": render_answer([[3]])})


def test_free_prose_still_available_in_lexical_only_mode():
    refs = [{"id": "q", "output_text": "The patient had three admissions."}]
    report = score_records(refs, {"q": refs[0]["output_text"]}, controlled=False)
    assert report["lexical"]["normalized_EM"] == 100


def test_correct_json_input_and_reference_still_score(tmp_path):
    file = tmp_path / "predictions.json"
    # Use the real JSON encoder so this test verifies the loader, not escaping.
    import json
    file.write_text(json.dumps({"q": render_answer([[3]])}), encoding="utf-8")
    refs = [{"id": "q", "output_text": render_answer([[3]]), "answerable": True, "result_rows": [[3]]}]
    assert score_records(refs, load_records(file))["controlled"]["fact_EM"] == 100
