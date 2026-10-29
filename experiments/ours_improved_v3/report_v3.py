"""Verify only new SQL predictions in Docker and compare frozen references."""
import argparse
from collections import Counter
import hashlib
import json
import subprocess
from infrastructure import ROOT,V2,OURS,WORKSPACE,BASELINE,DB,load,dump,sha,run_directory,question_rows,normalized_question
from scoring_v3 import MODES,api_usage
from evaluate import paired_delta
from pipeline_v3 import messages_for
from retrieval import schema_metadata
from risk_v3 import POLICIES,select_record


def usage_breakdown(directory):
    events=[json.loads(line) for line in (directory/'api_events.jsonl').read_text(encoding='utf-8').splitlines()]
    stages={}
    for event in events:
        if event['kind']!='success':
            continue
        key=event['stage']
        entry=stages.setdefault(key,{'calls':0,'input_tokens':0,'completion_tokens_including_reasoning':0,
                                     'reasoning_tokens_reported':0,'reasoning_usage_missing_calls':0})
        entry['calls']+=1
        usage=event['usage']
        entry['input_tokens']+=usage.get('prompt_tokens',0) or 0
        entry['completion_tokens_including_reasoning']+=usage.get('completion_tokens',0) or 0
        reasoning=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
        if reasoning is None:
            entry['reasoning_usage_missing_calls']+=1
        else:
            entry['reasoning_tokens_reported']+=reasoning
    return stages


def validate_initial_request_hashes(records):
    schemas,_=schema_metadata()
    verified=0
    for row in records:
        for candidate in row['candidates']:
            route=candidate['route']
            params={'provider':'deepseek','model':'deepseek-flash',
                    'messages':messages_for(row['question'],candidate['retrieval'],schemas,route),
                    'temperature':0,'max_tokens':4096 if route=='plan' else 2048,
                    'thinking':{'type':'enabled' if route=='plan' else 'disabled'},'stream':False,'logprobs':False}
            actual=hashlib.sha256(json.dumps(params,sort_keys=True).encode()).hexdigest()
            if actual!=candidate['call_hashes'][0]:
                raise ValueError('Stored inference request does not match frozen prompts: '+row['id']+'/'+route)
            verified+=1
    return verified


def validate_development_exclusions(records,plan):
    blocked=set(plan['tune']+plan['audit'])
    questions={r['id']:r['question'] for r in question_rows('dev')}
    blocked_text={normalized_question(questions[key]) for key in blocked}
    seen=0
    for row in records:
        for candidate in row['candidates']:
            context=candidate['retrieval']
            for example in context['examples']+context['null_neighbors']:
                if example['id'] in blocked or normalized_question(example['question']) in blocked_text:
                    raise ValueError('Held-out development question leaked to RAG prompt')
                seen+=1
    return seen


def policy_ablations(records,route_outcomes,labels):
    """Secondary fixed-grid analysis on the SAME three verified candidates.

    No new policy is selected here. Route outcome labels have already been
    checked against Docker, so SQL executions/LLM calls need not be repeated.
    """
    result={}
    outcomes={}
    for policy in POLICIES:
        details={}
        answered=[]
        for row in records:
            key=row['id']
            index=select_record(row['candidates'],policy)['selected_candidate_index']
            if index is None:
                details[key]='correct' if labels[key]=='null' else 'abstained_answerable'
            else:
                details[key]=route_outcomes[MODES[index]][key]
                answered.append(key)
        counts=Counter(details.values())
        n=len(details)
        result[policy]={'correct':counts['correct'],'wrong':counts['wrong'],
                        'false_abstentions':counts['abstained_answerable'],
                        'coverage':100*len(answered)/n,
                        'answer_precision':100*sum(details[key]=='correct' for key in answered)/len(answered) if answered else None,
                        'scores':{name:100*(counts['correct']-penalty*counts['wrong'])/n for name,penalty in
                                  [('RS0',0),('RS5',5),('RS10',10),('RSN',n)]},
                        'selection_used_test':False,'same_three_candidates_and_inference_cost':True}
        outcomes[policy]=details
    return result,outcomes


def docker_score(directory,mode):
    prediction=directory/'test'/(mode+'.prediction.json')
    target=BASELINE/'runs'/('ours_verified_'+directory.name)/mode
    target.mkdir(parents=True,exist_ok=True)
    saved=target/'prediction.json'
    if saved.exists() and saved.read_bytes()!=prediction.read_bytes():
        raise ValueError('Refusing to replace other predictions')
    saved.write_bytes(prediction.read_bytes())
    output=target/'scores.json'
    if not output.exists():
        relative=target.relative_to(BASELINE).as_posix()
        subprocess.run(['docker','compose','exec','-T','probgate-baseline','python','reproduce.py','score','--split','test',
            '--scorer','official','--predictions',relative+'/prediction.json','--output',relative+'/scores.json'],cwd=WORKSPACE,check=True)
    result=load(output)
    if result['prediction_sha256']!=sha(prediction) or result['scorer']!='official':
        raise ValueError('Docker score provenance mismatch')
    return result,str(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v3_20261029_r2')
    parser.add_argument('--docker',action='store_true')
    args=parser.parse_args()
    directory=run_directory(args.run_name)
    host=load(directory/'test/evaluation.json')
    if not host['full_benchmark_complete'] or host['completed_questions']!=1167:
        raise ValueError('Complete test required; no partial final report')
    protocol=load(directory/'protocol.json')
    policy=load(directory/'policy.json')
    config=load(directory/'test/config.json')
    if (config['policy_sha256']!=sha(directory/'policy.json') or config['protocol_sha256']!=sha(directory/'protocol.json')
        or policy['selected_policy']!=host['selected_policy']):
        raise ValueError('Frozen policy mismatch')
    if any(sha(ROOT/name)!=value for name,value in protocol['source_sha256'].items()):
        raise ValueError('Source code changed since the run')
    if any(sha(ROOT.parent/name)!=value for name,value in protocol['shared_sha256'].items()):
        raise ValueError('Shared historical implementation changed since the run')
    for path,key in [(DB,'database_sha256'),(BASELINE/'source_manifest.json','source_manifest_sha256'),
                     (BASELINE/'baseline_core.py','scorer_sha256')]:
        if sha(path)!=protocol[key]:
            raise ValueError('Pinned data/scorer provenance mismatch: '+key)
    audit_config=load(directory/'audit/config.json')
    audit=load(directory/'audit/evaluation.json')
    if (policy['protocol_sha256']!=sha(directory/'protocol.json')
        or policy['tune_records_sha256']!=sha(directory/'tune/records.jsonl')
        or audit_config['policy_sha256']!=sha(directory/'policy.json')
        or audit_config['protocol_sha256']!=sha(directory/'protocol.json')
        or audit['selected_policy']!=policy['selected_policy'] or audit['completed_questions']!=100):
        raise ValueError('Tune/audit policy provenance mismatch')
    labels=load(BASELINE/'data/gold/test/label.json')
    answerable={key for key in labels if labels[key]!='null'}
    rows={}
    outcomes={}
    validation={}
    for mode in MODES:
        result,source=docker_score(directory,mode) if args.docker else (host['variants'][mode],str(directory/'test/evaluation.json'))
        predictions=load(directory/'test'/(mode+'.prediction.json'))
        if set(predictions)!=set(labels) or set(result['per_question'])!=set(labels):
            raise ValueError('Test IDs do not match exactly')
        nonnull={key for key in predictions if predictions[key]!='null'}
        invalid={e['id'] for e in result.get('execution_errors',[])}|{key for key,sql in predictions.items() if not sql.strip()}
        correct_sql=sum(result['per_question'][key]=='correct' for key in answerable)
        rows[mode]={'scores':result['scores'],'EX':100*correct_sql/len(answerable),'VSR':100*len(nonnull-invalid)/len(labels) if args.docker else result['VSR'],
                    'correct':result['correct'],'wrong':result['wrong'],'correct_answerable_sql':correct_sql,
                    'false_abstentions':sum(predictions[key]=='null' for key in answerable),
                    'false_answers_on_unanswerable':sum(predictions[key]!='null' for key in set(labels)-answerable),
                    'coverage':100*len(nonnull)/len(labels),'answer_precision':100*correct_sql/len(nonnull) if nonnull else None,
                    'invalid_sql_count':len(invalid),'source':source}
        outcomes[mode]=result['per_question']
        validation[mode]={'same_host_per_question':result['per_question']==host['variants'][mode]['per_question'],
                          'score_delta_from_host':{key:result['scores'][key]-host['variants'][mode]['scores'][key] for key in result['scores']}}
    previous=load(V2/'runs/deepseek_flash_v2b_20261028/FINAL_RESULTS.json')
    for mode in ['v2_grounded','v2_calibrated','full_schema_rag_agentic_gef','vanna','vanna_gef','paper']:
        rows[mode]=previous['rows'][mode]
    paper=load(BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json')
    v2=load(V2/'runs/deepseek_flash_v2b_20261028/test/evaluation.json')
    comparisons={key:paired_delta(reference,outcomes['v3_selected']) for key,reference in
        [('paper',paper['per_question']),('v2_full',v2['variants']['v2_calibrated']['per_question']),('v2_generation',v2['variants']['v2_grounded']['per_question'])]}
    records=[json.loads(x) for x in (directory/'test/records.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(records)!=1167 or {r['id'] for r in records}!=set(labels) or any(
        [c['route'] for c in r['candidates']]!=['direct','structural','plan'] for r in records):
        raise ValueError('Candidate order or complete test checkpoint provenance mismatch')
    initial_request_hashes_verified=validate_initial_request_hashes(records)
    tune_records=[json.loads(x) for x in (directory/'tune/records.jsonl').read_text(encoding='utf-8').splitlines()]
    audit_records=[json.loads(x) for x in (directory/'audit/records.jsonl').read_text(encoding='utf-8').splitlines()]
    if {r['id'] for r in tune_records}!=set(protocol['calibration_plan']['tune']) or {r['id'] for r in audit_records}!=set(protocol['calibration_plan']['audit']):
        raise ValueError('Development partition IDs changed')
    inherited_tune_request_hashes_verified=validate_initial_request_hashes(tune_records)
    audit_request_hashes_verified=validate_initial_request_hashes(audit_records)
    checked_development_examples=validate_development_exclusions(tune_records+audit_records,protocol['calibration_plan'])
    if any(not value['same_host_per_question'] or any(delta!=0 for delta in value['score_delta_from_host'].values()) for value in validation.values()):
        raise ValueError('Host/Docker scores disagree; investigate before final report')
    operational={route:{'guard_filtered':sum(r['candidates'][i].get('guard_rejected',False) for r in records),
                        'incomplete_generations':sum(r['candidates'][i].get('finish_reason')!='stop' for r in records),
                        'genuine_model_nulls':sum(r['candidates'][i]['sql']=='null' and not r['candidates'][i].get('guard_rejected') for r in records)}
                 for i,route in enumerate(['direct','structural','plan'])}
    primary=rows['v3_selected']
    prior_guard=load(WORKSPACE/'research/V2_RELIABILITY_DIAGNOSTIC_20261028.json')['hypothetical_generation_plus_existing_guard']
    secondary,secondary_outcomes=policy_ablations(records,outcomes,labels)
    if secondary_outcomes[policy['selected_policy']]!=outcomes['v3_selected']:
        raise ValueError('Secondary policy audit does not reproduce the frozen primary')
    report={'run':args.run_name,'test_questions':1167,'primary_variant':'v3_selected','primary_metric':'RS10',
            'selected_policy':policy['selected_policy'],'minimum_tuning_coverage':policy['min_coverage'],
            'runtime':'Docker official scorer' if args.docker else 'Host official scorer',
            'rows':rows,'comparisons':comparisons,'validation':validation,'operational_diagnostics':operational,
            'previous_v2_guard_only_retrospective_diagnostic':prior_guard,
            'RS10_delta_vs_prior_guard_diagnostic':primary['scores']['RS10']-prior_guard['RS10'],
            'request_provenance':{'test_initial_requests_verified':initial_request_hashes_verified,
                                  'tune_including_inherited_requests_verified':inherited_tune_request_hashes_verified,
                                  'audit_requests_verified':audit_request_hashes_verified,
                                  'development_examples_checked_for_leakage':checked_development_examples},
            'fixed_policy_secondary_ablations':secondary,
            'paired_primary_vs_fixed_majority_same_candidates':paired_delta(secondary_outcomes['majority_two_of_three'],outcomes['v3_selected']),
            'audit_primary':audit['variants']['v3_selected'],'tune_grid':policy['tune_grid'],
            'api_usage':{phase:api_usage(directory/phase) for phase in ['tune','audit','test']},
            'api_usage_by_stage':{phase:usage_breakdown(directory/phase) for phase in ['tune','audit','test']},
            'exceeds_paper_RS10':primary['scores']['RS10']>paper['scores']['RS10'],
            'exceeds_previous_full_RS10':primary['scores']['RS10']>rows['v2_calibrated']['scores']['RS10'],
            'research_status':protocol['research_status'],'reference_model_calls_this_run':0,
            'paper_note':'RS are published reference verified from cache. EX/VSR derived from cache, not published paper metrics.',
            'limits':['Test-informed design; final test is exploratory, not a fresh holdout.',
                      'Same DeepSeek Flash backbone, but plan route enables thinking and adds compute.',
                      'Additional dev retrieval knowledge and different fine-tuning/model protocol from paper.',
                      'Calibration excludes all400questions but final knowledge restores train+dev; no formal conformal guarantee.',
                      'Agreement on one SQLite database does not establish semantic equivalence.']}
    dump(directory/'FINAL_RESULTS.json',report)
    lines=['# V3 — kết quả hệ thống đề xuất','',
           'Đủ 1.167 câu test. Primary/policy được chọn trên 300 câu tuning, khóa trước 100 câu audit và trước test. Không chạy lại mô hình tác giả/Vanna.',
           f'Policy: {policy["selected_policy"]}; coverage tối thiểu khi tuning 35%. Runtime: {report["runtime"]}.','',
           '## Các cấu hình và đối chứng','']
    for label,key in [('V3 primary','v3_selected'),('V3 A/direct + guard','v3_direct'),('V3 B/structural + guard','v3_structural'),
                      ('V3 C/plan-thinking + guard','v3_plan'),('V2 đầy đủ','v2_calibrated'),('V2 generation','v2_grounded'),
                      ('V1 đầy đủ','full_schema_rag_agentic_gef'),('Vanna cũ + GEF','vanna_gef'),('Paper ProbGate','paper')]:
        r=rows[key]
        lines.append(f'- **{label}**: RS0={r["scores"]["RS0"]:.2f}; RS5={r["scores"]["RS5"]:.2f}; RS10={r["scores"]["RS10"]:.2f}; RSN={r["scores"]["RSN"]:.2f}; EX={r["EX"]:.2f}%; VSR={r["VSR"]:.2f}%.')
    lines+=['','[Paper ProbGate](https://aclanthology.org/2024.clinicalnlp-1.65/): RS là mốc công bố đã đối chiếu cache. EX/VSR tính bổ sung từ cache. Các nhánh V3 đã có guard/GEF; không gọi là raw generation.',
            f'V2 generator + guard, bỏ reviewer: RS10={prior_guard["RS10"]:.2f}, EX={prior_guard["EX"]:.2f}%, theo ablation hồi cứu trên output cũ; không là primary cũ. V3 primary hơn mốc chẩn đoán này {report["RS10_delta_vs_prior_guard_diagnostic"]:+.2f} RS10.',
            f'Primary: đúng {primary["correct"]}, sai {primary["wrong"]}, từ chối nhầm {primary["false_abstentions"]}; false answer trên unanswerable {primary["false_answers_on_unanswerable"]}; coverage {primary["coverage"]:.2f}%.',
            f'Vượt mốc paper theo RS10: {report["exceeds_paper_RS10"]}. Kết luận này chỉ theo điểm hệ thống trên cấu hình đã đo.','',
            '## Phát triển và kiểm tra độc lập với lựa chọn policy','',
            f'Tune RS10={policy["selected_summary"]["scores"]["RS10"]:.2f}; audit RS10={audit["variants"]["v3_selected"]["scores"]["RS10"]:.2f}. Audit không chọn lại policy.',
            '400 câu dev bị loại khỏi tất cả example/null-neighbor khi phát triển, cùng câu trùng nội dung. Final knowledge dùng train+dev 6.287 câu.',
            'Nhánh plan bật thinking; các nhánh khác tắt. Không fine-tune LLM. Báo toàn bộ chi phí thay vì quy cải thiện hoàn toàn cho retrieval.','']
    for name,value in comparisons.items():
        lines.append(f'- Primary so với {name}: RS10 {value["delta_points"]:+.2f} điểm; paired bootstrap95% {value["paired_bootstrap_95_percent_interval"]}.')
    lines+=['','## Ablation policy, giữ nguyên model/candidates/chi phí','',
            'Các policy dưới đây đã có trong grid trước test. Đây là kết quả phụ, không dùng chọn lại primary. Cả bảy dùng cùng ba ứng viên và cùng ngân sách inference đã trả phí; chỉ thay quy tắc chọn/từ chối.']
    for name,value in secondary.items():
        lines.append(f'- {name}: RS10={value["scores"]["RS10"]:.2f}; coverage={value["coverage"]:.2f}%; sai={value["wrong"]}.')
    matched=report['paired_primary_vs_fixed_majority_same_candidates']
    lines+=['',f'Primary so với majority2/3 cùng candidates: {matched["delta_points"]:+.2f} RS10; paired bootstrap95% {matched["paired_bootstrap_95_percent_interval"]}. '
            'Đối chứng này kiểm tra đóng góp quy tắc selection; không tách riêng hiệu quả của generation, RAG hay thinking.']
    lines+=['','## Tài nguyên','']
    for phase,usage in report['api_usage'].items():
        lines.append(f'- {phase}: {usage["calls"]} calls; input {usage["prompt_tokens"]:,}; output {usage["completion_tokens"]:,}; failed attempts {usage["failed_attempts"]}.')
    lines+=['','Completion/output tokens gồm cả reasoning tokens; phân rã theo stage trong FINAL_RESULTS.json. Không cộng reasoning thêm lần nữa vào tổng output.',
            'Cache smoke được kế thừa và tính một lần. Số dư tài khoản không phải hóa đơn độc quyền nếu tài khoản có hoạt động khác.','',
            '## Giới hạn nghiên cứu','',
            '**Test đã được xem để thiết kế từ các vòng trước. V3 là exploratory; không tuyên bố test độc lập hay hiệu quả lâm sàng.**',
            'So với paper khác model/fine-tuning, knowledge và ngân sách suy luận. Muốn tách hiệu quả phương pháp cần các đối chứng cùng model/compute và holdout mới.',
            'Các policy không được chọn lại bằng điểm test. Không thay kết quả cũ hoặc loại câu thất bại khỏi mẫu số.','']
    (directory/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    try:
        dump(ROOT/'STATUS.json',{'state':'complete','run':args.run_name,'test_questions':1167,'primary':primary,
                               'selected_policy':policy['selected_policy'],'exceeds_paper_RS10':report['exceeds_paper_RS10'],
                               'report':str(directory/'FINAL_REPORT.md')})
    except PermissionError:
        print('Final report is saved; Windows locked non-authoritative app status metadata.',flush=True)
    print(json.dumps({'primary':primary,'exceeds_paper_RS10':report['exceeds_paper_RS10'],'comparisons':comparisons,'api_usage':report['api_usage']},indent=2))


if __name__=='__main__':
    main()
