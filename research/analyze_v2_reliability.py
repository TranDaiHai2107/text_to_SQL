"""Read-only retrospective analysis of frozen v2 predictions; no model calls.

Derived variants below were NOT prespecified primary systems. No parameters,
thresholds, prompts, predictions or historical scores are changed by this file.
"""
from collections import Counter
import hashlib
import json
from pathlib import Path

WORKSPACE=Path(__file__).resolve().parents[1]
RUN=WORKSPACE/'experiments/ours_improved_v2/runs/deepseek_flash_v2b_20261028'
BASELINE=WORKSPACE/'baselines/probgate_ehrsql_2024'


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def metrics(outcomes,labels):
    counts=Counter(outcomes.values())
    return {'n':len(outcomes),'correct':counts['correct'],'wrong':counts['wrong'],
            'abstained_answerable':counts['abstained_answerable'],
            'RS10':100*(counts['correct']-10*counts['wrong'])/len(outcomes),
            'EX':100*sum(outcomes[key]=='correct' for key in outcomes if labels[key]!='null')/
                 sum(labels[key]!='null' for key in outcomes)}


def main():
    labels=load(BASELINE/'data/gold/test/label.json')
    final=load(RUN/'FINAL_RESULTS.json')
    rows=[json.loads(line) for line in (RUN/'test/records.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(rows)==1167 and {r['id'] for r in rows}==set(labels)
    original=load(final['rows']['v2_grounded']['source'])['per_question']
    reviewed=load(final['rows']['v2_verified']['source'])['per_question']
    guarded=dict(original)
    filtered=[]
    for row in rows:
        key=row['id']
        record=row['variants']['v2_grounded']
        check=record['execution']
        if record['sql']!='null' and (not check['valid'] or check['empty'] or record['static_issues']):
            guarded[key]='correct' if labels[key]=='null' else 'abstained_answerable'
            filtered.append({'id':key,'previous_outcome':original[key],
                             'new_outcome':guarded[key],'empty':check['empty'],
                             'static_issues':record['static_issues']})
    assert len(filtered)==29
    assert all(r['previous_outcome']=='wrong' and r['empty'] for r in filtered)
    transitions=Counter(original[key]+' -> '+reviewed[key] for key in labels)
    after_guard=Counter(guarded[key]+' -> '+reviewed[key] for key in labels)
    unanswerable_only=dict(original)
    for row in rows:
        if labels[row['id']]=='null':
            unanswerable_only[row['id']]='correct'
    sources=[RUN/'test/records.jsonl',RUN/'FINAL_RESULTS.json',BASELINE/'data/gold/test/label.json']
    result={'analysis_type':'retrospective_test_informed_diagnostics_only',
            'no_new_inference':True,'historical_primary_unchanged':'v2_calibrated',
            'original_generation':metrics(original,labels),
            'hypothetical_generation_plus_existing_guard':metrics(guarded,labels),
            'original_full_pipeline':metrics(reviewed,labels),
            'all_abstain_reference':100*sum(v=='null' for v in labels.values())/len(labels),
            'oracle_unanswerable_only_fix':metrics(unanswerable_only,labels),
            'oracle_note':'Upper-bound illustration using gold answerability, not an implementable detector or a measured improvement.',
            'generation_to_full_transitions':dict(sorted(transitions.items())),
            'guard_only_to_full_transitions':dict(sorted(after_guard.items())),
            'filtered_queries':filtered,
            'source_sha256':{str(p.relative_to(WORKSPACE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    output=Path(__file__).with_name('V2_RELIABILITY_DIAGNOSTIC_20261028.json')
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'filtered_queries','source_sha256'}},indent=2))


if __name__=='__main__':
    main()
