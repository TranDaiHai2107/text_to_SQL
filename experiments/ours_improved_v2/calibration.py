"""Predeclared dev-only threshold selection; test never read here."""
import hashlib
from common import BASELINE,load,question_rows,score_answers
from grounded_pipeline import apply_threshold

THRESHOLDS=[None,-2.,-1.5,-1.,-.75,-.5,-.35,-.25,-.2,-.15,-.1,-.075,-.05,-.025,-.01,0.]


def calibration_plan():
    labels=load(BASELINE/'data/gold/dev/label.json')
    groups={kind:sorted([r for r in question_rows('dev') if (labels[r['id']]=='null')==kind],
            key=lambda r:hashlib.sha256(('ours_v2_calibration:'+r['id']).encode()).hexdigest()) for kind in [False,True]}
    return {'tune':[r['id'] for r in groups[False][:160]+groups[True][:40]],
            'audit':[r['id'] for r in groups[False][160:240]+groups[True][40:60]],
            'split':'dev','seed':'ours_v2_calibration','self_and_exact_question_duplicates_excluded':True,
            'threshold_grid':THRESHOLDS,'selection_metric':'RS10','audit_used_for_selection':False,
            'note':'Leave-one-question-out retrieval calibration; other train/dev knowledge remains. Test-informed exploratory method; not a fresh independent test.'}


def choose_threshold(rows,predicted_answers,gold,plan):
    by_id={r['id']:r for r in rows}
    required=set(plan['tune']+plan['audit'])
    if set(by_id)!=required or set(predicted_answers)!=required or set(gold)!=required:
        raise ValueError('All calibration predictions and only dev calibration IDs required')
    eligible=[r['variants']['v2_verified']['confidence']['score'] for r in rows if r['variants']['v2_verified']['sql']!='null']
    finite=[v for v in eligible if isinstance(v,(int,float)) and __import__('math').isfinite(v)]
    distinct=sorted(set(finite))
    usable=len(finite)==len(eligible) and len(distinct)>1
    quality={'eligible_questions':len(eligible),'finite_scores':len(finite),'distinct_scores':distinct,
             'usable':usable,'decision':'enable_calibrated_gate' if usable else 'disable_degenerate_or_missing_confidence_gate',
             'rule':'A constant or missing score cannot rank risk. Disable this gate independently of gold accuracy; retain semantic/execution guards.'}
    def at(ids,threshold):
        predicted={key:'null' if apply_threshold(by_id[key]['variants']['v2_verified'],threshold)['sql']=='null' else predicted_answers[key] for key in ids}
        return score_answers({key:gold[key] for key in ids},predicted,'official')
    candidates=[]
    for threshold in THRESHOLDS:
        metrics=at(plan['tune'],threshold)
        candidates.append({'threshold':threshold,**{k:metrics[k] for k in ['n','correct','wrong','abstained_answerable','scores']}})
    # Ties: fewer wrong answers, then first entry in fixed grid.
    best=max(candidates,key=lambda r:(r['scores']['RS10'],-r['wrong']))
    selected=best['threshold'] if usable else None
    return {'selected_threshold':selected,'confidence_quality':quality,'unconstrained_grid_optimum':best['threshold'],'tune_grid':candidates,
            'tune_selected':at(plan['tune'],selected),
            'audit_selected':at(plan['audit'],selected),
            'audit_ungated':at(plan['audit'],None),'plan':plan}
