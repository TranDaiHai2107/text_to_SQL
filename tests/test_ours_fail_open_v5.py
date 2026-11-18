"""Ours v5: procedure evidence, constant-false filters and fail-open fallbacks."""
from pathlib import Path

import pytest

from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import ProposedFlags, build_pipeline, dictionary_search
from ehrqa.clinsql.public_terminology import PublicClinicalCatalog

from test_proposed_readiness import CORRECT, QUESTION, RECORDS, TABLE, V51, model_for, verification


def schema():
    return build_pipeline(MockBigQuery(RECORDS), MockLLM({})).db.schema


@pytest.mark.parametrize('sql', [
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE FALSE',
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE hadm_id > 0 AND 1 = 0',
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE (FALSE)',
    f"SELECT COUNT(*) AS n FROM {TABLE} WHERE 'a' = 'b'",
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE 1 <> 1',
    f'WITH x AS (SELECT hadm_id FROM {TABLE} WHERE FALSE) SELECT COUNT(*) AS n FROM x',
    f'WITH x AS (SELECT hadm_id FROM {TABLE} WHERE FALSE) SELECT COUNT(*) AS n FROM {TABLE} '
    'WHERE hadm_id IN (SELECT hadm_id FROM x)',
    f'SELECT COUNT(*) AS n FROM {TABLE} a JOIN {TABLE} b ON FALSE',
    f'SELECT hadm_id FROM {TABLE} GROUP BY hadm_id HAVING FALSE',
])
def test_constant_false_filters_are_invalid(sql):
    inspection = schema().inspect(sql)
    assert not inspection['valid']
    assert inspection['errors'][0].startswith('Constant-false filter')


@pytest.mark.parametrize('sql', [
    CORRECT,
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE TRUE',
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE 1 = 1',
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE FALSE OR hadm_id = 1',
    f'SELECT COUNT(*) AS n FROM {TABLE} WHERE hadm_id IS NOT NULL',
    f'WITH unused AS (SELECT 1 WHERE FALSE) SELECT COUNT(*) AS n FROM {TABLE}',
])
def test_satisfiable_filters_remain_valid(sql):
    assert schema().inspect(sql)['valid']


def test_constant_false_filter_is_sent_to_repair():
    placeholder = f'SELECT COUNT(*) AS n FROM {TABLE} WHERE FALSE'
    model = model_for([placeholder, CORRECT, CORRECT], repairs=[CORRECT])
    output = build_pipeline(MockBigQuery(RECORDS), model,
                            flags=ProposedFlags(requirement_verification=False)).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    first = output['selected']['history'][0]
    assert first['error_category'] == 'schema' and first['error'].startswith('Constant-false filter')


def test_no_supported_candidate_falls_back_to_executed_sql_with_flag():
    model = model_for([CORRECT, CORRECT, CORRECT],
                      [verification('c1', False), verification('c2', False), verification('c3', False)])
    flags = ProposedFlags(self_correction=False, **V51)
    output = build_pipeline(MockBigQuery(RECORDS), model, flags=flags).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert output['fallbacks'] == ['unverified_selection']
    assert output['selected']['id'] == 'c1'


def test_no_executable_candidate_returns_last_sql_unexecuted():
    bad = f'SELECT missing FROM {TABLE}'
    model = model_for([bad, bad, bad])
    flags = ProposedFlags(self_correction=False)
    db = MockBigQuery(RECORDS)
    output = build_pipeline(db, model, flags=flags).run(QUESTION)
    assert output['status'] == 'unresolved' and output['sql'] == bad
    assert output['fallbacks'] == ['unexecuted_sql'] and output['selected'] is None
    assert not db.calls


def test_dictionary_quota_keeps_procedure_evidence_next_to_diagnoses():
    catalog = PublicClinicalCatalog(Path(__file__).resolve().parents[1] / 'data/clinsql/public_terminology')
    question = ('How many heart failure patients had a procedure for assistance with cardiac output '
                'using a balloon pump?')
    context = {'tables': ['diagnoses_icd', 'procedures_icd', 'admissions']}
    rows = dictionary_search(catalog, question, context)
    assert 0 < len(rows) <= 24 and len({row['id'] for row in rows}) == len(rows)
    tables = {row['table'] for row in rows}
    assert tables == {'d_icd_diagnoses', 'd_icd_procedures'}
    assert any(row['icd_version'] == 10 and row['table'] == 'd_icd_procedures' for row in rows)
    # Without an implied dictionary the single global ranking is unchanged.
    assert dictionary_search(catalog, question, {'tables': ['admissions']}) == catalog.search(
        question, {'tables': ['admissions']})


# --- v5.1: verifier leniency, redacted error classes, catalog cache, early stop ---

from ehrqa.agentic import contracts
from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
from ehrqa.clinsql.execution_errors import redacted_sql_error_class


def test_error_class_whitelist_never_returns_raw_text():
    assert redacted_sql_error_class('Unrecognized name: foo_bar at [1:8]') == 'unrecognized name'
    assert redacted_sql_error_class('BigQuery SQL error; sql error class: syntax error; details withheld') == 'syntax error'
    assert redacted_sql_error_class('No matching signature for operator = for argument types') == 'no matching signature'
    assert redacted_sql_error_class('patient 12345 value 9.9 something odd') == 'details withheld'


def _executed(schema_, sql):
    from ehrqa.agentic.evidence import build_catalog
    inspection = schema_.inspect(sql)
    return inspection, build_catalog(sql, 'c1', schema_.dialect)


def test_lenient_verifier_downgrades_bad_evidence_instead_of_rejecting():
    s = schema()
    inspection, catalog = _executed(s, CORRECT)
    requirements = [{'id': 'r1'}, {'id': 'r2'}]
    audit = {'checks': [
        {'requirement_id': 'r1', 'status': 'satisfied', 'sql_evidence_ids': ['c1:query'],
         'schema_refs': ['admissions.hadm_id'], 'evidence': 'count'},
        {'requirement_id': 'r2', 'status': 'satisfied', 'sql_evidence_ids': ['c1:query'],
         'schema_refs': ['admissions.not_used'], 'evidence': 'cites an unused ref'}],
        'question_coverage': {'status': 'complete', 'uncovered_spans': [], 'extra_constraints': []},
        'verdict': 'supported'}
    with pytest.raises(contracts.StageError):
        contracts.verification(dict(audit, checks=[dict(c) for c in audit['checks']]), requirements,
                               CORRECT, inspection, QUESTION, s, catalog)
    out = contracts.verification(audit, requirements, CORRECT, inspection, QUESTION, s, catalog, lenient=True)
    assert [c['status'] for c in out['checks']] == ['satisfied', 'unknown']
    assert out['verdict'] == 'unknown' and out['evidence_warnings']
    # Structural defects still fail.
    with pytest.raises(contracts.StageError):
        contracts.verification({'checks': [], 'question_coverage': {}}, requirements, CORRECT,
                               inspection, QUESTION, s, catalog, lenient=True)


def test_verifier_gets_one_attempt_and_first_executable_is_kept():
    model = model_for([CORRECT, CORRECT, CORRECT], ['not json', 'not json'])
    output = build_pipeline(MockBigQuery(RECORDS), model, flags=ProposedFlags(**V51)).run(QUESTION)
    assert output['status'] == 'answered' and output['fallbacks'] == ['unverified_selection']
    stages = [c['stage'] for c in model.calls]
    assert stages == ['link', 'decompose', 'generate', 'verify']


def test_cached_catalog_search_matches_reference_ranking():
    rows = [{'table': 'd_icd_procedures', 'icd_version': 10, 'icd_code': f'X{i}', 'long_title': title}
            for i, title in enumerate(['Balloon pump assistance', 'Cardiac output assistance',
                                       'Unrelated thing', 'ECMO', 'balloon'])]
    catalog = ClinicalCatalog(rows, source='test')
    question = 'Count balloon pump procedures with ECMO'

    def reference():
        from ehrqa.agentic.retrieval import terms
        import re as _re
        words, text, ranked = terms(question), question.casefold(), []
        for r in catalog.records.values():
            names = (r['label'],)
            exact = any(_re.search(r'(?<!\w)' + _re.escape(n.casefold()) + r'(?!\w)', text) for n in names)
            overlap = max(len(words & terms(n)) for n in names)
            if exact or overlap:
                ranked.append((not exact, -overlap, True, r['id']))
        return [item[3] for item in sorted(ranked)]

    assert [r['id'] for r in catalog.search(question, {'tables': []})] == reference()
