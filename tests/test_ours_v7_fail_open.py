"""Ours v7: decompose fail-open, tolerant selector audits, broader reference-patient coverage."""
from ehrqa.agentic import contracts
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import build_pipeline

from test_proposed_readiness import CORRECT, QUESTION, RECORDS, TABLE, model_for

OTHER = f'SELECT COUNT(*) AS n FROM {TABLE}'
THIRD = f'SELECT COUNT(DISTINCT hadm_id) AS n FROM {TABLE} WHERE admittime IS NOT NULL'


def test_invalid_decomposition_skips_only_the_decomposed_branch():
    model = model_for([CORRECT, CORRECT])
    bad_plan = {'steps': [{'id': 's1', 'operation': 'aggregate', 'depends_on': [],
                           'requirement_ids': ['r1'], 'tables': ['no_such_table'],
                           'description': 'x'}], 'output_step': 's1'}
    model.responses['decompose'].clear(); model.responses['decompose'].extend([bad_plan, bad_plan])
    db = MockBigQuery(RECORDS, results={CORRECT: Execution(('n',), ((2,),), True)})
    output = build_pipeline(db, model).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert output['fallbacks'] == ['decompose_fallback']
    stages = sorted(call['stage'] for call in model.calls)
    assert stages == ['decompose', 'decompose', 'generate', 'generate', 'link']
    assert any(e['stage'] == 'pipeline.fallback' and e.get('kind') == 'decompose_fallback'
               for e in output['trace'])


def test_selector_with_malformed_audit_still_resolves_disagreement():
    model = model_for([CORRECT, OTHER, THIRD])
    decision = {'selected_id': 'c1', 'reason': 'Applies the discharge window',
                'assessments': [{'candidate_id': c, 'checks': []} for c in ('c1', 'c2', 'c3')]}
    model.responses['select'].extend([decision])
    db = MockBigQuery(RECORDS, results={CORRECT: Execution(('n',), ((2,),), True),
                                        OTHER: Execution(('n',), ((9,),), True),
                                        THIRD: Execution(('n',), ((7,),), True)})
    output = build_pipeline(db, model).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert 'llm_selection' in output['reason'] and output['fallbacks'] == []


def test_reference_patient_openings_are_covered_verbatim():
    for question, number in [('I have an 89-year-old female inpatient. Among women aged 84-94, how many?', '89'),
                             ('Patient: female, 55. Among female inpatients aged 50-60, how many?', '55'),
                             ('My 56-year-old male inpatient: among men aged 51-61, how many?', '56')]:
        obj = {'requirements': [{'id': 'r1', 'kind': 'output', 'span': 'how many', 'description': 'count'}],
               'links': [], 'joins': []}
        obj, warnings = contracts.normalize_linking(question, obj, None, [])
        added = obj['requirements'][-1]
        assert added['kind'] == 'population' and number in added['span'] and added['span'] in question
        assert warnings
