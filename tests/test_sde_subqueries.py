"""SDE decomposition parity on synthetic SQL, with no database or LLM calls."""
import subprocess

import pytest
import sqlglot

from ehrqa.clinsql.baselines import sde_subqueries
from ehrqa.clinsql.baselines.sde_subqueries import (
    _native_generate_result, bigquery_get_subsqls, native_get_subsqls)
from ehrqa.clinsql.source_templates import isolated_function


def test_get_subsqls_matches_locked_native_function():
    sql = 'SELECT COUNT(subject_id) FROM admissions WHERE subject_id = 1'
    source_fn = isolated_function('sde_sql_official', 'src/refine_new.py', 'get_subsqls')
    source_fn.__globals__['generate_result'] = _native_generate_result()
    assert native_get_subsqls(sql) == source_fn(sql)
    assert native_get_subsqls(sql)


def test_bigquery_boundary_produces_single_select_probes():
    sql = 'SELECT COUNT(subject_id) FROM `admissions` WHERE subject_id = 1'
    pieces = bigquery_get_subsqls(sql)
    assert pieces
    assert all(isinstance(sqlglot.parse_one(piece, read='bigquery'), sqlglot.exp.Select)
               for piece in pieces)


def test_qualified_join_and_dates_survive_native_decomposition():
    sql = ('SELECT COUNT(a.subject_id) FROM `demo.hosp.admissions` a '
           'JOIN `demo.hosp.patients` p ON a.subject_id=p.subject_id '
           'WHERE EXTRACT(YEAR FROM a.admittime)=2150')
    probes = bigquery_get_subsqls(sql)
    assert any('EXTRACT(YEAR' in probe for probe in probes)
    assert any('JOIN' in probe for probe in probes)
    for probe in probes:
        assert all((table.catalog, table.db) == ('demo', 'hosp')
                   for table in sqlglot.parse_one(probe, read='bigquery').find_all(sqlglot.exp.Table))


def test_native_diagnosis_timeout_uses_source_deadline(monkeypatch):
    def timeout(command, **kwargs):
        assert kwargs['timeout'] == 60 and kwargs['input'] == 'SELECT 1'
        raise subprocess.TimeoutExpired(command, kwargs['timeout'])

    monkeypatch.setattr(sde_subqueries.subprocess, 'run', timeout)
    with pytest.raises(ValueError, match='timed out'):
        sde_subqueries.timed_bigquery_get_subsqls('SELECT 1')
