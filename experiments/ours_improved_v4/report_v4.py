"""Verify v4 with the official Docker scorer; generation remains frozen v3."""
import argparse
from collections import Counter
import json
from infrastructure_v4 import ROOT,V3,BASELINE,DB,load,dump,sha,run_directory
from run_v4 import SOURCE_RUN,MODES
from report_v3 import docker_score,validate_initial_request_hashes
from evaluate import paired_delta
from postprocess_v4 import select_v4


def events(path):
    return [json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def usage_from_events(items):
    good=[e for e in items if e['kind']=='success']
    return {'calls':len(good),'failed_attempts':len(items)-len(good),
            **{key:sum(e['usage'].get(key,0) or 0 for e in good) for key in ['prompt_tokens','completion_tokens','total_tokens']}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v4_20261029_r1')
    parser.add_argument('--docker',action='store_true')
    args=parser.parse_args()
    directory=run_directory(args.run_name)
    host=load(directory/'test/evaluation.json')
    if not host['full_benchmark_complete']:
        raise ValueError('Full1167test required')
    protocol=load(directory/'protocol.json')
    policy=load(directory/'policy.json')
    test_config=load(directory/'test/config.json')
    audit_config=load(directory/'audit/config.json')
    audit=load(directory/'audit/evaluation.json')
    if (policy['protocol_sha256']!=sha(directory/'protocol.json') or policy['tune_records_sha256']!=sha(directory/'tune/records.jsonl')
        or test_config['policy_sha256']!=sha(directory/'policy.json') or test_config['protocol_sha256']!=sha(directory/'protocol.json')
        or audit_config['policy_sha256']!=sha(directory/'policy.json') or audit_config['protocol_sha256']!=sha(directory/'protocol.json')
        or audit['selected_policy']!=policy['selected_policy'] or audit['completed_questions']!=100):
        raise ValueError('Frozen tune/audit/test policy provenance mismatch')
    if any(sha(ROOT/name)!=value for name,value in protocol['source_sha256'].items()) or any(
        sha(V3/name)!=value for name,value in protocol['v3_source_sha256'].items()):
        raise ValueError('Code changed after freezing')
    if sha(DB)!=protocol['database_sha256'] or sha(BASELINE/'baseline_core.py')!=protocol['scorer_sha256']:
        raise ValueError('Pinned database/scorer changed')
    source_file=SOURCE_RUN/'test/records.jsonl'
    if sha(source_file)!=protocol['generation_source_records_sha256']:
        raise ValueError('Source SQL candidates changed')
    source_records={r['id']:r for r in [json.loads(x) for x in source_file.read_text(encoding='utf-8').splitlines()]}
    records=[json.loads(x) for x in (directory/'test/records.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(records)!=1167 or {r['id'] for r in records}!=set(source_records):
        raise ValueError('Incomplete cached test replay')
    for row in records:
        original=source_records[row['id']]
        if row['question']!=original['question'] or len(row['candidates'])!=3:
            raise ValueError('Wrong question/candidate association')
        for index,candidate in enumerate(row['candidates']):
            if candidate['v4_original_record']!=original['candidates'][index]:
                raise ValueError('Source generation was mutated')
    previous_sql=load(SOURCE_RUN/'test/v3_selected.prediction.json')
    if any(select_v4(row['candidates'],'strict3_raw')['sql']!=previous_sql[row['id']] for row in records):
        raise ValueError('Raw reference policy no longer reproduces frozen v3 SQL exactly')
    request_count=validate_initial_request_hashes(records)
    labels=load(BASELINE/'data/gold/test/label.json')
    answerable={k for k in labels if labels[k]!='null'}
    rows={}
    outcomes={}
    validation={}
    for mode in MODES:
        score,path=docker_score(directory,mode) if args.docker else (host['variants'][mode],str(directory/'test/evaluation.json'))
        pred=load(directory/'test'/(mode+'.prediction.json'))
        if set(pred)!=set(labels) or set(score['per_question'])!=set(labels):
            raise ValueError('Wrong test IDs')
        nonnull={k for k in pred if pred[k]!='null'}
        errors={e['id'] for e in score.get('execution_errors',[])}|{k for k,sql in pred.items() if not sql.strip()}
        correct_sql=sum(score['per_question'][k]=='correct' for k in answerable)
        rows[mode]={'scores':score['scores'],'EX':100*correct_sql/len(answerable),
                    'VSR':100*len(nonnull-errors)/len(labels) if args.docker else score['VSR'],
                    'correct':score['correct'],'wrong':score['wrong'],'correct_answerable_sql':correct_sql,
                    'false_abstentions':sum(pred[k]=='null' for k in answerable),
                    'false_answers_on_unanswerable':sum(pred[k]!='null' for k in set(labels)-answerable),
                    'coverage':100*len(nonnull)/len(labels),'precision':100*correct_sql/len(nonnull) if nonnull else None,'source':path}
        outcomes[mode]=score['per_question']
        validation[mode]={'same_host_per_question':score['per_question']==host['variants'][mode]['per_question'],
                          'same_host_scores':score['scores']==host['variants'][mode]['scores']}
    if not all(v['same_host_per_question'] and v['same_host_scores'] for v in validation.values()):
        raise ValueError('Host/Docker discrepancy requires investigation')
    previous=load(SOURCE_RUN/'FINAL_RESULTS.json')
    v3=load(SOURCE_RUN/'test/evaluation.json')
    paper=load(BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json')
    for name in ['v3_selected','v3_direct','v2_calibrated','v2_grounded','paper','vanna','vanna_gef']:
        rows[name]=previous['rows'][name]
    primary=rows['v4_selected']
    incremental={phase:usage_from_events(events(directory/phase/'api_events.jsonl')) for phase in ['tune','audit','test']}
    effective={}
    for phase in ['tune','audit','test']:
        phase_rows=[json.loads(x) for x in (directory/phase/'records.jsonl').read_text(encoding='utf-8').splitlines()]
        used={h for r in phase_rows for c in r['candidates'] for h in c['call_hashes']}
        origin=events(SOURCE_RUN/('test' if phase=='test' else 'tune')/'api_events.jsonl') if phase in {'tune','test'} else []
        available={e['request_hash']:e for e in origin+events(directory/phase/'api_events.jsonl') if e['kind']=='success'}
        if used-set(available):
            raise ValueError('Missing effective generation usage records')
        effective[phase]=usage_from_events([available[h] for h in used])
    comparisons={'paper':paired_delta(paper['per_question'],outcomes['v4_selected']),
                 'v3_same_generated_candidates':paired_delta(v3['variants']['v3_selected']['per_question'],outcomes['v4_selected'])}
    transitions=Counter(v3['variants']['v3_selected']['per_question'][key]+' -> '+outcomes['v4_selected'][key] for key in labels)
    new_guards=Counter(c.get('v4_guard_reason','not_newly_guarded') for row in records for c in row['candidates'])
    report={'run':args.run_name,'test_questions':1167,'primary':'v4_selected','primary_metric':'RS10',
            'selected_policy':policy['selected_policy'],'runtime':'Docker official scorer' if args.docker else 'Host official scorer',
            'rows':rows,'comparisons':comparisons,'validation':validation,
            'initial_test_requests_verified':request_count,'source_generation_unchanged':True,'test_model_calls_this_iteration':0,
            'raw_reference_SQL_identical_to_v3':True,'v3_to_v4_primary_transitions':dict(transitions),
            'new_candidate_guard_reasons':dict(new_guards),
            'incremental_API_usage':incremental,'effective_generation_API_usage_including_reuse':effective,
            'tune_grid':policy['tune_grid'],'audit_primary':audit['variants']['v4_selected'],
            'exceeds_paper_RS10':primary['scores']['RS10']>paper['scores']['RS10'],
            'development_protocol':protocol['plan'],
            'limitations':['Overall design already observed prior test results; exploratory, not an untouched final test.',
                           'V4 numerical/ICD fixes developed only on tuning records and checked with a fresh100question audit.',
                           'Paper uses a different fine-tuned model and train-only protocol; not a controlled claim of method superiority.',
                           'Agreement follows benchmark numeric3precision on full rows, not a proof of clinical correctness.']}
    dump(directory/'FINAL_RESULTS.json',report)
    lines=['# V4 — kết quả chính thức của hệ thống đề xuất','',
           'Đủ 1.167 câu test. Generation giữ nguyên ba ứng viên DeepSeek Flash của V3; chỉ thay kiểm tra metadata/chuẩn so kết quả/chọn ứng viên. Không gọi model lại trên test.',
           f'Policy khóa từ tuning: **{policy["selected_policy"]}**. Runtime: {report["runtime"]}.','',
           '## Kết quả','']
    for label,key in [('V4 primary','v4_selected'),('V4 direct + guard','v4_direct'),('V4 structural + guard','v4_structural'),
                      ('V4 plan + guard','v4_plan'),('V3 primary','v3_selected'),('V2 đầy đủ','v2_calibrated'),
                      ('V2 generation','v2_grounded'),('Paper ProbGate','paper')]:
        r=rows[key]
        lines.append(f'- **{label}**: RS0={r["scores"]["RS0"]:.2f}; RS5={r["scores"]["RS5"]:.2f}; RS10={r["scores"]["RS10"]:.2f}; RSN={r["scores"]["RSN"]:.2f}; EX={r["EX"]:.2f}%; VSR={r["VSR"]:.2f}%.')
    lines+=['',f'Primary: {primary["correct"]} đúng, {primary["wrong"]} sai, {primary["false_abstentions"]} từ chối nhầm; false answer trên unanswerable={primary["false_answers_on_unanswerable"]}; coverage={primary["coverage"]:.2f}%.',
            f'Vượt RS10 paper theo điểm quan sát: **{report["exceeds_paper_RS10"]}**.',
            '[ProbGate paper](https://aclanthology.org/2024.clinicalnlp-1.65/): RS là số công bố đã kiểm tra từ cache; EX/VSR paper tính bổ sung, không phải cột paper công bố.','',
            '## Cách chọn và kiểm tra','',
            f'Tune RS10={policy["selected_summary"]["scores"]["RS10"]:.2f}; audit100câu mới RS10={audit["variants"]["v4_selected"]["scores"]["RS10"]:.2f}. Audit mới không trùng các tập đã chấm trước, không chọn lại policy từ audit.',
            '400 câu tune+audit bị loại khỏi RAG trong phát triển; final generation đã có train+dev6.287câu từ V3.',
            'Chuẩn fingerprint dùng process_item chính thức ở độ chính xác3số, nhưng giữ toàn bộ dòng/shape/duplicate; không cap100 dòng khi bỏ phiếu. Mã ICD kiểm tra với full dictionary, không lấy thiếu patient facts làm lý do từ chối.',
            'Trivial scalar và exact binding là các policy đã khai báo trước khi audit; không chọn bằng test.','']
    for name,value in comparisons.items():
        lines.append(f'- So với {name}: RS10 {value["delta_points"]:+.2f}; paired bootstrap95% {value["paired_bootstrap_95_percent_interval"]}.')
    lines+=['','## Tài nguyên và provenance','',
            f'{request_count} request generation ban đầu của test đã được tái tạo hash và kiểm tra. Cả1.167bộ candidates gốc được giữ bất biến.',
            'V3 nguồn được giữ nguyên với RS10=71,21. Không thay lịch sử hoặc chỉ giữ lần điểm đẹp.','']
    for phase in ['tune','audit','test']:
        inc=incremental[phase]; eff=effective[phase]
        lines.append(f'- {phase}: gọi mới {inc["calls"]}; input mới {inc["prompt_tokens"]:,}, output mới {inc["completion_tokens"]:,}. Generation hiệu dụng gồm cache: {eff["calls"]} calls, input {eff["prompt_tokens"]:,}, output {eff["completion_tokens"]:,}.')
    lines+=['','Output tokens bao gồm reasoning. Các generation call được tái sử dụng vẫn tính vào compute hiệu dụng, không gọi đó là inference miễn phí.','',
            '## Giới hạn','',
            '**Đây là cải thiện exploratory sau các vòng đã xem điểm test. Không tuyên bố là holdout độc lập.**',
            'So với V3, cùng model/candidates/compute generation cho phép quan sát tác động gói validation+selection. So với paper, khác model/fine-tuning, knowledge và tài nguyên nên không tách riêng ưu thế phương pháp.',
            'Khoảng tin cậy có thể chứa0 dù điểm quan sát cao hơn; cần đọc cùng CI và cần dữ liệu chưa dùng để thiết kế để khẳng định tổng quát.',
            'Đánh giá này là English→SQL, không xác nhận ASR, câu trả lời tự nhiên hay độ an toàn lâm sàng.','']
    (directory/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    try:
        dump(ROOT/'STATUS.json',{'state':'complete','run':args.run_name,'test_questions':1167,'primary':primary,
                               'exceeds_paper_RS10':report['exceeds_paper_RS10'],'report':str(directory/'FINAL_REPORT.md')})
    except PermissionError:
        pass
    print(json.dumps({'primary':primary,'exceeds_paper_RS10':report['exceeds_paper_RS10'],'comparisons':comparisons,
                      'incremental':incremental,'effective':effective},indent=2))


if __name__=='__main__':
    main()
