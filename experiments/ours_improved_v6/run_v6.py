"""Dev-selected deterministic V6, followed by one frozen full-paper test replay.

No API/model calls. The inherited generation cost is not zero; only incremental
postprocessing uses no model. Existing 147 frozen artifacts remain unchanged.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[1]
EXPERIMENTS = HERE.parent
V5 = EXPERIMENTS / "ours_improved_v5"
V5_RUN = V5 / "runs/deepseek_flash_v5_20261029_r1"
BASELINE = WORKSPACE / "baselines/probgate_ehrsql_2024"
for folder in (HERE, V5, EXPERIMENTS / "ours_improved_v4", EXPERIMENTS / "ours_improved_v3", BASELINE):
    if str(folder) not in sys.path:
        sys.path.append(str(folder))

from baseline_core import execute_readonly, score_answers
from postprocess_v5 import load_metadata, select_v5
from risk_v3 import structure_signature

DB = BASELINE / "upstream/src/data/mimic_iv/mimic_iv.sqlite"
DEFAULT_RUN = HERE / "runs/reviewed_20261101_once"
POLICIES = (
    "v5_reference", "v6_strict3", "v6_pair_ast", "v6_pair_plan_ast",
    "v6_pair_nontrivial", "v6_pair_plan_nontrivial", "v6_pair_third_null", "v6_pair_all",
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_rows(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def write_rows(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def frozen_check():
    lock = load(EXPERIMENTS / "research_validation/V5_LOCK.json")
    for name, digest in lock["files"].items():
        if sha(WORKSPACE / name) != digest:
            raise ValueError("Frozen original changed: " + name)
    return len(lock["files"])


def implementation():
    names = ("run_v6.py", "postprocess_v6.py", "english_evaluation.py")
    values = {name: sha(HERE / name) for name in names}
    english = EXPERIMENTS / "sql_to_text_evaluation"
    values.update({"english_dependency/" + name: sha(english / name)
                   for name in ("english_metrics.py", "reference_renderer.py", "answer_from_sql.py", "common_io.py")})
    return values


def freeze(path, value):
    if Path(path).exists() and load(path) != value:
        raise ValueError("Immutable protocol changed; create a new run")
    if not Path(path).exists():
        dump(path, value)


def eligible(candidate):
    execution = candidate["execution"]
    return (candidate["sql"] != "null" and execution.get("valid") is True
            and execution.get("abstained") is False and execution.get("empty") is False
            and not candidate.get("static_issues")
            and not candidate.get("contract", {}).get("hard_issues")
            and candidate.get("result_fingerprint") is not None)


def choose(original, enhanced, policy):
    if policy not in POLICIES:
        raise ValueError("Unknown predeclared policy")
    if policy == "v5_reference":
        return select_v5(original, "strict3_canonical")
    selected = select_v5(enhanced, "strict3_canonical")
    selected["selection"]["v6_policy"] = policy
    if selected["selected_candidate_index"] is not None or policy == "v6_strict3":
        return selected
    groups = {}
    for index, candidate in enumerate(enhanced):
        if eligible(candidate):
            groups.setdefault(candidate["result_fingerprint"], []).append(index)
    for voters in sorted(groups.values(), key=lambda group: (-len(group), group)):
        hashes = {enhanced[i].get("call_hashes", [None])[-1] for i in voters if enhanced[i].get("call_hashes")}
        if len(voters) < 2 or len(hashes - {None}) < 2:
            continue
        if "plan" in policy and not any(enhanced[i].get("route") == "plan" for i in voters):
            continue
        if "nontrivial" in policy and any(enhanced[i].get("result_summary", {}).get("trivial_scalar") is not False for i in voters):
            continue
        if "ast" in policy:
            signatures = [structure_signature(enhanced[i]["sql"]) for i in voters]
            if not all(signatures) or len(set(signatures)) != 1:
                continue
        if policy == "v6_pair_third_null":
            other = [i for i in range(3) if i not in voters]
            if len(other) != 1 or enhanced[other[0]]["sql"] != "null":
                continue
            if enhanced[other[0]].get("guard_rejected"):
                continue  # genuine model-null only; failures are not votes
        index = min(voters)
        result = deepcopy(enhanced[index])
        result["selected_candidate_index"] = index
        result["selection"] = {"policy": policy, "v6_policy": policy,
                               "reason": "dev_selected_two_way_fallback", "supporting_candidate_indices": voters,
                               "selected_candidate_index": index,
                               "agreement_is_not_probability_or_semantic_proof": True}
        return result
    return selected


def score_mapping(predictions, gold, cache):
    if set(predictions) != set(gold):
        raise ValueError("All expected IDs required for scoring")
    answers = {}
    for key, sql in predictions.items():
        if sql == "null":
            answers[key] = "null"
            continue
        if not sql.strip():
            answers[key] = "error_pred"
            continue
        if sql not in cache:
            try:
                cache[sql] = execute_readonly(sql, DB, 120)
            except Exception:
                cache[sql] = "error_pred"
        answers[key] = cache[sql]
    metrics = score_answers(gold, answers, "official")
    answerable = {k for k in gold if gold[k] != "null"}
    answered = {k for k in predictions if predictions[k] != "null"}
    correct_sql = sum(metrics["per_question"][k] == "correct" for k in answerable)
    metrics.update(EX=100 * correct_sql / len(answerable),
                   VSR=100 * sum(isinstance(v, list) for v in answers.values()) / len(gold),
                   coverage=100 * len(answered) / len(gold),
                   answer_precision=100 * correct_sql / len(answered) if answered else None,
                   correct_answerable_sql=correct_sql,
                   correct_abstentions=metrics["correct"] - correct_sql,
                   execution_errors=sum(v == "error_pred" for v in answers.values()))
    return metrics


def transform(rows, metadata):
    from postprocess_v6 import enhance_v6
    return [{"id": row["id"], "question": row["question"], "partition": row["partition"],
             "original_candidates": row["candidates"],
             "candidates": enhance_v6(row["question"], row["candidates"], metadata)} for row in rows]


def sqls_for(rows, policy):
    return {row["id"]: choose(row["original_candidates"], row["candidates"], policy)["sql"] for row in rows}


def dev(run):
    frozen_count = frozen_check()
    protocol = {"date": "2026-11-01", "dataset": "paper_EHRSQL2024_MIMIC_IV_only",
                "model_generation": "unchanged_cached_DeepSeek_Flash_V3_candidates_used_by_V5",
                "new_model_API_calls": 0, "policies": list(POLICIES), "selection_metric": "RS10",
                "min_coverage_percent": 35, "selection_partition": "original_V5_tune300",
                "audit100": "previously exposed development diagnostics, not independent validation or policy selection",
                "original_test_status": "historically exposed through V5; exploratory benchmark comparison only",
                "test_rule": "Freeze selected policy/code before one full test; never retune from test outcomes",
                "tie_break": "RS10, precision, fewer wrong, coverage, earlier policy",
                "source_records_sha256": {phase: sha(V5_RUN / phase / "records.jsonl") for phase in ("tune", "audit", "test")},
                "implementation_sha256": implementation(), "frozen_original_files_verified": frozen_count}
    english_manifest = EXPERIMENTS / "sql_to_text_evaluation/data/MANIFEST.json"
    protocol["English_reference_manifest_sha256"] = sha(english_manifest)
    protocol["English_reference_sha256"] = {name: value["reference_sha256"]
                                           for name, value in load(english_manifest)["splits"].items()}
    freeze(run / "protocol.json", protocol)
    metadata = load_metadata()
    tune = transform(read_rows(V5_RUN / "tune/records.jsonl"), metadata)
    audit = transform(read_rows(V5_RUN / "audit/records.jsonl"), metadata)
    if len(tune) != 300 or len(audit) != 100 or {r["id"] for r in tune} & {r["id"] for r in audit}:
        raise ValueError("Wrong fixed development partitions")
    all_gold = load(BASELINE / "data/gold/dev/answer.json")
    gold = {r["id"]: all_gold[r["id"]] for r in tune}
    cache, grid = {}, []
    for name in POLICIES:
        metric = score_mapping(sqls_for(tune, name), gold, cache)
        metric.pop("per_question")
        grid.append({"policy": name, **metric})
    feasible = [r for r in grid if r["coverage"] >= 35]
    best = max(feasible, key=lambda r: (r["scores"]["RS10"], r["answer_precision"], -r["wrong"],
                                        r["coverage"], -POLICIES.index(r["policy"])))
    if protocol["implementation_sha256"] != implementation():
        raise ValueError("Code changed during dev; discard this diagnostic run and use a new run")
    # The decision is finalized before looking at audit100 scores or test labels.
    selection = {"selected_policy": best["policy"], "selected_on": "tune300_only", "selected_summary": best,
                 "tune_grid": grid, "protocol_sha256": sha(run / "protocol.json"),
                 "implementation_sha256": implementation()}
    freeze(run / "policy.json", selection)
    audit_gold = {r["id"]: all_gold[r["id"]] for r in audit}
    audits = {name: score_mapping(sqls_for(audit, name), audit_gold, cache) for name in ("v5_reference", best["policy"])}
    dump(run / "development_audit_diagnostics.json", audits)
    write_rows(run / "tune/records.jsonl", tune)
    write_rows(run / "audit/records.jsonl", audit)
    lock = {"policy_sha256": sha(run / "policy.json"), "protocol_sha256": sha(run / "protocol.json"),
            "implementation_sha256": implementation(), "selected_policy": best["policy"],
            "test_scores_consulted_for_this_selection": False}
    freeze(run / "TEST_LOCK.json", lock)
    frozen_check()
    print(json.dumps({"selected": best, "audit_diagnostic_RS10": {k: v["scores"]["RS10"] for k, v in audits.items()}}, ensure_ascii=False))


def test(run):
    frozen_check()
    lock = load(run / "TEST_LOCK.json")
    if lock["implementation_sha256"] != implementation() or lock["policy_sha256"] != sha(run / "policy.json") or lock["protocol_sha256"] != sha(run / "protocol.json"):
        raise ValueError("Test lock changed")
    if load(run / "protocol.json")["English_reference_manifest_sha256"] != sha(EXPERIMENTS / "sql_to_text_evaluation/data/MANIFEST.json"):
        raise ValueError("English reference manifest changed after locking")
    if (run / "TEST_COMPLETE.json").exists():
        raise ValueError("Full test already completed; do not rerun or retune to seek higher scores")
    original = read_rows(V5_RUN / "test/records.jsonl")
    questions = load(BASELINE / "data/inputs/test.json")["data"]
    if len(original) != 1167 or {r["id"] for r in original} != {r["id"] for r in questions}:
        raise ValueError("Full original paper test required")
    rows = transform(original, load_metadata())
    primary = lock["selected_policy"]
    outputs = {"V5_frozen": sqls_for(rows, "v5_reference"), "V6_dev_selected": sqls_for(rows, primary)}
    for name, mapping in outputs.items():
        dump(run / "test" / (name + ".prediction.json"), mapping)
    write_rows(run / "test/records.jsonl", rows)
    # Predictions are saved before evaluation labels are loaded.
    gold = load(BASELINE / "data/gold/test/answer.json")
    cache = {}
    metrics = {name: score_mapping(mapping, gold, cache) for name, mapping in outputs.items()}
    previous = load(V5_RUN / "test/evaluation.json")["variants"]["v5_selected"]
    if metrics["V5_frozen"]["per_question"] != previous["per_question"]:
        raise ValueError("Unchanged V5 no longer matches frozen outcomes")
    transitions = {}
    for key in gold:
        change = metrics["V5_frozen"]["per_question"][key] + " -> " + metrics["V6_dev_selected"]["per_question"][key]
        transitions[change] = transitions.get(change, 0) + 1
    report = {"status": "full_original_paper_test_complete", "n": 1167, "primary_policy": primary,
              "new_model_API_calls": 0, "generation_reused_not_regenerated": True,
              "inherited_generation_compute_not_zero": True,
              "test_selection_allowed": False, "systems": metrics, "transitions_vs_V5": transitions,
              "RS10_delta": metrics["V6_dev_selected"]["scores"]["RS10"] - metrics["V5_frozen"]["scores"]["RS10"],
              "original_frozen_files_verified": frozen_check()}
    dump(run / "test/evaluation.json", report)
    dump(run / "TEST_COMPLETE.json", {"evaluation_sha256": sha(run / "test/evaluation.json"),
                                      "policy_sha256": sha(run / "policy.json"), "n": 1167})
    print(json.dumps({"primary": primary, "RS10_delta": report["RS10_delta"], "transitions": transitions,
                      "scores": {k: {x: v[x] for x in ("scores", "EX", "VSR", "wrong", "answer_precision")} for k, v in metrics.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("dev", "test"), required=True)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    (dev if args.phase == "dev" else test)(args.run_dir)
