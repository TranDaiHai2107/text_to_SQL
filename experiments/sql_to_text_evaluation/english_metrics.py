"""Independent English-answer evaluation; never imports or changes the SQL scorer.

The lexical metrics measure wording similarity to generated references, not clinical
truth. controlled_fact_EM is an exact result-equivalence check only for the
explicit, reversible answer format produced by reference_renderer.py. It is not
a semantic judge of arbitrary English prose.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import unicodedata
from typing import Callable, Mapping


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise ValueError("English output must be a string; use an empty string for a failed output")
    # No article, negation, punctuation, sign, or decimal removal.
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def tokenize(text: str) -> list[str]:
    return normalize_text(text).split()


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    """Unit-cost token Levenshtein distance, including insertions/deletions."""
    if reference == hypothesis:
        return 0
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for i, real in enumerate(reference, 1):
        current = [i]
        for j, predicted in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (real != predicted)))
        previous = current
    return previous[-1]


def lcs_length(reference: list[str], hypothesis: list[str]) -> int:
    """ROUGE-L longest common subsequence; row memory is O(min(n,m))."""
    if reference == hypothesis:
        return len(reference)
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = [0] * (len(hypothesis) + 1)
    for real in reference:
        current = [0]
        for j, predicted in enumerate(hypothesis, 1):
            current.append(previous[j - 1] + 1 if real == predicted
                           else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def _f1(overlap: int, reference_count: int, prediction_count: int) -> float:
    if reference_count == prediction_count == 0:
        return 1.0
    return 2.0 * overlap / (reference_count + prediction_count)


def lexical_pair(reference: str, prediction: str) -> dict:
    real, predicted = tokenize(reference), tokenize(prediction)
    overlap = sum((Counter(real) & Counter(predicted)).values())
    return {
        "raw_EM": reference == prediction,
        "normalized_EM": real == predicted,
        "token_F1": _f1(overlap, len(real), len(predicted)),
        "ROUGE_L_F1": _f1(lcs_length(real, predicted), len(real), len(predicted)),
        "edit_distance": edit_distance(real, predicted),
        "reference_tokens": len(real),
        "prediction_tokens": len(predicted),
        "matched_tokens": overlap,
    }


def _records(value, *, references: bool) -> dict[str, dict]:
    if isinstance(value, dict) and isinstance(value.get("data"), list):
        value = value["data"]
    if isinstance(value, Mapping):
        rows = []
        for identifier, item in value.items():
            if isinstance(item, str) and not references:
                rows.append({"id": identifier, "output_text": item})
            elif isinstance(item, dict):
                if "id" in item and item["id"] != identifier:
                    raise ValueError("Mapping key and embedded ID disagree")
                rows.append({**item, "id": identifier})
            else:
                raise ValueError("Records must contain output_text strings")
    elif isinstance(value, list):
        rows = value
    else:
        raise ValueError("Expected a list of records or an ID mapping")
    result = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ValueError("Every record needs a non-empty string ID")
        if row["id"] in result:
            raise ValueError(f"Duplicate ID: {row['id']}")
        normalize_text(row.get("output_text"))
        if references and "answerable" in row and not isinstance(row["answerable"], bool):
            raise ValueError("answerable must be a boolean")
        result[row["id"]] = row
    if not result:
        raise ValueError("Cannot score an empty dataset")
    return result


def _controlled_tools():
    if __package__:
        from .reference_renderer import canonical_rows, parse_controlled_answer
    else:
        from reference_renderer import canonical_rows, parse_controlled_answer
    return parse_controlled_answer, canonical_rows


def _controlled_pair(reference: dict, text: str, parser: Callable,
                     canonicalizer: Callable) -> dict:
    if not isinstance(reference.get("answerable"), bool) or "result_rows" not in reference:
        raise ValueError("Controlled scoring requires answerable and result_rows in every reference")
    # Invalid references stop the evaluation. Invalid PREDICTED text is a failed
    # parse and remains in the denominator, including malformed/deeply nested JSON.
    if not reference["answerable"] and reference["result_rows"] is not None:
        raise ValueError("Unanswerable references cannot carry result rows")
    expected_rows = canonicalizer(reference["result_rows"]) if reference["answerable"] else None
    # Gold English text must express the SAME facts as its structured result.
    # Otherwise lexical and fact scores would silently grade different targets.
    try:
        gold_text = parser(reference["output_text"])
        if not isinstance(gold_text, dict) or not isinstance(gold_text.get("answerable"), bool):
            raise ValueError("Invalid reference parser result")
        gold_rows = canonicalizer(gold_text["rows"]) if gold_text["answerable"] else None
        if (gold_text["answerable"] != reference["answerable"] or gold_rows != expected_rows
                or (not gold_text["answerable"] and gold_text.get("rows") is not None)):
            raise ValueError("Reference text and result_rows disagree")
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError) as error:
        raise ValueError("Invalid controlled reference text or inconsistent result_rows") from error
    try:
        parsed = parser(text)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("answerable"), bool):
            raise ValueError("Controlled parser returned an invalid result")
        actual_rows = canonicalizer(parsed["rows"]) if parsed["answerable"] else None
        if not parsed["answerable"] and parsed.get("rows") is not None:
            raise ValueError("Unanswerable predictions cannot carry result rows")
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError):
        return {"controlled_parseable": False, "controlled_fact_EM": False}
    correct = parsed["answerable"] == reference["answerable"] and actual_rows == expected_rows
    return {"controlled_parseable": True, "controlled_fact_EM": correct}


def _aggregate(rows: list[dict], controlled: bool) -> dict:
    n = len(rows)
    reference_tokens = sum(r["reference_tokens"] for r in rows)
    predicted_tokens = sum(r["prediction_tokens"] for r in rows)
    edits = sum(r["edit_distance"] for r in rows)
    # No reference words with non-empty predictions has an undefined WER.
    wer = 100 * edits / reference_tokens if reference_tokens else (0.0 if edits == 0 else None)
    result = {
        "n": n,
        "lexical": {
            "raw_EM": 100 * sum(r["raw_EM"] for r in rows) / n,
            "normalized_EM": 100 * sum(r["normalized_EM"] for r in rows) / n,
            "token_F1_macro": 100 * sum(r["token_F1"] for r in rows) / n,
            "token_F1_micro": 100 * _f1(sum(r["matched_tokens"] for r in rows),
                                        reference_tokens, predicted_tokens),
            "ROUGE_L_F1_macro": 100 * sum(r["ROUGE_L_F1"] for r in rows) / n,
            "WER": wer,
            "WER_edit_distance": edits,
            "WER_reference_tokens": reference_tokens,
            "WER_prediction_tokens": predicted_tokens,
        },
    }
    if controlled:
        result["controlled"] = {
            "fact_EM": 100 * sum(r["controlled_fact_EM"] for r in rows) / n,
            "parse_coverage": 100 * sum(r["controlled_parseable"] for r in rows) / n,
            "correct": sum(r["controlled_fact_EM"] for r in rows),
            "parseable": sum(r["controlled_parseable"] for r in rows),
        }
    return result


def score_records(references, predictions, *, controlled: bool = True,
                  controlled_parser: Callable | None = None,
                  canonicalizer: Callable | None = None) -> dict:
    """Score every ID once; missing/extra/duplicate IDs fail rather than vanish.

    Empty-string predictions are explicit failed outputs and remain in all
    denominators. Passing result_rows in predictions cannot affect factual scores:
    controlled facts are parsed from the prediction TEXT only. For arbitrary
    English answers use controlled=False; lexical scores cannot validate facts.
    """
    real = _records(references, references=True)
    predicted = _records(predictions, references=False)
    if set(real) != set(predicted):
        raise ValueError(f"IDs must match exactly: missing={len(set(real)-set(predicted))}, "
                         f"extra={len(set(predicted)-set(real))}")
    if controlled:
        if (controlled_parser is None) != (canonicalizer is None):
            raise ValueError("Supply both controlled_parser and canonicalizer, or neither")
        if controlled_parser is None:
            controlled_parser, canonicalizer = _controlled_tools()
    details = {}
    for identifier, row in real.items():
        text = predicted[identifier]["output_text"]
        item = lexical_pair(row["output_text"], text)
        if controlled:
            item.update(_controlled_pair(row, text, controlled_parser, canonicalizer))
        if "answerable" in row:
            item["answerable"] = row["answerable"]
        details[identifier] = item
    scores = _aggregate(list(details.values()), controlled)
    groups = {}
    for label, expected in (("answerable", True), ("unanswerable", False)):
        group = [r for r in details.values() if r.get("answerable") is expected]
        if group:
            groups[label] = _aggregate(group, controlled)
    return {
        "metric_version": "english_reference_v1",
        "scope": "Similarity to generated English references; not expert clinical validation",
        "tokenization": "Unicode NFKC, casefold, whitespace tokens; signs, punctuation and negation retained",
        "units": "All aggregate scores are percentages; WER is lower-better and may exceed 100",
        "controlled_metric_scope": "Exact result equivalence parsed from controlled English TEXT; arbitrary prose can be unparseable",
        "missing_output_policy": "IDs must match exactly; explicit empty output counts as failure",
        **scores,
        "groups": groups,
        "per_question": details,
    }


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def load_records(path: Path):
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line, object_pairs_hook=_unique_json_object)
                for line in path.read_text(encoding="utf-8-sig").splitlines()
                if line.strip()]
    return json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=_unique_json_object)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--lexical-only", action="store_true",
                        help="Disable controlled fact parsing for general English prose")
    args = parser.parse_args()
    result = score_records(load_records(args.references), load_records(args.predictions),
                           controlled=not args.lexical_only)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "per_question"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
