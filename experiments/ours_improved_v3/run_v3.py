"""Develop on held-out dev questions, freeze policy, audit, then run full test."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed,CancelledError
import hashlib
import json
import os
import time
from infrastructure import ROOT,OURS,V2,BASELINE,DB,load,dump,sha,freeze,question_rows,run_directory,api_balance,RunBlocked,score_answers
from client_v3 import V3Client
from retrieval_v3 import StructuredRAG
from semantics_v3 import RULE_EVIDENCE
from pipeline_v3 import run_question
from risk_v3 import fit_policy,select_record,NoFeasiblePolicyError,POLICIES,MIN_COVERAGE
from scoring_v3 import candidate_answers,evaluate,api_usage


def calibration_plan():
    labels=load(BASELINE/'data/gold/dev/label.json')
    old_plan=load(V2/'runs/deepseek_flash_v2b_20261028/threshold.json')['plan']
    previously_used=set(old_plan['tune']+old_plan['audit'])
    rule_ids={r['id'] for refs in RULE_EVIDENCE.values() for r in refs if r['split']=='dev'}
    excluded_from_sampling=previously_used|rule_ids
    groups={kind:sorted([r for r in question_rows('dev') if r['id'] not in excluded_from_sampling and (labels[r['id']]=='null')==kind],
        key=lambda r:hashlib.sha256(('v3_dev_20261029:'+r['id']).encode()).hexdigest()) for kind in [False,True]}
    if len(groups[False])<320 or len(groups[True])<80:
        raise ValueError('Insufficient dev partition after excluding prior calibration and semantic evidence')
    return {'tune':[r['id'] for r in groups[False][:240]+groups[True][:60]],
            'audit':[r['id'] for r in groups[False][240:320]+groups[True][60:80]],
            'seed':'v3_dev_20261029','split':'dev','knowledge_exclusion':'All400heldoutIDs_and_exact_question_duplicates_from_all_RAG_examples',
            'old_v2_calibration_and_rule_evidence_excluded_from_sampling':True,'audit_used_for_selection':False,
            'min_tuning_coverage':MIN_COVERAGE,'policies':list(POLICIES),
            'research_status':'Question-held-out dev development; prior test was inspected for v3 design, so final test is exploratory.'}


def protocol(plan,workers):
    return {'model':'deepseek-flash','temperature':0,'routes':['direct','structural','plan'],
            'route_thinking':{'direct':'disabled','structural':'disabled','plan':'enabled'},
            'max_tokens':{'direct':2048,'structural':2048,'plan':4096},'logprobs':False,
            'knowledge_splits':['train','dev'],'final_knowledge_questions':6287,'full_schema_tables':17,
            'calibration_plan':plan,'workers':workers,'primary_variant':'v3_selected','primary_metric':'RS10',
            'no_finetuning':True,'no_author_or_vanna_model_calls':True,
            'source_sha256':{p.name:sha(p) for p in ROOT.glob('*.py') if p.name!='report_v3.py'},
            'shared_sha256':{str(p.relative_to(ROOT.parent)):sha(p) for p in
                [OURS/'pipeline.py',OURS/'deepseek_client.py',OURS/'retrieval.py',OURS/'sql_runtime.py',OURS/'settings.py',
                 V2/'common.py',V2/'hybrid_retrieval.py']},
            'database_sha256':sha(DB),'source_manifest_sha256':sha(BASELINE/'source_manifest.json'),
            'scorer_sha256':sha(BASELINE/'baseline_core.py'),'research_status':plan['research_status']}


def save_rows(directory,rows):
    target=directory/'records.jsonl'
    temporary=target.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows),encoding='utf-8')
    temporary.replace(target)


def infer(directory,selected,rag,workers,phase,max_questions=None):
    directory.mkdir(parents=True,exist_ok=True)
    expected={r['id']:r['question'] for r in selected}
    completed={p.stem:load(p) for p in (directory/'checkpoints').glob('*.json')}
    if any(key not in expected or row['id']!=key or row['question']!=expected[key] or len(row['candidates'])!=3 for key,row in completed.items()):
        raise ValueError('Invalid checkpoint or partition changed')
    normal=V3Client(directory,thinking=False)
    reasoning=V3Client(directory,thinking=True)
    reasoning._event_lock=normal._event_lock
    reasoning._keys_lock=normal._keys_lock
    reasoning._key_locks=normal._key_locks
    clients={'normal':normal,'reasoning':reasoning}
    todo=[r for r in selected if r['id'] not in completed]
    if max_questions is not None:
        todo=todo[:max_questions]
    reason=None
    status_warning=False
    def status(state):
        nonlocal status_warning
        value={'state':state,'phase':phase,'completed_questions':len(completed),'expected_questions':len(selected),
               'reason':reason,'updated_at_unix':time.time()}
        try:
            dump(directory/'status.json',value)
            dump(ROOT/'STATUS.json',{**value,'run':directory.parent.name})
        except PermissionError:
            # A UI/indexer can temporarily hold a Windows status file. Status
            # is non-authoritative; checkpoints and the API cache remain durable.
            if not status_warning:
                print('Status metadata is locked by Windows; continuing with durable checkpoints.',flush=True)
                status_warning=True
    def work(item):
        staged={'id':item['id'],'question':item['question'],'candidates':[],'partition':phase}
        def stage(route,record):
            staged['candidates'].append(record)
            dump(directory/'staged'/(item['id']+'.json'),staged)
        row=run_question(item,rag,clients,stage)
        row['partition']=phase
        return row
    status('running')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(work,item) for item in todo]
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
            status('running' if reason is None else 'stopping')
            if len(completed)%20==0 or max_questions is not None:
                print(f'{phase}: {len(completed)}/{len(selected)} completed',flush=True)
    ordered=[completed[r['id']] for r in selected if r['id'] in completed]
    save_rows(directory,ordered)
    complete=len(completed)==len(selected)
    status('complete' if complete else 'blocked' if reason else 'partial')
    if reason:
        raise RunBlocked(reason)
    return ordered,complete


def phase_config(directory,phase,protocol_hash,policy_hash=None):
    freeze(directory/'config.json',{'phase':phase,'split':'test' if phase=='test' else 'dev',
        'protocol_sha256':protocol_hash,'policy_sha256':policy_hash,
        'exclude_all400_calibration_questions_from_RAG':phase!='test'})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v3_20261029_dev1')
    parser.add_argument('--phase',choices=['tune','audit','test','all'],default='tune')
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--max-questions',type=int)
    args=parser.parse_args()
    if not 1<=args.workers<=16 or (args.max_questions is not None and args.max_questions<1):
        parser.error('Invalid worker/partial limit')
    directory=run_directory(args.run_name)
    directory.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    plan=calibration_plan()
    config=protocol(plan,args.workers)
    freeze(directory/'protocol.json',config)
    balance=api_balance()
    if balance.get('is_available') is False:
        raise RunBlocked('No API balance available; existing checkpoints retained')
    if not (directory/'starting_balance.json').exists():
        dump(directory/'starting_balance.json',balance)
    phash=sha(directory/'protocol.json')
    by_dev={r['id']:r for r in question_rows('dev')}
    heldout=set(plan['tune']+plan['audit'])
    rag=None
    if args.phase in {'tune','all'}:
        rag=StructuredRAG(excluded_ids=heldout)
        freeze(directory/'development_knowledge_manifest.json',rag.manifest)
        phase_config(directory/'tune','tune',phash)
        rows,complete=infer(directory/'tune',[by_dev[key] for key in plan['tune']],rag,args.workers,'tune',args.max_questions)
        if not complete:
            print('Partial tune only; no policy fitted and no audit/test score.',flush=True)
            return 0
        if not (directory/'policy.json').exists():
            gold_all=load(BASELINE/'data/gold/dev/answer.json')
            gold={key:gold_all[key] for key in plan['tune']}
            try:
                fitted=fit_policy(rows,gold,candidate_answers(rows),score_fn=score_answers,allowed_tune_ids=plan['tune'])
            except NoFeasiblePolicyError as error:
                dump(directory/'no_feasible_policy.json',{'grid':error.grid,'min_coverage':error.min_coverage})
                raise
            fitted.update(tune_records_sha256=sha(directory/'tune/records.jsonl'),protocol_sha256=phash)
            dump(directory/'policy.json',fitted)
        policy=load(directory/'policy.json')
        print('DEV POLICY:',policy['selected_policy'],policy['selected_summary'],flush=True)
        evaluate(directory/'tune',rows,'dev',policy['selected_policy'],expected_ids=plan['tune'])
    if args.phase=='tune':
        return 0
    policy=load(directory/'policy.json')
    if policy['protocol_sha256']!=phash or policy['tune_records_sha256']!=sha(directory/'tune/records.jsonl'):
        raise ValueError('Frozen policy provenance mismatch')
    if args.phase in {'audit','all'}:
        if rag is None:
            rag=StructuredRAG(excluded_ids=heldout)
        phase_config(directory/'audit','audit',phash,sha(directory/'policy.json'))
        rows,complete=infer(directory/'audit',[by_dev[key] for key in plan['audit']],rag,args.workers,'audit',args.max_questions)
        if not complete:
            return 0
        result=evaluate(directory/'audit',rows,'dev',policy['selected_policy'],expected_ids=plan['audit'])
        print('AUDIT:',result['variants']['v3_selected']['scores'],flush=True)
    if args.phase=='audit':
        return 0
    if not (directory/'audit/evaluation.json').exists():
        raise ValueError('Complete frozen-policy audit before running full test')
    audit_config=load(directory/'audit/config.json')
    audit_report=load(directory/'audit/evaluation.json')
    if (audit_config['policy_sha256']!=sha(directory/'policy.json') or audit_config['protocol_sha256']!=phash
        or audit_report['selected_policy']!=policy['selected_policy']
        or not audit_report.get('full_expected_partition_complete') or audit_report['completed_questions']!=len(plan['audit'])):
        raise ValueError('Audit does not belong to this frozen policy/protocol')
    final_rag=StructuredRAG(excluded_ids=())
    freeze(directory/'final_knowledge_manifest.json',final_rag.manifest)
    phase_config(directory/'test','test',phash,sha(directory/'policy.json'))
    rows,complete=infer(directory/'test',question_rows('test'),final_rag,args.workers,'test',args.max_questions)
    if not complete:
        return 0
    result=evaluate(directory/'test',rows,'test',policy['selected_policy'],expected_ids=[r['id'] for r in question_rows('test')])
    dump(directory/'ending_balance.json',api_balance())
    for mode,metric in result['variants'].items():
        print(mode,metric['scores'],'EX',metric['EX'],'coverage',metric['coverage'],flush=True)
    print('Completed only proposed system:',directory,flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
