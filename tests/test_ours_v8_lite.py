"""Ours v8 lite: pruned-schema linker, no decomposer, one candidate, adaptive escalation."""
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery
from ehrqa.clinsql.proposed import ProposedFlags, build_pipeline

from test_proposed_readiness import CORRECT, QUESTION, RECORDS, TABLE, model_for

LITE = ProposedFlags(adaptive_single=True)
EMPTY = f'SELECT hadm_id FROM {TABLE} WHERE hadm_id < 0'
TWO = Execution(('n',), ((2,),), True)


def stages(model):
    return sorted(call['stage'] for call in model.calls)


def test_single_pass_when_first_candidate_returns_values():
    model = model_for([CORRECT])
    db = MockBigQuery(RECORDS, results={CORRECT: TWO})
    output = build_pipeline(db, model, flags=LITE).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert output['reason'] == 'v8 selection: single_pass' and output['fallbacks'] == []
    assert stages(model) == ['generate', 'link']


def test_escalates_once_when_first_candidate_is_empty():
    model = model_for([EMPTY, CORRECT])
    db = MockBigQuery(RECORDS, results={CORRECT: TWO, EMPTY: Execution(('hadm_id',), (), True)})
    output = build_pipeline(db, model, flags=LITE).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert output['fallbacks'] == ['escalated_second_candidate']
    assert stages(model) == ['generate', 'generate', 'link']
    assert 'escalated_c3' in output['reason']


def test_keeps_empty_result_when_escalation_also_empty():
    model = model_for([EMPTY, EMPTY])
    db = MockBigQuery(RECORDS, results={EMPTY: Execution(('hadm_id',), (), True)})
    output = build_pipeline(db, model, flags=LITE).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == EMPTY
    assert 'without_values' in output['reason'] and 'select' not in stages(model)
