"""Ours v6: local fingerprint voting, gated verification and LLM selection on disagreement."""
import json

from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import ProposedFlags, build_pipeline

from test_proposed_readiness import CORRECT, QUESTION, RECORDS, TABLE, model_for, verification

OTHER = f'SELECT COUNT(*) AS n FROM {TABLE}'
THIRD = f'SELECT COUNT(DISTINCT hadm_id) AS n FROM {TABLE} WHERE admittime IS NOT NULL'
EMPTY = f'SELECT hadm_id FROM {TABLE} WHERE hadm_id < 0'
TWO = Execution(('n',), ((2,),), True)
NINE = Execution(('n',), ((9,),), True)
SEVEN = Execution(('n',), ((7,),), True)


def stages(model):
    return sorted(call['stage'] for call in model.calls)


def generated(model):
    """SQL order in the mock queue is consumption order, which is c1/c3 then c2."""
    return [c for c in model.calls if c['stage'] == 'generate']


def test_majority_by_result_fingerprint_needs_no_verifier_or_selector():
    # c1 and c3 (first two generations) agree; c2 differs.
    model = model_for([CORRECT, CORRECT, OTHER])
    db = MockBigQuery(RECORDS, results={CORRECT: TWO, OTHER: NINE})
    output = build_pipeline(db, model).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert 'fingerprint_majority_2_of_3' in output['reason']
    assert stages(model) == ['decompose', 'generate', 'generate', 'generate', 'link']
    assert output['fallbacks'] == []
    events = [e['stage'] for e in output['trace']]
    assert 'selection.fingerprints' in events and 'semantic.verification' not in events


def test_disagreement_calls_one_selector_without_requiring_supported():
    model = model_for([CORRECT, OTHER, THIRD])
    invalid = {'selected_id': 'c2', 'reason': 'Counts distinct admissions in scope', 'assessments': []}
    model.responses['select'].extend([invalid, invalid])
    db = MockBigQuery(RECORDS, results={CORRECT: TWO, OTHER: NINE, THIRD: SEVEN})
    output = build_pipeline(db, model).run(QUESTION)
    # An empty assessment list fails "assess every candidate" twice, so the
    # first executed candidate with values is kept and the fallback is flagged.
    assert output['status'] == 'answered'
    assert output['fallbacks'] == ['selection_fallback']
    assert stages(model).count('select') == 2 and 'verify' not in stages(model)


def test_selector_choice_is_used_when_valid():
    model = model_for([CORRECT, OTHER, THIRD])
    db = MockBigQuery(RECORDS, results={CORRECT: TWO, OTHER: NINE, THIRD: SEVEN})
    pipeline = build_pipeline(db, model)
    # Assess the three distinct representatives (c1, c2, c3) with unknown verdicts.
    assessments = [{**verification(cid, False), 'candidate_id': cid} for cid in ('c1', 'c2', 'c3')]
    for item in assessments:
        item['checks'][0]['status'] = 'unknown'
        item['verdict'] = 'unknown'
    model.responses['select'].append({'selected_id': 'c3', 'reason': 'Matches the window', 'assessments': assessments})
    output = pipeline.run(QUESTION)
    assert output['status'] == 'answered'
    assert output['reason'] == 'v6 selection: llm_selection'
    assert output['sql'] in {CORRECT, OTHER, THIRD}


def test_empty_result_triggers_one_gated_verification_and_repair():
    model = model_for([EMPTY, EMPTY, EMPTY], [verification('c1', False)], [CORRECT])
    db = MockBigQuery(RECORDS, results={EMPTY: Execution(('hadm_id',), (), True), CORRECT: TWO})
    output = build_pipeline(db, model).run(QUESTION)
    assert output['status'] == 'answered' and output['sql'] == CORRECT
    assert 'gated_verification' in output['reason'] and 'semantic_repair' in output['reason']
    assert stages(model).count('verify') == 1 and stages(model).count('repair') == 1


def test_static_context_leads_the_payload_for_prompt_caching():
    model = model_for([CORRECT, CORRECT, CORRECT])
    build_pipeline(MockBigQuery(RECORDS), model).run(QUESTION)
    payload = json.loads(generated(model)[0]['prompt'][-1]['content'])
    keys = list(payload)
    assert keys[0] == 'schema' and keys[-1] == 'original_question'


def test_v51_ablation_flags_restore_sequential_verify_all_flow():
    flags = ProposedFlags(fingerprint_selection=False, parallel_branches=False, self_correction=False)
    model = model_for([CORRECT, CORRECT, CORRECT],
                      [verification('c1'), verification('c2'), verification('c3')])
    output = build_pipeline(MockBigQuery(RECORDS, results={CORRECT: TWO}), model, flags=flags).run(QUESTION)
    assert output['status'] == 'answered'
    assert stages(model).count('verify') == 3
