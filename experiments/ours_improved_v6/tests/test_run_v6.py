from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import run_v6 as runner
from normalization import FINGERPRINT_METHOD


def candidate(index, value="same", sql="SELECT 3", *, trivial=False, genuine_null=False):
    row = {"sql": "null" if genuine_null else sql,
           "execution": {"valid": not genuine_null, "abstained": genuine_null,
                         "empty": None if genuine_null else False, "error": None},
           "static_issues": [], "contract": {"hard_issues": [], "soft_issues": []},
           "result_fingerprint": None if genuine_null else value,
           "result_summary": {"trivial_scalar": trivial},
           "call_hashes": [f"generation-{index}"], "route": ["direct", "structural", "plan"][index],
           "namespace_repair": {"changed": False}, "guard_rejected": False,
           "v4_normalization": {"method": FINGERPRINT_METHOD}}
    row["v5_original_record"] = deepcopy(row)
    return row


def pick(rows, policy):
    return runner.choose(deepcopy(rows), deepcopy(rows), policy)


def test_reference_strict3_rejects_two_of_three():
    rows = [candidate(0), candidate(1), candidate(2, "other", "SELECT 4")]
    assert pick(rows, "v5_reference")["sql"] == "null"
    assert pick(rows, "v6_strict3")["sql"] == "null"
    assert pick(rows, "v6_pair_ast")["sql"] == "SELECT 3"


def test_same_result_different_sql_not_ast_equivalent():
    rows = [candidate(0), candidate(1, sql="SELECT 4"), candidate(2, "other", "SELECT 5")]
    assert pick(rows, "v6_pair_ast")["sql"] == "null"
    assert pick(rows, "v6_pair_all")["sql"] == "SELECT 3"


def test_plan_vote_required_when_declared():
    rows = [candidate(0), candidate(1), candidate(2, "other", "SELECT 5")]
    assert pick(rows, "v6_pair_plan_ast")["sql"] == "null"
    rows[2] = candidate(2)
    rows[1] = candidate(1, "other", "SELECT 5")
    assert pick(rows, "v6_pair_plan_ast")["sql"] == "SELECT 3"


def test_trivial_zero_fallback_blocked():
    rows = [candidate(0, trivial=True), candidate(1, trivial=True), candidate(2, "other", "SELECT 5")]
    assert pick(rows, "v6_pair_nontrivial")["sql"] == "null"


def test_reused_request_never_counts_as_two_votes():
    rows = [candidate(0), candidate(1), candidate(2, "other", "SELECT 5")]
    rows[1]["call_hashes"] = rows[0]["call_hashes"]
    assert pick(rows, "v6_pair_all")["sql"] == "null"


def test_provider_error_stops_instead_of_becoming_abstention():
    rows = [candidate(0), candidate(1), candidate(2)]
    rows[0]["api_error"] = "failed"
    with pytest.raises(ValueError):
        pick(rows, "v6_strict3")


def test_third_genuine_null_is_distinct_from_guarded_failure():
    rows = [candidate(0), candidate(1), candidate(2, genuine_null=True)]
    assert pick(rows, "v6_pair_third_null")["sql"] == "SELECT 3"
    rows[2]["guard_rejected"] = True
    assert pick(rows, "v6_pair_third_null")["sql"] == "null"


def test_source_candidates_immutable():
    rows = [candidate(0), candidate(1), candidate(2)]
    before = deepcopy(rows)
    runner.choose(rows, rows, "v6_pair_all")
    assert rows == before


def test_unknown_policy_rejected():
    with pytest.raises(ValueError):
        pick([candidate(0), candidate(1), candidate(2)], "after_looking_at_test")
