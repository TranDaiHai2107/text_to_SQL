"""Official scoring only after all 1167 new paired inferences complete."""
from collections import Counter
import json
from pathlib import Path
import sqlite3

from run import ROOT, BASELINE, DB, V5_RUN, MODES, load, dump, sha, verify_lock
from baseline_core import execute_readonly, post_process_sql, score_answers


def usage(directory):
    path=directory/'api_events.jsonl'
    events=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    paid=[e for e in events if e['kind'] in ('success','incomplete')]
    unique={e['request_hash']:e for e in paid}
    return {'successful_calls':sum(e['kind']=='success' for e in paid),
            'incomplete_calls':sum(e['kind']=='incomplete' for e in paid),
            'failed_attempts':len(events)-len(paid),
            'input_tokens':sum(e['usage']['prompt_tokens'] for e in unique.values()),
            'cached_input_tokens':sum(e['usage'].get('prompt_cache_hit_tokens',0) for e in unique.values()),
            'output_tokens_including_reasoning':sum(e['usage']['completion_tokens'] for e in unique.values()),
            'reasoning_tokens':sum((e['usage'].get('completion_tokens_details') or {}).get('reasoning_tokens') or 0 for e in unique.values()),
            'models':dict(Counter(e['model'] for e in paid)),
            'efforts':dict(Counter(e['reasoning_effort'] for e in paid))}


def score_run(directory):
    directory=Path(directory)
    verify_lock()
    config=load(directory/'protocol.json')
    if any(sha(ROOT/name)!=digest for name,digest in config['new_source_sha256'].items()):
        raise ValueError('Runner changed since inference registration')
    inputs=load(BASELINE/'data/inputs/test.json')['data']
    ids={r['id'] for r in inputs}
    rows=[load(p) for p in (directory/'paired').glob('*.json')]
    if len(rows)!=1167 or {r['id'] for r in rows}!=ids:
        raise ValueError('Full 1167 paired questions required; no padding')
    gold=load(BASELINE/'data/gold/test/answer.json')
    answerable={k for k in gold if gold[k]!='null'}
    output={}
    sql_cache={}
    for mode in MODES:
        sqls=load(directory/(mode+'.prediction.json'))
        if set(sqls)!=ids or any(sqls[r['id']]!=r['predictions'][mode] for r in rows):
            raise ValueError('Incomplete or modified prediction export')
        pred={}
        errors=0
        for key,sql in sqls.items():
            if sql=='null':
                pred[key]='null'
                continue
            if not sql.strip():
                pred[key]='error_pred'
                errors+=1
                continue
            cleaned=post_process_sql(sql)
            if cleaned not in sql_cache:
                try:
                    sql_cache[cleaned]=execute_readonly(cleaned,DB,30)
                except Exception:
                    sql_cache[cleaned]='error_pred'
            pred[key]=sql_cache[cleaned]
            errors+=pred[key]=='error_pred'
        metric=score_answers(gold,pred,'official')
        answered={k for k in sqls if sqls[k]!='null'}
        correct_sql=sum(metric['per_question'][k]=='correct' for k in answerable)
        metric.update(EX=100*correct_sql/len(answerable),VSR=100*(len(answered)-errors)/len(ids),
                      coverage=100*len(answered)/len(ids),
                      answer_precision=100*correct_sql/len(answered) if answered else None,
                      correct_answerable_sql=correct_sql,
                      correct_abstentions=metric['correct']-correct_sql,
                      false_answers_on_unanswerable=sum(sqls[k]!='null' for k in ids-answerable),
                      execution_errors=errors,prediction_sha256=sha(directory/(mode+'.prediction.json')))
        output[mode]=metric
    from validation_common import WORKSPACE
    historical=load(WORKSPACE/'experiments/result_confirmation/CONFIRMED_RESULTS.json')
    costs={family:usage(directory/family) for family in ('ours','vanna')}
    for family,data in costs.items():
        if set(data['models'])!={config['model']} or set(data['efforts'])!={config['reasoning_effort']} or data['incomplete_calls']:
            raise ValueError('Model/reasoning/incomplete response provenance mismatch: '+family)
    report={'state':'complete','split':'test','completed_questions':1167,'answerable_questions':len(answerable),
            'provider':'openai','model':config['model'],'reasoning_effort':config['reasoning_effort'],
            'variants':output,'usage':costs,'historical_references':historical['systems'],
            'protocol_sha256':sha(directory/'protocol.json'),'official_scorer':True,
            'runtime':'Host official core; not newly Docker verified','sqlite':sqlite3.sqlite_version,
            'new_backbone_inference':True,'fine_tuning':False,'V5_algorithm_changed':False,
            'reasoning_disabled_on_all_routes':True,'one_full_pass_only':True,
            'independent_holdout':False,'equal_generation_budget_ours_vs_native_vanna':False,
            'scope':'English-to-SQL only'}
    dump(directory/'evaluation.json',report)
    lines=['# OpenAI — V5 và Vanna trên EHRSQL test', '',
           f"Model **{config['model']}**, reasoning **none**, service tier **flex** cho cả hai hệ thống. Đủ **1.167 câu test**, gồm934answerable và233unanswerable. Một lượt inference mới; không replay SQL của DeepSeek/tác giả.", '',
           '## Kết quả', '']
    for name,m in output.items():
        s=m['scores']
        lines.append(f"- **{name}**: RS0={s['RS0']:.2f}; RS5={s['RS5']:.2f}; RS10={s['RS10']:.2f}; RSN={s['RSN']:.2f}; EX={m['EX']:.2f}%; VSR={m['VSR']:.2f}%; sai={m['wrong']}.")
    lines+=['', '## So với kết quả trước', '',
            'DeepSeek V5: RS10=74,89; EX=92,29%. Vanna DeepSeek: RS10=−58,10; Vanna+GEF=−12,08. ProbGate paper: RS10=74,21.', '',
            'V5 giữ nguyên generation prompt/retrieval, compiler và policy strict3_canonical. Dùng model tiết kiệm GPT-6 Luna, reasoning none ở cả ba route theo yêu cầu người dùng. Không fit lại ngưỡng từ test và không chạy nhiều vòng để lấy điểm cao.', '',
            'Vanna là native legacy SQL/RAG của Vanna2.0.2, cùng model và reasoning none nhưng một lượt generation; V5 có ba lượt và sửa lỗi execution có giới hạn. Vì vậy không gọi đây là đối chứng bằng chi phí. GEF là biến thể lọc cùng output, không gọi model thêm. Giữ nguyên hệ thống và mọi kết quả Vanna trước đó.', '',
            '## Token', '']
    for family,data in costs.items():
        lines.append(f"- {family}: {data['successful_calls']} calls; input={data['input_tokens']:,}; cached input={data['cached_input_tokens']:,}; output gồm reasoning={data['output_tokens_including_reasoning']:,}; reasoning={data['reasoning_tokens']:,}.")
    lines+=['', 'Output tokens đã bao gồm reasoning, không cộng reasoning lần nữa. Không suy ra invoice từ token khi thiếu thông tin billing đầy đủ.', '',
            'Bộ chấm là official core trên host. Đây là test cũ đã dùng trong quá trình phát triển, chỉ là kết quả thực nghiệm của cấu hình mới; không chứng minh độc lập ưu thế phương pháp. Không đánh giá ASR, chuyển ngữ, SQL→text hoặc database mới.', '',
            '[OpenAI model](https://developers.openai.com/api/docs/models/gpt-6-luna) · [Flex](https://developers.openai.com/api/docs/guides/flex-processing) · [ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/)', '']
    (directory/'RESULTS_VI.md').write_text('\n'.join(lines),encoding='utf-8')
    return report
