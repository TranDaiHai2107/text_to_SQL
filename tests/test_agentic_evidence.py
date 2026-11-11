import pytest
from ehrqa.agentic.evidence import build_catalog,resolve_ids,public_catalog


def test_noncontiguous_sql_evidence_is_resolved_from_separate_real_handles():
    sql="SELECT COUNT(*) FROM admissions AS a WHERE a.subject_id = 1 GROUP BY a.subject_id"
    catalog=build_catalog(sql,'c1')
    count=next(e for e in catalog if e['sql']=='COUNT(*)')
    predicate=next(e for e in catalog if e['sql']=='a.subject_id = 1')
    assert resolve_ids(catalog,[count['id'],predicate['id']])==['COUNT(*)','a.subject_id = 1']
    assert all(e['sql'] in sql for e in catalog)
    assert 'sql' not in public_catalog(catalog)[-1]
    assert resolve_ids(catalog,['c1:query'])==[sql]


@pytest.mark.parametrize('ids',[[],['c2:e1'],['invented'],None,[1]])
def test_evidence_cannot_be_fabricated_or_borrowed_from_other_candidate(ids):
    with pytest.raises(ValueError):resolve_ids(build_catalog('SELECT 1','c1'),ids)


def test_complex_and_quoted_sql_keeps_original_literals():
    sql="WITH t AS (SELECT p.drug, COUNT(*) AS n FROM prescriptions AS p WHERE p.drug = 'CaseSensitive' GROUP BY p.drug) SELECT drug FROM t ORDER BY n DESC"
    catalog=build_catalog(sql,'c3')
    assert any(e['sql']=="p.drug = 'CaseSensitive'" for e in catalog)
    assert all(e['sql'] in sql for e in catalog)
