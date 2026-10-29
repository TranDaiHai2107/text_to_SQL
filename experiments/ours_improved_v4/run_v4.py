"""Develop v4 only on dev; reuse unchanged frozen v3 SQL candidates on test."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed,CancelledError
import hashlib
import json
import os
import sqlite3
import time
from infrastructure_v4 import ROOT,V3,BASELINE,DB,load,dump,sha,freeze,question_rows,api_balance,RunBlocked,score_answers,run_directory,V3Client,StructuredRAG,generate_question,RULE_EVIDENCE
from scoring_v3 import sql_answer
from postprocess_v4 import load_metadata,normalize_candidate,select_v4,POLICIES

SOURCE_RUN=V3/'runs/deepseek_flash_v3_20261029_r2'
MODES=['v4_direct','v4_structural','v4_plan','v4_selected']


def plan_v4():
    previous=load(SOURCE_RUN/'protocol.json')['calibration_plan']
    v2=load(ROOT.parent/'ours_improved_v2/runs/deepseek_flash_v2b_20261028/threshold.json')['plan']
    used=set(previous['tune']+previous['audit']+v2['tune']+v2['audit'])
    used|={r['id'] for refs in RULE_EVIDENCE.values() for r in refs if r['split']=='dev'}
    labels=load(BASELINE/'data/gold/dev/label.json')
    groups={kind:sorted([r for r in question_rows('dev') if r['id'] not in used and (labels[r['id']]=='null')==kind],
        key=lambda r:hashlib.sha256(('v4_new_audit_20261029:'+r['id']).encode()).hexdigest()) for kind in [False,True]}
    if len(groups[False])<80 or len(groups[True])<20:
        raise ValueError('Not enough untouched dev questions for a new audit')
    return {'tune':previous['tune'],'audit':[r['id'] for r in groups[False][:80]+groups[True][:20]],
            'audit_used_for_selection':False,'audit_previously_scored':False,
            'new_audit_disjoint_from_v2_v3_and_rule_evidence':True,
            'all400_calibration_questions_and_exact_duplicates_excluded_from_RAG':True,
            'min_coverage':.35,'policies':list(POLICIES),'selection_metric':'RS10',
            'research_status':'Exploratory iteration. Changes motivated by v3 tuning errors, not per-question v3 test failures; v3 aggregate test score was observed.'}


def save_rows(directory,rows):
    target=directory/'records.jsonl'
    temporary=directory/'records.jsonl.tmp'
    temporary.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    temporary.replace(target)


def status(directory,phase,done,total,state,reason=None):
    value={'state':state,'phase':phase,'completed_questions':done,'expected_questions':total,
           'run':directory.parent.name,'reason':reason,'updated_at_unix':time.time()}
    try:
        dump(directory/'status.json',value)
        dump(ROOT/'STATUS.json',value)
    except PermissionError:
        pass  # Non-authoritative app metadata; checkpoint/cache writes remain strict.


def initialize_tune_cache(directory):
    target=directory/'model_calls.sqlite'
    if not target.exists():
        directory.mkdir(parents=True,exist_ok=True)
        source=SOURCE_RUN/'tune/model_calls.sqlite'
        with sqlite3.connect(source) as src,sqlite3.connect(target) as dst:
            src.backup(dst)
        dump(directory/'cache_source.json',{'source':str(source),'source_sha256':sha(source),
            'source_events':str(SOURCE_RUN/'tune/api_events.jsonl'),
            'source_events_sha256':sha(SOURCE_RUN/'tune/api_events.jsonl'),
            'note':'Cache reused only by full request hash; changed RAG context generates a new request. New events log contains incremental calls only.'})


def infer_dev(directory,selected,rag,metadata,workers,phase):
    directory.mkdir(parents=True,exist_ok=True)
    expected={r['id']:r['question'] for r in selected}
    completed={p.stem:load(p) for p in (directory/'checkpoints').glob('*.json')}
    if any(k not in expected or r['question']!=expected[k] or len(r['candidates'])!=3 for k,r in completed.items()):
        raise ValueError('Bad dev checkpoint')
    normal=V3Client(directory,thinking=False)
    reasoning=V3Client(directory,thinking=True)
    reasoning._event_lock=normal._event_lock
    reasoning._keys_lock=normal._keys_lock
    reasoning._key_locks=normal._key_locks
    clients={'normal':normal,'reasoning':reasoning}
    def work(item):
        raw=generate_question(item,rag,clients)
        dump(directory/'raw_checkpoints'/(item['id']+'.json'),raw)
        result={'id':raw['id'],'question':raw['question'],'partition':phase,
                'candidates':[normalize_candidate(raw['question'],c,metadata) for c in raw['candidates']]}
        return result
    reason=None
    status(directory,phase,len(completed),len(selected),'running')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(work,item) for item in selected if item['id'] not in completed]
        for future in as_completed(pending):
            try:
                row=future.result()
            except CancelledError:
                continue
            except Exception as error:
                if reason is None:
                    reason=str(error)
                    for client in clients.values():
                        client.blocked_reason=reason
                        client.blocked.set()
                    for job in pending:
                        job.cancel()
                continue
            dump(directory/'checkpoints'/(row['id']+'.json'),row)
            completed[row['id']]=row
            status(directory,phase,len(completed),len(selected),'running',reason)
            if len(completed)%20==0:
                print(f'{phase}: {len(completed)}/{len(selected)}',flush=True)
    rows=[completed[r['id']] for r in selected if r['id'] in completed]
    save_rows(directory,rows)
    status(directory,phase,len(rows),len(selected),'complete' if len(rows)==len(selected) else 'blocked',reason)
    if reason or len(rows)!=len(selected):
        raise RunBlocked(reason or 'Incomplete partition; no padding')
    return rows


def answer_matrix(rows):
    return {r['id']:[sql_answer(c) for c in r['candidates']] for r in rows}


def selected_answer(row,selected,matrix):
    index=selected['selected_candidate_index']
    if index is None:
        return 'null'
    if selected['sql']==row['candidates'][index]['sql']:
        return matrix[row['id']][index]
    # The raw3-way reference deliberately uses the pre-v4 original candidate;
    # it must not accidentally inherit a new metadata guard's null answer.
    return sql_answer(selected)


def fit_v4(rows,plan):
    if {r['id'] for r in rows}!=set(plan['tune']) or any(r['partition']!='tune' for r in rows):
        raise ValueError('Only exact tuning partition may select a policy')
    all_gold=load(BASELINE/'data/gold/dev/answer.json')
    gold={r['id']:all_gold[r['id']] for r in rows}
    matrix=answer_matrix(rows)
    grid=[]
    for name in POLICIES:
        pred={}
        answered=[]
        for row in rows:
            selected=select_v4(row['candidates'],name)
            index=selected['selected_candidate_index']
            pred[row['id']]=selected_answer(row,selected,matrix)
            if index is not None:
                answered.append(row['id'])
        metric=score_answers(gold,pred,'official')
        coverage=len(answered)/len(rows)
        precision=sum(metric['per_question'][key]=='correct' for key in answered)/len(answered) if answered else 0.
        grid.append({'policy':name,'scores':metric['scores'],'correct':metric['correct'],'wrong':metric['wrong'],
                     'false_abstentions':metric['abstained_answerable'],'coverage':coverage,'precision':precision,
                     'feasible':coverage>=plan['min_coverage']})
    feasible=[r for r in grid if r['feasible']]
    if not feasible:
        raise ValueError('No policy meets frozen minimum coverage; do not pick all-null')
    best=max(feasible,key=lambda r:(r['scores']['RS10'],r['precision'],-r['wrong'],r['coverage'],-list(POLICIES).index(r['policy'])))
    return {'selected_policy':best['policy'],'selected_summary':best,'tune_grid':grid,
            'audit_used_for_selection':False,'min_coverage':plan['min_coverage'],'selection_metric':'RS10'}


def evaluate(directory,rows,split,policy,expected_ids):
    if len(rows)!=len(expected_ids) or {r['id'] for r in rows}!=set(expected_ids):
        raise ValueError('A complete partition is required')
    gold_all=load(BASELINE/'data/gold'/split/'answer.json')
    gold={r['id']:gold_all[r['id']] for r in rows}
    matrix=answer_matrix(rows)
    variants={}
    for index,mode in enumerate(MODES):
        pred={}
        sqls={}
        for row in rows:
            key=row['id']
            selected=select_v4(row['candidates'],policy) if mode=='v4_selected' else row['candidates'][index]
            ci=selected['selected_candidate_index'] if mode=='v4_selected' else index
            pred[key]=selected_answer(row,selected,matrix) if mode=='v4_selected' else matrix[key][ci]
            sqls[key]=selected['sql']
        metric=score_answers(gold,pred,'official')
        answerable={key for key in gold if gold[key]!='null'}
        nonnull={key for key in sqls if sqls[key]!='null'}
        correct_sql=sum(metric['per_question'][key]=='correct' for key in answerable)
        metric.update(EX=100*correct_sql/len(answerable),VSR=100*sum(isinstance(v,list) for v in pred.values())/len(rows),
            correct_answerable_sql=correct_sql,false_abstentions=sum(sqls[k]=='null' for k in answerable),
            false_answers_on_unanswerable=sum(sqls[k]!='null' for k in set(gold)-answerable),
            coverage=100*len(nonnull)/len(rows),answer_precision=100*correct_sql/len(nonnull) if nonnull else None)
        variants[mode]=metric
        dump(directory/(mode+'.prediction.json'),sqls)
    report={'split':split,'completed_questions':len(rows),'full_expected_partition_complete':True,
            'full_benchmark_complete':split=='test' and len(rows)==1167,'primary_variant':'v4_selected',
            'selected_policy':policy,'variants':variants}
    dump(directory/'evaluation.json',report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v4_20261029_r1')
    parser.add_argument('--phase',choices=['tune','audit','test'],default='tune')
    parser.add_argument('--workers',type=int,default=8)
    args=parser.parse_args()
    if not 1<=args.workers<=16:
        parser.error('Invalid workers')
    directory=run_directory(args.run_name)
    directory.mkdir(parents=True,exist_ok=True)
    plan=plan_v4()
    frozen={'plan':plan,'generation_source_run':str(SOURCE_RUN),'generation_protocol_sha256':sha(SOURCE_RUN/'protocol.json'),
            'generation_source_records_sha256':sha(SOURCE_RUN/'test/records.jsonl'),
            'source_sha256':{p.name:sha(p) for p in ROOT.glob('*.py') if p.name!='report_v4.py'},
            'v3_source_sha256':{p.name:sha(p) for p in V3.glob('*.py') if p.name!='report_v3.py'},
            'database_sha256':sha(DB),'scorer_sha256':sha(BASELINE/'baseline_core.py'),'workers':args.workers,
            'test_policy_selection_allowed':False,'model_generation_prompts_unchanged':True}
    freeze(directory/'protocol.json',frozen)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    metadata=load_metadata()
    if args.phase in {'tune','audit'}:
        balance=api_balance()
        if balance.get('is_available') is False:
            raise RunBlocked('No balance; checkpoints retained')
        if not (directory/'starting_balance.json').exists():
            dump(directory/'starting_balance.json',balance)
        rag=StructuredRAG(excluded_ids=set(plan['tune']+plan['audit']))
        freeze(directory/'development_manifest.json',rag.manifest)
        by_id={r['id']:r for r in question_rows('dev')}
        phase_dir=directory/args.phase
        if args.phase=='tune':
            initialize_tune_cache(phase_dir)
            rows=infer_dev(phase_dir,[by_id[key] for key in plan['tune']],rag,metadata,args.workers,'tune')
            if not (directory/'policy.json').exists():
                policy=fit_v4(rows,plan)
                policy.update(protocol_sha256=sha(directory/'protocol.json'),tune_records_sha256=sha(phase_dir/'records.jsonl'))
                dump(directory/'policy.json',policy)
            policy=load(directory/'policy.json')
            report=evaluate(phase_dir,rows,'dev',policy['selected_policy'],plan['tune'])
            print('DEV:',policy['selected_policy'],policy['selected_summary'],flush=True)
            return 0
        policy=load(directory/'policy.json')
        if policy['protocol_sha256']!=sha(directory/'protocol.json') or policy['tune_records_sha256']!=sha(directory/'tune/records.jsonl'):
            raise ValueError('Policy provenance mismatch')
        freeze(phase_dir/'config.json',{'policy_sha256':sha(directory/'policy.json'),'protocol_sha256':sha(directory/'protocol.json')})
        rows=infer_dev(phase_dir,[by_id[key] for key in plan['audit']],rag,metadata,args.workers,'audit')
        report=evaluate(phase_dir,rows,'dev',policy['selected_policy'],plan['audit'])
        print('AUDIT:',report['variants']['v4_selected']['scores'],flush=True)
        return 0
    policy=load(directory/'policy.json')
    audit=load(directory/'audit/evaluation.json')
    audit_config=load(directory/'audit/config.json')
    if (audit_config['policy_sha256']!=sha(directory/'policy.json') or audit_config['protocol_sha256']!=sha(directory/'protocol.json')
        or policy['protocol_sha256']!=sha(directory/'protocol.json') or policy['tune_records_sha256']!=sha(directory/'tune/records.jsonl')
        or audit['completed_questions']!=100 or audit['selected_policy']!=policy['selected_policy']):
        raise ValueError('Complete audit of the same frozen policy required before cached test replay')
    source=SOURCE_RUN/'test/records.jsonl'
    if sha(source)!=frozen['generation_source_records_sha256']:
        raise ValueError('Source generation records changed')
    raw_rows=[json.loads(x) for x in source.read_text(encoding='utf-8').splitlines()]
    test_dir=directory/'test'
    test_dir.mkdir(exist_ok=True)
    freeze(test_dir/'config.json',{'policy_sha256':sha(directory/'policy.json'),'protocol_sha256':sha(directory/'protocol.json'),
                                'model_calls':0,'source_generation':str(source),'source_sha256':sha(source)})
    def replay(row):
        return {'id':row['id'],'question':row['question'],'partition':'test',
                'candidates':[normalize_candidate(row['question'],c,metadata) for c in row['candidates']]}
    status(test_dir,'test',0,1167,'replaying_cached_SQLs')
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows=list(pool.map(replay,raw_rows))
    save_rows(test_dir,rows)
    report=evaluate(test_dir,rows,'test',policy['selected_policy'],[r['id'] for r in question_rows('test')])
    dump(directory/'ending_balance.json',api_balance())
    status(test_dir,'test',1167,1167,'complete')
    for name,metric in report['variants'].items():
        print(name,metric['scores'],'EX',metric['EX'],'coverage',metric['coverage'],flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
