from copy import deepcopy

import pytest

from ehrqa.agentic.schema import Schema
from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
from ehrqa.clinsql.evidence_router import RestrictedEvidenceEgress, guard_ours_payload
from ehrqa.clinsql.procedure_grounding import (
    REVIEW, CodeSetBlocked, adjudication_format, concept_type, procedure_candidates,
    procedure_evidence, validated_decisions, verify_procedure_cte,
)


@pytest.fixture
def catalog():
    codes = [
        ('d_icd_procedures', 9, '3761', 'Implant of pulsation balloon'),
        ('d_icd_procedures', 10, '5A02210', 'Continuous cardiac output assistance via balloon pump'),
        ('d_icd_procedures', 9, '3763', 'Repair of heart assist system'),
        ('d_icd_diagnoses', 10, 'R570', 'Cardiogenic shock with mechanical circulatory support'),
    ]
    return ClinicalCatalog([{'table': table, 'icd_version': version, 'icd_code': code, 'long_title': label}
                            for table, version, code, label in codes], source='test dictionary')


@pytest.mark.parametrize(('text', 'kind'), [
    ('mechanical circulatory support procedures', 'PROCEDURE'),
    ('heart failure diagnoses', 'DIAGNOSIS'),
    ('lab tests', 'LAB'),
    ('prescriptions', 'MEDICATION'),
    ('hospital length of stay', 'OTHER'),
])
def test_concept_routing(text, kind):
    assert concept_type(text) == kind


def test_procedure_candidates_exclude_diagnosis_rows_and_rank_sourced_aliases(catalog):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    assert [(item['icd_version'], item['icd_code']) for item in candidates] == [(9, '3761'), (10, '5A02210')]
    assert all(item['official_sources'] and item['dictionary_source'] == 'test dictionary' for item in candidates)
    assert procedure_candidates(catalog, 'IABP') == candidates
    format_ = adjudication_format(candidates)
    fields = format_['schema']['properties']['decisions']['items']['properties']
    assert fields['icd_code']['enum'] == ['3761', '5A02210']
    assert fields['decision']['enum'] == ['INCLUDE', 'EXCLUDE', 'AMBIGUOUS']


def decisions_for(candidates):
    return [{'icd_code': item['icd_code'], 'icd_version': item['icd_version'],
             'decision': 'INCLUDE', 'candidate_label': item['label'],
             'reason': 'Direct evidence of balloon pump support',
             'evidence_source_ids': item['official_sources']} for item in candidates]


def test_legacy_ecmo_is_not_silently_included(catalog):
    legacy = ClinicalCatalog([{'table': 'd_icd_procedures', 'icd_version': 9,
                               'icd_code': '3965', 'long_title': 'Extracorporeal membrane oxygenation'}],
                             source='test dictionary')
    with pytest.raises(CodeSetBlocked, match=REVIEW) as caught:
        procedure_evidence(legacy, {
            'requirements': [{'kind': 'entity', 'id': 'r1', 'span': 'mechanical circulatory support procedures'}],
            'links': [{'requirement_id': 'r1', 'table': 'procedures_icd'}],
        })
    assert caught.value.candidates[0]['status'] == 'AMBIGUOUS_LEGACY_CODE'
    supplied = caught.value.candidates
    with pytest.raises(CodeSetBlocked, match=REVIEW):
        validated_decisions(legacy, supplied, decisions_for(supplied))


@pytest.mark.parametrize('change', [
    {'icd_code': 'R570'}, {'icd_version': 10},
    {'evidence_source_ids': ['invented-source']}, {'decision': 'AMBIGUOUS'},
])
def test_model_decisions_cannot_substitute_or_claim_unsupported_evidence(catalog, change):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    decisions = decisions_for(candidates)
    decisions[0].update(change)
    with pytest.raises(CodeSetBlocked):
        validated_decisions(catalog, candidates, decisions)


def test_unrequested_code_cannot_expand_validated_set(catalog):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    decisions = decisions_for(candidates)
    decisions.append({**decisions[0], 'icd_code': '3763'})
    assert {r['icd_code'] for r in validated_decisions(catalog, candidates, decisions)} == {'3761', '5A02210'}


def candidate_sql(predicate, join_version=True):
    version = 'AND p.icd_version = c.icd_version' if join_version else ''
    return f"""WITH code_set AS (
        SELECT icd_code, icd_version FROM d_icd_procedures WHERE {predicate}
    ), cold_path AS (SELECT 1 WHERE FALSE)
    SELECT p.icd_code FROM procedures_icd p
    JOIN code_set c ON p.icd_code = c.icd_code {version}"""


def test_grounded_pairs_and_composite_join(catalog):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    includes = validated_decisions(catalog, candidates, decisions_for(candidates))
    predicate = "(icd_version = 9 AND icd_code IN ('3761')) OR (icd_version = 10 AND icd_code = '5A02210')"
    sql = candidate_sql(predicate)
    verify_procedure_cte(sql, 'code_set', includes)
    schema = Schema.from_records([{'table': name, 'ddl': f'CREATE TABLE {name} (icd_code STRING, icd_version INT64)'}
                                  for name in ('procedures_icd', 'd_icd_procedures')], dialect='bigquery')
    assert schema.inspect(sql)['valid']
    assert not schema.inspect(candidate_sql(predicate, join_version=False))['valid']


@pytest.mark.parametrize('predicate', [
    'FALSE',
    "icd_version = 10 AND icd_code IN ('R570', '5A02210')",
    "icd_version = 10 AND icd_code IN ('3761', '5A02210')",
    "(icd_version = 9 AND icd_code IN ('3761', '3763')) OR (icd_version = 10 AND icd_code = '5A02210')",
])
def test_required_procedure_cte_rejects_empty_diagnosis_wrong_version_or_overbreadth(catalog, predicate):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    includes = validated_decisions(catalog, candidates, decisions_for(candidates))
    with pytest.raises(ValueError):
        verify_procedure_cte(candidate_sql(predicate), 'code_set', includes)


def test_local_verified_sets_require_separate_egress_authorization():
    message = {'content': '{"verified_procedure_sets":{"code_set":[{"icd_code":"3761"}]}}'}
    with pytest.raises(RestrictedEvidenceEgress):
        guard_ours_payload('generate', [message])


def test_unused_selector_cannot_prove_grounding(catalog):
    candidates = procedure_candidates(catalog, 'MCS procedures')
    includes = validated_decisions(catalog, candidates, decisions_for(candidates))
    sql = """WITH code_set AS (
        SELECT icd_code, icd_version FROM d_icd_procedures
        WHERE (icd_version = 9 AND icd_code = '3761') OR
              (icd_version = 10 AND icd_code = '5A02210')
    ) SELECT icd_code FROM procedures_icd"""
    with pytest.raises(ValueError, match='not used by the final query'):
        verify_procedure_cte(sql, 'code_set', includes)
