"""Diagnostic matching rules are independent of the official CLINSQL judge."""
from scripts.evaluate_pilot5_diagnostic import _same_cell, _unordered_multiset_equal


def test_float_tolerance_and_null_distinction():
    assert _same_cell(1.0000004, '1')
    assert not _same_cell(1.01, '1')
    assert _same_cell(None, '')
    assert not _same_cell(None, 'NaN')
    assert not _same_cell(float('nan'), '')
    assert not _same_cell('', '')


def test_unordered_multiset_keeps_duplicates():
    assert _unordered_multiset_equal(((1,), (2,), (1,)), [['2'], ['1'], ['1']])
    assert not _unordered_multiset_equal(((1,), (2,), (2,)), [['2'], ['1'], ['1']])
