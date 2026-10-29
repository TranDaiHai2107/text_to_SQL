"""Matched DeepSeek comparison. Train+dev knowledge; untouched full test only."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
OURS = ROOT.parent/'apply_my_work_to_baseline'
VANNA = ROOT.parent/'vanna_ehrsql'
for path in (OURS, VANNA):
    sys.path.insert(0, str(path))
from benchmark import BASELINE, DB, load, dump, sha, questions
from retrieval import ThreeRAG
from pipeline import run_question
from deepseek_client import DeepSeekClient
from model_client import RunBlocked
from vanna_adapter import make_vanna, assert_index, generate

OUR_MODES = ['full_schema_rag', 'full_schema_rag_agentic', 'full_schema_rag_agentic_gef']
OUR_PRIMARY = 'full_schema_rag_agentic_gef'


def save_rows(path, rows):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in rows), encoding='utf-8')
    temporary.replace(path)


def frozen_config(directory, config):
    directory.mkdir(parents=True, exist_ok=True)
    target = directory/'config.json'
    if target.exists() and load(target) != config:
        raise ValueError('Frozen configuration/code changed. Choose a new comparison run name.')
    if not target.exists():
        dump(target, config)


def configurations(name, index_ours, index_vanna, workers):
    common = {'split':'test', 'provider':'deepseek', 'model':'deepseek-flash',
              'reasoning_effort':'none', 'thinking':'disabled', 'temperature':0, 'seed':None,
              'max_sql_completion_tokens':2048, 'max_rewrite_completion_tokens':256,
              'knowledge_splits':['train','dev'], 'knowledge_questions':6287,
              'gold_test_access_during_inference':False, 'selection_protocol':'fixed_before_test_no_dev_tuning',
              'scorer':'official', 'baseline_manifest_sha256':sha(BASELINE/'source_manifest.json'),
              'dataset_protocol_note':'Additional dev labels are retrieval knowledge. This differs from a train-only paper protocol.',
              'workers':workers, 'logprobs_requested':True,
              'comparison_code_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},
              'shared_code_sha256':{p.name:sha(p) for p in OURS.glob('*.py')}}
    ours = {**common, 'system':'proposed', 'modes':OUR_MODES, 'primary_variant':OUR_PRIMARY,
            'repair_retries':2, 'examples_split':'train+dev', 'knowledge_index':index_ours}
    vanna = {**common, 'system':'Vanna AI', 'pipeline':'legacy_SQL_RAG_in_Vanna_2.0.2',
             'modes':['vanna','vanna_gef'], 'primary_variant':'vanna', 'sql_tokens':2048,
             'index':index_vanna, 'examples_split':'train+dev',
             'allow_llm_to_see_data':False, 'auto_training':False,
             'vanna_code_sha256':{p.name:sha(p) for p in VANNA.glob('*.py')},
             'vanna_source_sha256':{p:sha(VANNA/'.vendor/vanna'/p) for p in ['legacy/base/base.py','legacy/chromadb/chromadb_vector.py']}}
    return ours, vanna


def api_balance():
    import httpx
    response = httpx.get('https://api.deepseek.com/user/balance',
                        headers={'Authorization':'Bearer '+os.environ['DEEPSEEK_API_KEY']}, timeout=30)
    if response.status_code != 200:
        return {'available':None, 'http_status':response.status_code}
    return response.json()


def finalize(directory, ours_dir, vanna_dir, state, reason):
    # Inference has ended before any evaluation gold is read.
    from evaluate import evaluate, paired_delta
    from score import score
    ours, vanna = evaluate(ours_dir), score(vanna_dir)
    complete = ours.get('full_benchmark_complete',False) and vanna.get('full_benchmark_complete',False)
    report = {'state':state, 'reason':reason, 'full_test_complete':complete,
              'model':'deepseek-flash', 'provider':'deepseek', 'knowledge_splits':['train','dev'],
              'knowledge_questions':6287, 'test_questions':1167,
              'completed_questions':min(ours['completed_questions'], vanna['completed_questions']),
              'ours_run':ours_dir.name, 'vanna_run':vanna_dir.name,
              'ours_variants':{k:{'scores':m['scores'], 'EX':m['answerable_ex'],
                                  'VSR':m['vsr_all_questions'], 'reliability':m.get('reliability')}
                               for k,m in ours.get('variants',{}).items()},
              'vanna_variants':{k:{'scores':m['scores'], 'EX':m['answerable_ex'],
                                   'VSR':m['vsr_all_questions'], 'reliability':m.get('reliability')}
                                for k,m in vanna.get('variants',{}).items()},
              'api_usage':{'ours':ours.get('api_usage',{}), 'vanna':vanna.get('api_usage',{})},
              'paper_comparison_scope':'System-level comparison: different LLM/training, plus additional dev retrieval knowledge. Not a controlled superiority claim over the original paper method.'}
    try:
        report['ending_account_balance'] = api_balance()
    except Exception:
        report['ending_account_balance'] = {'available':None}
    if complete:
        paper_path = BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json'
        paper = load(paper_path)
        primary = ours['variants'][OUR_PRIMARY]
        reference = vanna['variants']['vanna']
        matched = vanna['variants']['vanna_gef']
        report.update(paper_scores=paper['scores'],
                      ours_minus_paper={k:primary['scores'][k]-paper['scores'][k] for k in paper['scores']},
                      paired_ours_minus_paper=paired_delta(paper['per_question'],primary['per_question']),
                      paired_ours_minus_vanna=paired_delta(reference['per_question'],primary['per_question']),
                      paired_ours_minus_vanna_gef=paired_delta(matched['per_question'],primary['per_question']))
        # Descriptive test error analysis; no further inference or prompt tuning.
        records = [json.loads(line) for line in (ours_dir/'records.jsonl').read_text(encoding='utf-8').splitlines()]
        failures = []
        for row in records:
            result = primary['per_question'][row['id']]
            if result != 'correct':
                record = row['variants'][OUR_PRIMARY]
                failures.append({'id':row['id'], 'question':row['question'], 'outcome':result,
                                 'sql':record['sql'], 'attempts':record['attempts'],
                                 'error':record['execution']['error'], 'gef_filtered':record.get('gef_filtered',False)})
        dump(directory/'error_analysis.json', {'reliability':primary['reliability'], 'failures':failures,
                  'note':'Descriptive analysis only; test failures are not fed back into inference.'})
    dump(directory/'comparison.json', report)
    lines = ['# DeepSeek Flash — đối chiếu hệ thống đề xuất, Vanna và ProbGate', '',
             'Knowledge base: train + dev, 6.287 câu. Test tách riêng: 1.167 câu. Không fine-tune.',
             f"Đã chấm {report['completed_questions']}/1.167 câu paired.", '',
             '**FULL TEST**' if complete else '**PARTIAL: chưa có kết quả cuối, không so điểm mẫu với full paper.**', '']
    for label,key in [('Hệ thống đề xuất','ours_variants'),('Vanna','vanna_variants')]:
        lines += ['## '+label, '']
        for mode,metrics in report[key].items():
            text = ', '.join(f'{k}={v:.4f}' for k,v in metrics['scores'].items())
            ex = 'N/A' if metrics['EX'] is None else f"{metrics['EX']:.4f}"
            lines.append(f"- `{mode}`: {text}; EX={ex}; VSR={metrics['VSR']:.4f}.")
        lines.append('')
    if complete:
        lines += ['## So với paper', '', 'Paper (official cache replay): '+str(report['paper_scores']),
                  '', 'Chênh lệch primary đề xuất: '+str(report['ours_minus_paper']), '',
                  'Khác backbone/fine-tuning và dùng thêm dev làm knowledge: chỉ kết luận mức hệ thống trong cấu hình đã đo.', '']
    if reason:
        lines += ['## Gián đoạn', '', reason, '', 'Checkpoint/cache được giữ; không padding câu thiếu thành null.', '']
    lines += ['## Hướng cải thiện sau phân tích', '',
              '- Chọn bước cải thiện từ phân rã lỗi: sai ngữ nghĩa khi SQL vẫn chạy, từ chối nhầm, hoặc SQL lỗi.',
              '- Muốn dùng ProbGate trên DeepSeek: logprobs đã được lưu nếu API hỗ trợ; ngưỡng cần một tập calibration tách khỏi knowledge, không chọn bằng gold test.',
              '- Nếu sửa phương pháp dựa trên lỗi test này, đánh giá tiếp trên dữ liệu holdout mới; giữ kết quả gốc để tránh chọn điểm test cao nhất.', '']
    (directory/'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    dump(ROOT/'STATUS.json', {'state':state, 'run':directory.name, 'full_test_complete':complete,
                             'completed_questions':report['completed_questions'], 'reason':reason,
                             'report':str(directory/'RESULTS.md')})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', default='deepseek_flash_train_dev_20261028_v1')
    parser.add_argument('--workers', type=int, default=8)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}',args.run_name) or not 1 <= args.workers <= 16:
        parser.error('Invalid run name/workers')
    directory = ROOT/'runs'/args.run_name
    ours_dir, vanna_dir = OURS/'runs'/args.run_name, VANNA/'runs'/args.run_name
    balance = api_balance()
    if balance.get('is_available') is False:
        raise RunBlocked('DeepSeek balance is unavailable; add API credit before inference')
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    rag = ThreeRAG(knowledge_splits=('train','dev'))
    our_index = rag.build()
    index_path = VANNA/'indexes/chroma_train_dev'
    seed_vanna = make_vanna(index_path)
    vanna_index = assert_index(seed_vanna,index_path,('train','dev'))
    our_config, vanna_config = configurations(args.run_name, our_index, vanna_index, args.workers)
    frozen_config(ours_dir,our_config)
    frozen_config(vanna_dir,vanna_config)
    frozen_config(directory,{'ours':our_config,'vanna':vanna_config})
    if not (directory/'starting_balance.json').exists():
        dump(directory/'starting_balance.json',balance)
    commits = directory/'paired'
    commits.mkdir(exist_ok=True)
    completed = {p.stem:load(p) for p in commits.glob('*.json')}
    selected = sorted(questions('test'),key=lambda r:hashlib.sha256(('apply_work_v1:'+r['id']).encode()).hexdigest())
    expected = {row['id']:row['question'] for row in selected}
    if any(key not in expected or pair['ours']['question'] != expected[key] or pair['vanna']['question'] != expected[key]
           for key,pair in completed.items()):
        raise ValueError('Invalid paired checkpoint')
    # Authoritative atomic pair commits recover interruption between JSONL writes.
    for key,path in [('ours',ours_dir),('vanna',vanna_dir)]:
        save_rows(path/'records.jsonl',[pair[key] for pair in completed.values()])
    clients = {'ours':DeepSeekClient(ours_dir), 'vanna':DeepSeekClient(vanna_dir)}
    retrieval_lock = threading.Lock()
    class LockedRAG:
        schema = rag.schema
        def retrieve(self, question, mode):
            with retrieval_lock:
                return rag.retrieve(question,mode)
    safe_rag = LockedRAG()
    local = threading.local()
    def native_vanna():
        if not hasattr(local,'vn'):
            local.vn = make_vanna(index_path,client=clients['vanna'],embedding_function=seed_vanna.embedding_function)
            for name in ['get_similar_question_sql','get_related_ddl','get_related_documentation']:
                original = getattr(local.vn,name)
                def locked(*a,_method=original,**kw):
                    with retrieval_lock:
                        return _method(*a,**kw)
                setattr(local.vn,name,locked)
        return local.vn
    def work(item):
        checkpoint = ours_dir/'checkpoints'/(item['id']+'.json')
        staged = {'id':item['id'],'question':item['question'],'variants':{}}
        def save_stage(mode,record):
            staged['variants'][mode]=record
            dump(checkpoint,staged)
        ours = run_question(item,OUR_MODES,safe_rag,clients['ours'],save_stage)
        vanna = generate(native_vanna(),item)
        record = json.loads(json.dumps(vanna['variants']['vanna']))
        check = record['execution']
        record['gef_filtered'] = bool((not check['valid'] or check['empty']) and not check['abstained'])
        if record['gef_filtered']:
            record['sql']='null'
        vanna['variants']['vanna_gef']=record
        return {'id':item['id'],'ours':ours,'vanna':vanna}
    def status(state,reason=None):
        for path in [directory,ours_dir,vanna_dir]:
            dump(path/'status.json',{'state':state,'split':'test','completed_questions':len(completed),
                 'requested_questions':1167,'updated_at_unix':time.time(),'reason':reason})
        dump(ROOT/'STATUS.json',{'state':state,'run':directory.name,'completed_questions':len(completed),
                               'requested_questions':1167,'knowledge_questions':6287,'reason':reason})
    status('running')
    reason = None
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = [executor.submit(work,item) for item in selected if item['id'] not in completed]
        for future in as_completed(futures):
            try:
                pair = future.result()
            except CancelledError:
                continue
            except Exception as error:
                if reason is None:
                    reason = str(error)
                    for client in clients.values():
                        client.blocked_reason = reason
                        client.blocked.set()
                    for pending in futures:
                        pending.cancel()
                continue
            dump(commits/(pair['id']+'.json'),pair)
            completed[pair['id']]=pair
            for key,path in [('ours',ours_dir),('vanna',vanna_dir)]:
                with (path/'records.jsonl').open('a',encoding='utf-8') as handle:
                    handle.write(json.dumps(pair[key],ensure_ascii=False)+'\n')
                    handle.flush()
            status('running' if reason is None else 'stopping_after_api_error',reason)
            if len(completed)%10 == 0:
                print(f'DeepSeek paired test completed {len(completed)}/1167',flush=True)
    state = 'complete' if len(completed)==1167 else 'blocked_or_interrupted'
    status(state,reason)
    finalize(directory,ours_dir,vanna_dir,state,reason)
    print(f'Comparison ended: {len(completed)}/1167 paired questions. See {directory / "RESULTS.md"}',flush=True)
    return 0 if state=='complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
