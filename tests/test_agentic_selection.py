from itertools import combinations

import pytest

from ehrqa.agentic.selection import resolve
from ehrqa.agentic.contracts import sql_evidence


def pair(a,b,*,winner=None,equivalent=False):
    return {'left':a,'right':b,'winner':winner,'equivalent':equivalent}


def test_equivalent_candidates_have_a_canonical_representative():
    ids=['c3','c1','c2']
    decision=resolve(ids,[pair(a,b,equivalent=True) for a,b in combinations(ids,2)])
    assert decision['selected_id']=='c1' and decision['equivalent_ids']==['c1','c2','c3']


def test_equivalent_class_must_consistently_beat_other_candidates():
    r=[pair('a','b',equivalent=True),pair('a','c',winner='a'),pair('b','c',winner='b')]
    assert resolve(['a','b','c'],r)['selected_id']=='a'
    r[-1]=pair('b','c',winner='c')
    assert resolve(['a','b','c'],r)['selected_id'] is None


def test_unknown_is_not_equivalent_and_cycles_do_not_select():
    assert resolve(['a','b'],[pair('a','b')])['selected_id'] is None
    cycle=[pair('a','b',winner='a'),pair('b','c',winner='b'),pair('a','c',winner='c')]
    assert resolve(['a','b','c'],cycle)['selected_id'] is None


def test_nontransitive_equivalence_claims_are_rejected():
    r=[pair('a','b',equivalent=True),pair('b','c',equivalent=True),pair('a','c')]
    assert resolve(['a','b','c'],r)['selected_id'] is None
    with pytest.raises(ValueError):resolve(['a','b','c'],r[:1])


def test_evidence_alignment_preserves_literals_and_actual_source_spans():
    sql="SELECT p.drug FROM prescriptions AS p WHERE p.drug = 'CaseSensitive'"
    assert sql_evidence(sql,'select  P.drug')=='SELECT p.drug'
    assert sql_evidence(sql,"P.drug='CaseSensitive'")=="p.drug = 'CaseSensitive'"
    assert sql_evidence(sql,"p.drug = 'casesensitive'") is None
    assert sql_evidence(sql,'imaginary.drug') is None
