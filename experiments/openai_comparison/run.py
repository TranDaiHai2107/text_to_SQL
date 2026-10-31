"""New V5 + native Vanna inference on the original EHRSQL test with OpenAI."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
EXPERIMENTS = ROOT.parent
WORKSPACE = ROOT.parents[1]
sys.path.insert(1,str(EXPERIMENTS/'research_validation'))
from validation_common import activate_methods, verify_lock, BASELINE, DB, V5_RUN, VANNA, load, dump, sha, freeze
activate_methods()
from infrastructure import question_rows
from retrieval_v3 import StructuredRAG
from pipeline_v3 import run_question
from postprocess_v5 import load_metadata, normalize_candidate, select_v5
from openai_client import OpenAIReasoningClient, APIBlocked

MODES = ('ours_direct','ours_structural','ours_plan','ours_v5','vanna','vanna_gef')


def directory_for(name):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',name):
        raise ValueError('Invalid run name')
    return ROOT/'runs'/name


def protocol(model, effort, cap):
    verify_lock()
    return {'provider':'openai','model':model,'endpoint':'https://api.openai.com/v1/responses',
            'reasoning_effort':effort,'reasoning_enabled_for_all_routes_and_Vanna':True,
            'max_output_tokens_per_request_including_reasoning':cap,
            'service_tier':'default','store':False,'split':'test','expected_questions':1167,
            'knowledge_splits':['train','dev'],'knowledge_questions':6287,
            'ours':'Frozen V3 generation + frozen V5 strict3_canonical; backbone/reasoning transport changed only',
            'vanna':'Native legacy SQL/RAG in Vanna 2.0.2; one generation, plus derived GEF variant',
            'ours_repair':'At most one concrete schema/execution repair per route, as in frozen V3',
            'vanna_repair':False,'ours_selected_policy':'strict3_canonical','fit_new_thresholds':False,
            'equal_backbone_and_reasoning':True,'equal_inference_budget':False,
            'research_status':'Exploratory evaluation on the already-used original test; not independent confirmation',
            'scope':'English-to-SQL only; no Vietnamese/ASR/new database phase',
            'database_sha256':sha(DB),'scorer_sha256':sha(BASELINE/'baseline_core.py'),
            'frozen_V5_lock_sha256':sha(EXPERIMENTS/'research_validation/V5_LOCK.json'),
            'historical_V5_policy_sha256':sha(V5_RUN/'policy.json'),
            'new_source_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},
            'source_test_inputs_sha256':sha(BASELINE/'data/inputs/test.json'),
            'historical_outputs_overwritten':False,
            'pricing_reference':'https://developers.openai.com/api/docs/models/gpt-6.1-terra',
            'docs_reference':'https://developers.openai.com/api/docs/guides/reasoning'}


def native_export(record):
    if record.get('gef_filtered') or record['execution']['abstained']:
        return 'null'
    return record['sql'] if record['execution']['valid'] else ''


def run(args):
    config = protocol(args.model,args.effort,args.max_output_tokens)
    directory = directory_for(args.run_name)
    directory.mkdir(parents=True,exist_ok=True)
    freeze(directory/'protocol.json',config)
    stop = threading.Event()
    clients = {family:OpenAIReasoningClient(directory/family, model=args.model,effort=args.effort,
               max_output_tokens=args.max_output_tokens,stop_event=stop) for family in ('ours','vanna')}
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    rag = StructuredRAG()
    metadata = load_metadata()
    sys.path.insert(1,str(VANNA))
    from vanna_adapter import make_vanna, assert_index, generate, training_documents
    from benchmark import corpus, schema
    seed_vn = make_vanna(VANNA/'indexes/chroma_train_dev')
    vanna_index = assert_index(seed_vn,VANNA/'indexes/chroma_train_dev',('train','dev'))
    for kind,documents in training_documents(corpus(('train','dev')),schema()).items():
        existing=getattr(seed_vn,kind+'_collection').get(include=['documents'])
        if dict(zip(existing['ids'],existing['documents']))!=documents:
            raise ValueError('Vanna knowledge content changed')
    freeze(directory/'knowledge.json',{'ours':rag.manifest,'vanna':vanna_index})
    selected = sorted(question_rows('test'),key=lambda r:hashlib.sha256(('openai_fixed_order_20261030:'+r['id']).encode()).hexdigest())
    expected = {r['id']:r['question'] for r in selected}
    completed = {p.stem:load(p) for p in (directory/'paired').glob('*.json')}
    if any(k not in expected or row['question']!=expected[k] or set(row['predictions'])!=set(MODES)
           for k,row in completed.items()):
        raise ValueError('Invalid paired checkpoint')
    retrieval_lock = threading.RLock()
    local = threading.local()
    class LockedRAG:
        schema = rag.schema
        known_values = rag.known_values
        def retrieve(self,question,route='direct'):
            with retrieval_lock:
                return rag.retrieve(question,route=route)
    safe_rag = LockedRAG()
    def native_vanna():
        if not hasattr(local,'vn'):
            local.vn=make_vanna(VANNA/'indexes/chroma_train_dev',client=clients['vanna'],
                               embedding_function=seed_vn.embedding_function)
            for method in ('get_similar_question_sql','get_related_ddl','get_related_documentation'):
                original=getattr(local.vn,method)
                def locked(*a,_method=original,**kw):
                    with retrieval_lock:
                        return _method(*a,**kw)
                setattr(local.vn,method,locked)
        return local.vn
    def work(item):
        ours_path=directory/'ours/checkpoints'/(item['id']+'.json')
        if ours_path.exists():
            raw=load(ours_path)
        else:
            raw=run_question(item,safe_rag,{'normal':clients['ours'],'reasoning':clients['ours']})
            dump(ours_path,raw)
        if raw['question']!=item['question'] or len(raw['candidates'])!=3:
            raise ValueError('Invalid V5 source checkpoint')
        candidates=[normalize_candidate(item['question'],c,metadata) for c in raw['candidates']]
        chosen=select_v5(candidates,'strict3_canonical')
        vanna_path=directory/'vanna/checkpoints'/(item['id']+'.json')
        if vanna_path.exists():
            native=load(vanna_path)
        else:
            native=generate(native_vanna(),item)
            dump(vanna_path,native)
        if native['question']!=item['question']:
            raise ValueError('Invalid Vanna checkpoint')
        base=native['variants']['vanna']
        gef=deepcopy(base)
        check=gef['execution']
        gef['gef_filtered']=bool(not check['abstained'] and (not check['valid'] or check['empty']))
        if gef['gef_filtered']:
            gef['sql']='null'
        predictions={MODES[i]:candidates[i]['sql'] for i in range(3)}
        predictions.update(ours_v5=chosen['sql'],vanna=native_export(base),vanna_gef=native_export(gef))
        return {'id':item['id'],'question':item['question'],'predictions':predictions,
                'selection':chosen['selection'],'selected_candidate_index':chosen['selected_candidate_index'],
                'ours_call_hashes':list(dict.fromkeys(h for c in raw['candidates'] for h in c['call_hashes'])),
                'vanna_call_hashes':base['call_hashes']}
    def status(state,reason=None):
        value={'state':state,'run':args.run_name,'model':args.model,'reasoning_effort':args.effort,
               'completed_questions':len(completed),'expected_questions':1167,
               'reason':reason,'updated_at_unix':time.time()}
        dump(directory/'status.json',value)
        dump(ROOT/'STATUS.json',value)
    remaining=[r for r in selected if r['id'] not in completed]
    if args.limit is not None:
        remaining=remaining[:max(0,args.limit-len(completed))]
    status('running')
    reason=None
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        pending=[pool.submit(work,item) for item in remaining]
        for future in as_completed(pending):
            try:
                result=future.result()
            except CancelledError:
                continue
            except Exception as error:
                if reason is None:
                    reason=clients['ours'].redact(str(error))
                    stop.set()
                    for task in pending:
                        task.cancel()
                continue
            dump(directory/'paired'/(result['id']+'.json'),result)
            completed[result['id']]=result
            status('running',reason)
            if len(completed)%10==0 or len(completed)==1167:
                print(f'OpenAI paired: {len(completed)}/1167',flush=True)
    verify_lock()
    if reason:
        status('blocked_with_checkpoints',reason)
        print('BLOCKED:',reason,flush=True)
        return 2
    if len(completed)!=1167:
        status('partial_checkpoint_no_final_score')
        print(f'PARTIAL {len(completed)}/1167; no final score or null padding',flush=True)
        return 0
    for mode in MODES:
        freeze(directory/(mode+'.prediction.json'),{r['id']:completed[r['id']]['predictions'][mode] for r in selected})
    status('inference_complete_unscored')
    from score import score_run
    report=score_run(directory)
    status('complete')
    for name,m in report['variants'].items():
        print(name,m['scores'],'EX',m['EX'],'VSR',m['VSR'],flush=True)
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='gpt61terra_high_20261030_r1')
    parser.add_argument('--model',default=os.getenv('OPENAI_BENCHMARK_MODEL','gpt-6.1-terra'))
    parser.add_argument('--effort',choices=('low','medium','high'),default='high')
    parser.add_argument('--max-output-tokens',type=int,default=32768)
    parser.add_argument('--workers',type=int,default=16)
    parser.add_argument('--limit',type=int)
    args=parser.parse_args()
    if not 1<=args.workers<=32 or args.max_output_tokens<25000 or (args.limit is not None and args.limit<1):
        parser.error('Invalid workers/output budget/limit')
    raise SystemExit(run(args))
