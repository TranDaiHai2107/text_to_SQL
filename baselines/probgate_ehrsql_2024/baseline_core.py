"""Offline adapters for the published postprocessing rules.

No LLM SDK, application imports, network, training, or unsafe pickle loading.
Author source is preserved separately under upstream/.
"""
from __future__ import annotations

from ast import literal_eval
import importlib.util
import math
from pathlib import Path
import sqlite3
import time

ROOT = Path(__file__).resolve().parent


def post_process_sql(sql):
    path = ROOT / "upstream/src/scoring_program/postprocessing.py"
    spec = importlib.util.spec_from_file_location("probgate_original_postprocessing", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.post_process_sql(sql)


def bottom_logprob(logs, reserved, bottom_n=10):
    if not isinstance(bottom_n, int) or bottom_n < 1:
        raise ValueError("bottom_n must be a positive integer")
    values = sorted(row["logprob"] for row in logs if row["token"].strip() not in reserved)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("Non-finite token log probability")
    if not values:
        raise ValueError("No non-reserved tokens; upstream division is undefined. Cannot invent confidence.")
    values = values[:bottom_n]
    return sum(values) / len(values)


def apply_probgate(raw, reserved, rank_index, bottom_n=10):
    if not 0 <= rank_index < len(raw):
        raise ValueError("ProbGate threshold is a zero-based rank index, not a probability.")
    means = {key: bottom_logprob(value[1], reserved, bottom_n) for key, value in raw.items()}
    cutoff = sorted(means.values())[rank_index]
    # Notebook uses <=, so ties can abstain on more than index+1 questions.
    predictions = {key: "null" if means[key] <= cutoff else post_process_sql(value[0]) for key, value in raw.items()}
    return predictions, {"rank_index": rank_index, "bottom_n": bottom_n, "cutoff": cutoff,
        "abstained": sum(v == "null" for v in predictions.values())}


def apply_entropy(predictions, entropy, threshold):
    if set(predictions) != set(entropy):
        raise ValueError("Entropy IDs do not cover the prediction split exactly.")
    return {key: "null" if max(entropy[key]) > threshold else value for key, value in predictions.items()}


def apply_classifier(predictions, classifier):
    if set(predictions) != set(classifier):
        raise ValueError("Classifier IDs do not cover the prediction split exactly.")
    if any(v not in {"null", "answerable"} for v in classifier.values()):
        raise ValueError("Classifier labels must be 'answerable' or 'null'; no implicit label inversion.")
    return {key: "null" if classifier[key] == "null" else value for key, value in predictions.items()}


def process_item(item):
    try:
        item = round(float(item), 3)
    except (ValueError, TypeError):
        pass
    return str(item)


def process_answer(answer):
    try:
        answer = literal_eval(answer)
    except (ValueError, TypeError, SyntaxError):
        pass
    if isinstance(answer, str):
        return answer
    return str(sorted([[process_item(value) for value in row] for row in answer])[:100])


def author_process_answer(answer):
    """Released ProbGate helper sorts full rows, without rounding/capping."""
    if isinstance(answer, str):
        return answer
    return sorted([list(row) for row in answer])


def execute_readonly(sql, db, timeout_s=30):
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("SQL timeout must be positive and finite")
    connection = sqlite3.connect(Path(db).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        connection.text_factory = lambda value: value.decode(errors="ignore")
        connection.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + timeout_s
        connection.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
        return connection.execute(sql).fetchall()
    finally:
        connection.close()


def apply_gef(predictions, db, timeout_s=30):
    output = {}
    errors = []
    for key, sql in predictions.items():
        if sql == "null":
            output[key] = "null"
            continue
        try:
            result = author_process_answer(execute_readonly(sql, db, timeout_s))
            # Preserve the author's additional empty-result filtering in code,
            # even though section 3.5 describes execution errors only.
            output[key] = "null" if "error" in result or result == [] or result == "[]" or result == "['']" else sql
        except (sqlite3.Error, TypeError, ValueError) as error:
            output[key] = "null"
            errors.append({"id": key, "error": str(error)})
    return output, errors


def score_answers(gold, predicted, scorer="official"):
    if scorer not in {"author", "official"}:
        raise ValueError("Unknown scorer")
    if set(gold) != set(predicted):
        raise ValueError("Gold/prediction IDs must match exactly; failures cannot be dropped.")
    n = len(gold)
    if n == 0:
        raise ValueError("Empty evaluation split")
    correct = wrong = abstained_answerable = 0
    details = {}
    normalizer = author_process_answer if scorer == "author" else process_answer
    for key in gold:
        real, pred = normalizer(gold[key]), normalizer(predicted[key])
        if real == pred:
            outcome = "correct"
            correct += 1
        elif real != "null" and pred == "null":
            outcome = "abstained_answerable"
            abstained_answerable += 1
        else:
            outcome = "wrong"
            wrong += 1
        details[key] = outcome
    return {"n": n, "correct": correct, "wrong": wrong,
        "abstained_answerable": abstained_answerable,
        "scores": {name: 100*(correct-penalty*wrong)/n for name, penalty in
                   [("RS0", 0), ("RS5", 5), ("RS10", 10), ("RSN", n)]},
        "per_question": details}
