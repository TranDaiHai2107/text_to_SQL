"""Pure, predeclared selective-prediction policies for two/three SQL candidates.

This module reads no files, executes no SQL, and makes no API calls. The caller
supplies typed full-result fingerprints during inference, and executed answers
plus the official scoring function during dev-only policy fitting. A matching
fingerprint is evidence of agreement on one database, not proof of correctness.
"""
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
import math

from sqlglot import parse_one


MIN_COVERAGE = 0.35
POLICIES = (
    "direct_guard",
    "strict_two_agree",
    "majority_two_of_three",
    "structural_consensus",
    "strict_three_agree",
    "agree_exclude_trivial",
    "consensus_no_soft_issues",
)


class NoFeasiblePolicyError(ValueError):
    """No policy satisfies the predeclared coverage constraint on tuning dev."""

    def __init__(self, grid, min_coverage):
        super().__init__(
            f"No fixed policy meets tuning coverage >= {min_coverage:.2f}; "
            "do not silently select all-abstain or relax the constraint."
        )
        self.grid = deepcopy(grid)
        self.min_coverage = min_coverage


def _string_list(value, name):
    if not isinstance(value, (list, tuple)) or any(not isinstance(v, str) for v in value):
        raise ValueError(f"{name} must be a list of strings")
    return list(value)


def _validate_candidates(candidates):
    if not isinstance(candidates, (list, tuple)) or len(candidates) not in (2, 3):
        raise ValueError("Exactly two or three completed candidate records are required")
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"Candidate {index} is not a record")
        # Provider failures must stop inference upstream, never masquerade as a
        # genuine model null and earn a correct unanswerable abstention.
        if any(candidate.get(k) for k in ("api_error", "provider_error", "network_error", "quota_error")):
            raise ValueError(f"Candidate {index} contains an API/provider failure")
        if candidate.get("error_kind") in {"api", "provider", "network", "quota"}:
            raise ValueError(f"Candidate {index} contains an API/provider failure")
        sql = candidate.get("sql")
        execution = candidate.get("execution")
        if not isinstance(sql, str) or not isinstance(execution, Mapping):
            raise ValueError(f"Candidate {index} needs SQL and a completed execution record")
        if type(execution.get("valid")) is not bool or type(execution.get("abstained")) is not bool:
            raise ValueError(f"Candidate {index} has malformed execution booleans")
        if execution.get("empty") is not None and type(execution["empty"]) is not bool:
            raise ValueError(f"Candidate {index} has a malformed empty-result flag")
        error = execution.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError(f"Candidate {index} has a malformed execution error")
        if execution["abstained"] != (sql == "null"):
            raise ValueError(f"Candidate {index} has an inconsistent model-null record")
        if execution["abstained"] and (error is not None or execution.get("empty") is not None):
            raise ValueError(f"Candidate {index} cannot convert an error/result into a model null")
        if execution["valid"] and (execution["abstained"] or not sql.strip() or error is not None):
            raise ValueError(f"Candidate {index} has an inconsistent successful execution")
        if execution["valid"] and type(execution.get("empty")) is not bool:
            raise ValueError(f"Candidate {index} needs a completed empty/nonempty check")
        if not execution["valid"] and not execution["abstained"] and not error:
            raise ValueError(f"Candidate {index} has not completed SQL validation/execution")
        _string_list(candidate.get("static_issues", []), "static_issues")
        _string_list(candidate.get("call_hashes", []), "call_hashes")
        contract = candidate.get("contract", {})
        if not isinstance(contract, Mapping):
            raise ValueError(f"Candidate {index} has a malformed contract")
        for field in ("hard_issues", "soft_issues"):
            _string_list(contract.get(field, []), "contract." + field)
        fingerprint = candidate.get("result_fingerprint")
        if fingerprint is not None and (not isinstance(fingerprint, str) or not fingerprint):
            raise ValueError(f"Candidate {index} has a malformed result fingerprint")


def _hard_issues(candidate):
    return list(candidate.get("static_issues", [])) + list(candidate.get("contract", {}).get("hard_issues", []))


def _eligible(candidate):
    check = candidate["execution"]
    return (
        candidate["sql"] != "null" and check["valid"] and not check["abstained"]
        and check["empty"] is False and not _hard_issues(candidate)
    )


def structure_signature(sql):
    """Conservative canonical AST rendering, not semantic equivalence testing.

    Literal values, aliases, output columns, filters and ordering are retained.
    Only parser-supported syntactic presentation differences are normalized.
    """
    if sql == "null" or not sql.strip():
        return None
    try:
        tree = parse_one(sql, read="sqlite")
        return tree.sql(dialect="sqlite", normalize=True, comments=False) if tree else None
    except Exception:
        return None


def _generation_identity(candidate):
    identity = candidate.get("generation_call_hash")
    if isinstance(identity, str) and identity:
        return identity
    hashes = candidate.get("call_hashes", [])
    return hashes[-1] if hashes else None


def _independent_indices(indices, candidates):
    # Different request hashes do not prove statistical independence, but known
    # identical cached requests must not count as multiple pieces of evidence.
    identities = set()
    distinct = []
    for index in indices:
        identity = _generation_identity(candidates[index])
        if identity is not None and identity not in identities:
            identities.add(identity)
            distinct.append(index)
    return distinct


def agreement_features(candidates):
    """Expose observable agreement features without inventing a probability."""
    _validate_candidates(candidates)
    eligible = [i for i, row in enumerate(candidates) if _eligible(row)]
    groups = defaultdict(list)
    for index in eligible:
        fingerprint = candidates[index].get("result_fingerprint")
        if fingerprint is not None:
            groups[fingerprint].append(index)
    result_groups = [
        {"fingerprint": key, "candidate_indices": value,
         "distinct_request_indices": _independent_indices(value, candidates)}
        for key, value in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[1]))
    ]
    signatures = {i: structure_signature(candidates[i]["sql"]) for i in eligible}
    nonnull = [i for i, row in enumerate(candidates) if row["sql"] != "null"]
    return {
        "candidate_count": len(candidates),
        "eligible_candidate_indices": eligible,
        "genuine_model_null_indices": [i for i, row in enumerate(candidates)
                                       if row["execution"]["abstained"] and not row.get("guard_rejected")],
        "guard_rejected_indices": [i for i, row in enumerate(candidates) if row.get("guard_rejected")],
        "invalid_execution_indices": [i for i, row in enumerate(candidates)
                                      if not row["execution"]["valid"] and not row["execution"]["abstained"]],
        "empty_execution_indices": [i for i, row in enumerate(candidates)
                                    if row["execution"]["valid"] and row["execution"]["empty"]],
        "guard_failed_indices": [i for i, row in enumerate(candidates) if _hard_issues(row)],
        "missing_fingerprint_indices": [i for i in eligible if candidates[i].get("result_fingerprint") is None],
        "execution_groups": result_groups,
        "all_nonnull_agree": (len(eligible) >= 2 and len(eligible) == len(nonnull)
                              and len(groups) == 1 and sum(map(len, groups.values())) == len(eligible)),
        "structure_disagreement": len({v for v in signatures.values() if v is not None}) > 1,
        "missing_structure_indices": [i for i, signature in signatures.items() if signature is None],
        "confidence_probability": None,
        "note": "Agreement is an observed feature, not a calibrated probability or correctness proof.",
    }


def _policy_name(policy):
    if isinstance(policy, Mapping):
        policy = policy.get("name", policy.get("policy"))
    if policy not in POLICIES:
        raise ValueError(f"Unknown fixed policy: {policy!r}")
    return policy


def _all_hashes(candidates):
    return list(dict.fromkeys(value for row in candidates for value in row.get("call_hashes", [])))


def _selection(candidates, policy, selected_index, reason, voters, features):
    if selected_index is None:
        record = {
            "sql": "null", "execution": {"valid": False, "abstained": True, "empty": None, "error": None},
            "static_issues": [], "result_fingerprint": None,
            "route": "risk_selection_abstention",
        }
    else:
        record = deepcopy(candidates[selected_index])
    record["call_hashes"] = _all_hashes(candidates)
    record["selected_candidate_index"] = selected_index
    record["selection"] = {
        "policy": policy, "reason": reason, "selected_candidate_index": selected_index,
        "supporting_candidate_indices": list(voters), "candidate_a_preserved": True,
        "candidate_routes": [row.get("route") for row in candidates],
        "baseline_candidate_index": 0, "features": deepcopy(features),
    }
    return record


def select_record(candidates, policy):
    """Return a new selected SQL/null record without mutating candidates.

    A is index 0. Strict-two uses A+B only; majority policies can select B when
    B+C agree against A. Missing/failed/empty results never cast agreement votes.
    Null is a deliberate policy abstention, not a replacement for provider errors.
    """
    policy = _policy_name(policy)
    features = agreement_features(candidates)
    eligible = set(features["eligible_candidate_indices"])
    if policy == "direct_guard":
        index = 0 if 0 in eligible else None
        return _selection(candidates, policy, index, "candidate_a_passes_guards" if index is not None else "candidate_a_rejected", [0] if index is not None else [], features)

    voters = [i for i in range(len(candidates)) if i in eligible]
    if policy == "strict_two_agree":
        voters = [i for i in (0, 1) if i in eligible]
    elif policy == "strict_three_agree" and len(candidates) != 3:
        return _selection(candidates, policy, None, "three_candidates_required", [], features)
    elif policy == "agree_exclude_trivial":
        voters = [i for i in voters if candidates[i].get("result_summary", {}).get("trivial_scalar") is False]
    elif policy == "consensus_no_soft_issues":
        voters = [i for i in voters if not candidates[i].get("contract", {}).get("soft_issues", [])]

    groups = defaultdict(list)
    for index in voters:
        candidate = candidates[index]
        fingerprint = candidate.get("result_fingerprint")
        if fingerprint is None:
            continue
        if policy == "structural_consensus":
            signature = structure_signature(candidate["sql"])
            if signature is None:
                continue
            key = (fingerprint, signature)
        else:
            key = fingerprint
        groups[key].append(index)
    required = 3 if policy == "strict_three_agree" else 2
    ordered = sorted(groups.values(), key=lambda group: (-len(group), group))
    for group in ordered:
        distinct = _independent_indices(group, candidates)
        if len(distinct) >= required:
            # Preserve A whenever it belongs to the accepted consensus.
            return _selection(candidates, policy, min(group), "nonempty_execution_consensus", distinct, features)
    null_indices = features["genuine_model_null_indices"]
    null_voters = [i for i in null_indices if i < 2] if policy == "strict_two_agree" else null_indices
    reason = "genuine_model_null_consensus" if len(_independent_indices(null_voters, candidates)) >= required else "insufficient_nonempty_execution_consensus"
    return _selection(candidates, policy, None, reason, [], features)


def _tune_rows(tune_records):
    if isinstance(tune_records, Mapping):
        result = []
        for key, value in tune_records.items():
            candidates = value.get("candidates") if isinstance(value, Mapping) else value
            result.append({"id": key, "candidates": candidates})
    elif isinstance(tune_records, Sequence) and not isinstance(tune_records, (str, bytes)):
        result = list(tune_records)
    else:
        raise ValueError("tune_records must be records or an ID-to-candidates mapping")
    if not result or any(not isinstance(row, Mapping) or not isinstance(row.get("id"), str) or not row["id"] for row in result):
        raise ValueError("Nonempty tuning records with question IDs are required")
    if len({row["id"] for row in result}) != len(result):
        raise ValueError("Duplicate tuning question IDs")
    for row in result:
        if row.get("partition") not in (None, "tune"):
            raise ValueError("Only the tune partition may be passed to policy selection")
        _validate_candidates(row.get("candidates"))
    return result


def fit_policy(tune_records, gold_answers, candidate_answers, *, score_fn,
               min_coverage=MIN_COVERAGE, policies=POLICIES, allowed_tune_ids=None):
    """Fit a fixed policy using tuning-dev answers only, with coverage >= .35.

    candidate_answers is {id: [executed rows, 'null', or 'error_pred', ...]} in
    the same order as each row's candidates. score_fn(gold, predicted) must
    return the official {n,correct,wrong,abstained_answerable,scores,per_question}
    result; the caller can pass its existing official normalizer/scorer directly.
    Audit/test data is not an input. All tuning IDs must be present in all maps.
    """
    if not callable(score_fn):
        raise ValueError("The caller must supply the official scoring function")
    if not isinstance(min_coverage, (int, float)) or not math.isfinite(min_coverage) or not MIN_COVERAGE <= min_coverage <= 1:
        raise ValueError(f"min_coverage must be between the fixed floor {MIN_COVERAGE} and 1")
    rows = _tune_rows(tune_records)
    ids = [row["id"] for row in rows]
    expected = set(ids)
    if set(gold_answers) != expected or set(candidate_answers) != expected:
        raise ValueError("Every tuning ID, and only tuning IDs, must be supplied; no dropped questions")
    if allowed_tune_ids is not None and set(allowed_tune_ids) != expected:
        raise ValueError("Records do not match the predeclared tuning partition")
    names = [_policy_name(policy) for policy in policies]
    if not names or len(set(names)) != len(names):
        raise ValueError("A nonempty unique fixed policy grid is required")
    for row in rows:
        answers = candidate_answers[row["id"]]
        if not isinstance(answers, (list, tuple)) or len(answers) != len(row["candidates"]):
            raise ValueError("Executed answers must cover each candidate in its original order")

    grid = []
    detailed = {}
    for name in names:
        predictions = {}
        answered = []
        for row in rows:
            selected = select_record(row["candidates"], name)
            index = selected["selected_candidate_index"]
            predictions[row["id"]] = "null" if index is None else candidate_answers[row["id"]][index]
            if index is not None:
                if predictions[row["id"]] in ("null", "error_pred"):
                    raise ValueError("An eligible successful SQL candidate has no executed answer")
                answered.append(row["id"])
        metrics = score_fn(gold_answers, predictions)
        if metrics.get("n") != len(ids) or set(metrics.get("per_question", {})) != expected:
            raise ValueError("Scorer must evaluate every tuning question exactly once")
        scores = metrics.get("scores", {})
        if not isinstance(scores.get("RS10"), (int, float)) or not math.isfinite(scores["RS10"]):
            raise ValueError("Official RS10 is required for policy selection")
        coverage = len(answered) / len(ids)
        correct_answered = sum(metrics["per_question"][key] == "correct" for key in answered)
        precision = correct_answered / len(answered) if answered else 0.0
        summary = {
            "policy": name, "n": len(ids), "answered_questions": len(answered),
            "coverage": coverage, "coverage_percent": 100 * coverage,
            "answer_precision": precision, "correct_answered": correct_answered,
            "correct": metrics["correct"], "wrong": metrics["wrong"],
            "abstained_answerable": metrics["abstained_answerable"], "scores": deepcopy(scores),
            "feasible": coverage >= min_coverage,
        }
        grid.append(summary)
        detailed[name] = metrics
    feasible = [row for row in grid if row["feasible"]]
    if not feasible:
        raise NoFeasiblePolicyError(grid, min_coverage)
    # Predeclared tie order: RS10, precision, fewer mistakes, coverage, grid order.
    best = max(feasible, key=lambda row: (row["scores"]["RS10"], row["answer_precision"],
                                        -row["wrong"], row["coverage"], -names.index(row["policy"])))
    return {
        "selected_policy": best["policy"], "min_coverage": min_coverage,
        "selection_metric": "RS10", "tune_ids": ids, "tune_questions": len(ids),
        "tune_grid": grid, "tune_selected": deepcopy(detailed[best["policy"]]),
        "selected_summary": deepcopy(best), "audit_used_for_selection": False,
        "tie_break": ["RS10", "answer_precision", "fewer_wrong", "higher_coverage", "fixed_grid_order"],
        "confidence_probability_invented": False,
    }
