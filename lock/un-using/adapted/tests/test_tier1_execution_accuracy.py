"""Tier 1 deterministic execution accuracy (supplementary, not the official CLINSQL score)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from score_execution_accuracy import ex_relaxed, ex_strict, mcnemar_exact  # noqa: E402


def test_strict_ignores_names_and_row_order_but_not_width():
    assert ex_strict(['a', 'b'], [[1, 'x'], [2, 'y']], ['n', 'label'], [['2', 'y'], ['1', 'x']])
    assert not ex_strict(['a'], [[1]], ['n', 'm'], [['1', '2']])
    assert ex_strict(['v'], [[0.3333333333]], ['v'], [['0.3333333333333']])
    assert not ex_strict(['v'], [[None]], ['v'], [['0']])


def test_relaxed_allows_extra_and_reordered_columns_only_by_value():
    rows = [[7, 'female', 0.5], [3, 'male', 0.25]]
    assert ex_relaxed(['n', 'sex', 'share'], rows, ['gender', 'cnt'], [['male', '3'], ['female', '7']])
    assert not ex_relaxed(['n', 'sex', 'share'], rows, ['gender', 'cnt'], [['male', '4'], ['female', '7']])
    assert not ex_relaxed(['n'], [[1], [2]], ['n'], [['1']])
    # The projection must keep rows aligned, not just column multisets.
    assert not ex_relaxed(['a', 'b'], [[1, 'x'], [2, 'y']], ['b', 'a'], [['y', '1'], ['x', '2']])


def test_mcnemar_counts_discordant_pairs():
    result = mcnemar_exact([True, True, False, True], [False, True, False, False])
    assert result['only_first'] == 2 and result['only_second'] == 0
    assert 0 < result['p_value'] <= 1
