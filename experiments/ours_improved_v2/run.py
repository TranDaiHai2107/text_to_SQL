"""Calibrate on self-excluded dev, freeze gate, then run only the proposed system."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed,CancelledError
import hashlib
import json
import os
import time
from common import ROOT,OURS,BASELINE,DB,OLD_RUN,load,dump,sha,run_directory,question_rows,DeepSeekClient,RunBlocked
from hybrid_retrieval import HybridRAG
from grounded_pipeline import MODES,PRIMARY,run_question
from calibration import calibration_plan,choose_threshold
from scoring import answers,score_records


def api_balance():
    import httpx
    response=httpx.get('https://api.deepseek.com/user/balance',headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']},timeout=30)
    if response.status_code!=200:
        raise RunBlocked(f'Balance check failed: HTTP {response.status_code}')
    return response.json()


def freeze(path,value):
    if path.exists() and load(path)!=value:
        raise ValueError('Frozen protocol changed; use a new run name: '+str(path))
    if not path.exists():
        dump(path,value)


def records(directory,selected):
    expected={r['id']:r['question'] for r in selected}
    rows={p.stem:load(p) for p in (directory/'checkpoints').glob('*.json')}
    if any(key not in expected or row['id']!=key or row['question']!=expected[key] or set(row['variants'])!=set(MODES) for key,row in rows.items()):
        raise ValueError('Invalid checkpoint')
    return rows


def save_rows(directory,rows):
    path=directory/'records.jsonl'
    temporary=path.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows),encoding='utf-8')
    temporary.replace(path)


def infer(directory,selected,rag,workers,threshold,exclude_self):
    directory.mkdir(parents=True,exist_ok=True)
    completed=records(directory,selected)
    client=DeepSeekClient(directory)
    reason=None
    def status(state):
        value={'state':state,'phase':directory.name,'completed_questions':len(completed),'requested_questions':len(selected),
               'updated_at_unix':time.time(),'reason':reason}
        dump(directory/'status.json',value)
        dump(ROOT/'STATUS.json',{**value,'run':directory.parent.name})
    status('running')
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending=[pool.submit(run_question,item,rag,client,threshold,exclude_self) for item in selected if item['id'] not in completed]
        for future in as_completed(pending):
            try:
                row=future.result()
            except CancelledError:
                continue
            except Exception as error:
                if reason is None:
                    reason=str(error)
                    client.blocked_reason=reason
                    client.blocked.set()
                    for job in pending:
                        job.cancel()
                continue
            dump(directory/'checkpoints'/(row['id']+'.json'),row)
            completed[row['id']]=row
            status('running' if reason is None else 'stopping')
            if len(completed)%20==0:
                print(f'{directory.name}: {len(completed)}/{len(selected)} completed',flush=True)
    ordered=[completed[item['id']] for item in selected if item['id'] in completed]
    save_rows(directory,ordered)
    status('complete' if len(completed)==len(selected) else 'blocked_or_interrupted')
    if reason or len(completed)!=len(selected):
        raise RunBlocked(reason or 'Incomplete phase; checkpoint retained')
    return ordered


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v2b_20261028')
    parser.add_argument('--workers',type=int,default=8)
    parser.add_argument('--calibration-only',action='store_true')
    args=parser.parse_args()
    if not 1<=args.workers<=16:
        parser.error('workers must be 1..16')
    directory=run_directory(args.run_name)
    directory.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    plan=calibration_plan()
    protocol={'model':'deepseek-flash','thinking':'disabled','temperature':0,'max_sql_tokens':2048,'max_review_tokens':512,
              'knowledge_splits':['train','dev'],'knowledge_questions':6287,'test_questions':1167,
              'primary_variant':PRIMARY,'modes':MODES,'workers':args.workers,'calibration_plan':plan,
              'baseline_manifest_sha256':sha(BASELINE/'source_manifest.json'),'database_sha256':sha(DB),
              'inference_code_sha256':{p.name:sha(p) for p in ROOT.glob('*.py') if p.name not in {'report.py','verify_docker.py'}},
              'shared_code_sha256':{name:sha(OURS/name) for name in ['deepseek_client.py','pipeline.py','retrieval.py','sql_runtime.py','settings.py']},
              'scorer_sha256':sha(BASELINE/'baseline_core.py'),
              'research_status':'Exploratory improvement informed by v1 test errors; not an untouched holdout. No new test-gold selection.',
              'rerun_author_or_vanna':False}
    freeze(directory/'protocol.json',protocol)
    balance=api_balance()
    if balance.get('is_available') is False:
        raise RunBlocked('No DeepSeek balance available')
    if not (directory/'starting_balance.json').exists():
        dump(directory/'starting_balance.json',balance)
    rag=HybridRAG()
    freeze(directory/'knowledge_manifest.json',rag.manifest)
    selected_ids=set(plan['tune']+plan['audit'])
    calibration_rows=[r for r in question_rows('dev') if r['id'] in selected_ids]
    calibration_dir=directory/'calibration'
    freeze(calibration_dir/'config.json',{'split':'dev','modes':MODES,'primary_variant':PRIMARY,'threshold':None,
                                        'self_exclusion':True,'protocol_sha256':sha(directory/'protocol.json')})
    calibration_records=infer(calibration_dir,calibration_rows,rag,args.workers,None,True)
    # Only now read dev answers. No test labels have been accessed.
    if not (directory/'threshold.json').exists():
        gold=load(BASELINE/'data/gold/dev/answer.json')
        selected_gold={r['id']:gold[r['id']] for r in calibration_records}
        gate=choose_threshold(calibration_records,answers(calibration_records,'v2_verified'),selected_gold,plan)
        gate['calibration_records_sha256']=sha(calibration_dir/'records.jsonl')
        dump(directory/'threshold.json',gate)
    gate=load(directory/'threshold.json')
    if gate['calibration_records_sha256']!=sha(calibration_dir/'records.jsonl'):
        raise ValueError('Calibration records changed after freezing the gate')
    print('Frozen dev-selected threshold:',gate['selected_threshold'],flush=True)
    print('Tune RS10:',gate['tune_selected']['scores']['RS10'],'audit RS10:',gate['audit_selected']['scores']['RS10'],flush=True)
    if args.calibration_only:
        return 0
    test_dir=directory/'test'
    freeze(test_dir/'config.json',{'split':'test','modes':MODES,'primary_variant':PRIMARY,
                                 'threshold':gate['selected_threshold'],'threshold_sha256':sha(directory/'threshold.json'),
                                 'protocol_sha256':sha(directory/'protocol.json'),'self_exclusion':False})
    selected=sorted(question_rows('test'),key=lambda r:hashlib.sha256(('ours_v2_test:'+r['id']).encode()).hexdigest())
    rows=infer(test_dir,selected,rag,args.workers,gate['selected_threshold'],False)
    result=score_records(test_dir,rows,'test',MODES)
    dump(directory/'ending_balance.json',api_balance())
    for name,metric in result['variants'].items():
        print(name,metric['scores'],'EX',metric['answerable_ex'],flush=True)
    print('Completed only the proposed system:',directory,flush=True)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
