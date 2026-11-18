import pytest

from ehrqa.agentic.schema import Schema


@pytest.fixture
def schema():
    return Schema.from_records([
        {'table': table, 'ddl': f'CREATE TABLE {table} (icd_code STRING, icd_version INT64)'}
        for table in ('procedures_icd', 'd_icd_procedures', 'unrelated')
    ], dialect='bigquery')


@pytest.mark.parametrize('sql', [
    """SELECT p.icd_code FROM procedures_icd p JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code AND d.icd_version = p.icd_version""",
    """WITH d AS (SELECT icd_code, icd_version FROM d_icd_procedures)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """WITH d AS (SELECT icd_code AS code, icd_version AS version FROM d_icd_procedures)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON (p.icd_code = d.code AND p.icd_version = d.version)""",
    """WITH d AS (SELECT icd_code, icd_version FROM d_icd_procedures),
       nested AS (WITH d AS (SELECT icd_code, icd_version FROM unrelated)
                  SELECT d.icd_code FROM d)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """WITH d AS (SELECT icd_code, icd_version FROM d_icd_procedures),
       nested AS (SELECT icd_code AS code, icd_version AS version FROM d)
       SELECT p.icd_code FROM procedures_icd p JOIN nested n
       ON p.icd_code = n.code AND p.icd_version = n.version""",
])
def test_accepts_same_join_with_both_grounded_keys(schema, sql):
    result = schema.inspect(sql)
    assert result['valid'], result['errors']


@pytest.mark.parametrize('sql', [
    """SELECT p.icd_code FROM procedures_icd p JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code""",
    """SELECT p.icd_code FROM procedures_icd p JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code WHERE p.icd_version = d.icd_version""",
    """SELECT p.icd_code FROM procedures_icd p JOIN unrelated u ON p.icd_version = u.icd_version
       JOIN d_icd_procedures d ON p.icd_code = d.icd_code AND u.icd_version = d.icd_version""",
    """WITH d AS (SELECT src.icd_code, u.icd_version
                  FROM d_icd_procedures src JOIN unrelated u ON src.icd_code = u.icd_code)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """WITH d AS (SELECT icd_code FROM d_icd_procedures)
       SELECT p.icd_code FROM procedures_icd p JOIN d ON p.icd_code = d.icd_code""",
    """WITH d AS (SELECT icd_code, icd_version + 1 AS icd_version FROM d_icd_procedures)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """WITH d AS (SELECT icd_code, icd_version FROM d_icd_procedures
                  UNION ALL SELECT icd_code, icd_version FROM unrelated)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """SELECT p.icd_code FROM procedures_icd p JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code AND EXISTS (
           SELECT 1 FROM unrelated p WHERE p.icd_version = d.icd_version
       )""",
    """SELECT p.icd_code FROM procedures_icd p JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code OR p.icd_version = d.icd_version""",
    """SELECT p.icd_code FROM procedures_icd p JOIN procedures_icd other
       ON p.icd_code = other.icd_code JOIN d_icd_procedures d
       ON p.icd_code = d.icd_code AND other.icd_version = d.icd_version""",
])
def test_rejects_missing_or_unproven_composite_key(schema, sql):
    result = schema.inspect(sql)
    assert not result['valid']
    assert result['errors'] == ['Missing composite icd_version JOIN']


@pytest.mark.parametrize('sql', [
    """WITH d AS (SELECT icd_code, icd_version FROM d_icd_procedures WHERE icd_version = 9
                  UNION DISTINCT SELECT icd_code, icd_version FROM d_icd_procedures WHERE icd_version = 10)
       SELECT p.icd_code FROM procedures_icd p JOIN d
       ON p.icd_code = d.icd_code AND p.icd_version = d.icd_version""",
    """SELECT p.icd_code FROM procedures_icd p WHERE EXISTS (
           SELECT 1 FROM d_icd_procedures d
           WHERE d.icd_code = p.icd_code AND d.icd_version = p.icd_version)""",
    """SELECT p.icd_code FROM procedures_icd p
       WHERE p.icd_code IN (SELECT icd_code FROM d_icd_procedures)""",
])
def test_v7_accepts_union_lineage_and_subquery_filters(schema, sql):
    result = schema.inspect(sql)
    assert result['valid'], result['errors']


def test_v7_rejects_correlated_exists_without_version(schema):
    result = schema.inspect("""SELECT p.icd_code FROM procedures_icd p WHERE EXISTS (
        SELECT 1 FROM d_icd_procedures d WHERE d.icd_code = p.icd_code)""")
    assert result['errors'] == ['Missing composite icd_version JOIN']


def test_v7_resolves_columns_through_star_projection():
    schema = Schema.from_records([
        {'table': 'patients', 'ddl': 'CREATE TABLE patients (subject_id INT64, gender STRING)'}],
        dialect='bigquery')
    result = schema.inspect("""WITH a AS (SELECT p.subject_id, p.gender FROM patients p),
        b AS (SELECT x.*, 1 AS risk FROM a AS x)
        SELECT COUNT(DISTINCT subject_id), AVG(risk) FROM b""")
    assert result['valid'], result['errors']
