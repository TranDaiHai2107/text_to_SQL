"""Compare new predictions to frozen references; never calls any LLM."""
import argparse
from collections import Counter
import json
import subprocess
from common import ROOT,WORKSPACE,BASELINE,OURS,OLD_RUN,load,dump,sha,run_directory
from grounded_pipeline import MODES,PRIMARY
from evaluate import paired_delta


def docker_score(directory,mode):
    source=directory/'test'/(mode+'.prediction.json')
    target=BASELINE/'runs'/('ours_verified_'+directory.name)/mode
    target.mkdir(parents=True,exist_ok=True)
    prediction=target/'prediction.json'
    if prediction.exists() and prediction.read_bytes()!=source.read_bytes():
        raise ValueError('Refusing to replace another prediction')
    prediction.write_bytes(source.read_bytes())
    score_path=target/'scores.json'
    if not score_path.exists():
        relative=target.relative_to(BASELINE).as_posix()
        subprocess.run(['docker','compose','exec','-T','probgate-baseline','python','reproduce.py','score',
            '--split','test','--scorer','official','--predictions',relative+'/prediction.json',
            '--output',relative+'/scores.json'],cwd=WORKSPACE,check=True)
    score=load(score_path)
    if score['prediction_sha256']!=sha(source) or score['scorer']!='official':
        raise ValueError('Docker score provenance mismatch')
    return score,str(score_path)


def usage(directory):
    path=directory/'api_events.jsonl'
    events=[json.loads(x) for x in path.read_text(encoding='utf-8').splitlines()]
    success=[e for e in events if e['kind']=='success']
    return {'calls':len(success),**{k:sum(e['usage'].get(k,0) or 0 for e in success) for k in
        ['prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']},
        'failed_attempts':len(events)-len(success)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_v2b_20261028')
    parser.add_argument('--docker',action='store_true')
    args=parser.parse_args()
    directory=run_directory(args.run_name)
    host=load(directory/'test/evaluation.json')
    if not host['full_benchmark_complete'] or host['completed_questions']!=1167:
        raise ValueError('A complete test is required')
    gate=load(directory/'threshold.json')
    protocol=load(directory/'protocol.json')
    test_config=load(directory/'test/config.json')
    if test_config['threshold_sha256']!=sha(directory/'threshold.json') or test_config['protocol_sha256']!=sha(directory/'protocol.json'):
        raise ValueError('Test did not use the frozen protocol/threshold')
    if any(sha(ROOT/name)!=value for name,value in protocol['inference_code_sha256'].items()):
        raise ValueError('Inference code changed since calibration/test')
    labels=load(BASELINE/'data/gold/test/label.json')
    answerable={key for key,value in labels.items() if value!='null'}
    expected=set(labels)
    rows={}
    outcomes={}
    validations={}
    for mode in MODES:
        metric,source=docker_score(directory,mode) if args.docker else (host['variants'][mode],str(directory/'test/evaluation.json'))
        prediction=load(directory/'test'/(mode+'.prediction.json'))
        if set(prediction)!=expected or set(metric['per_question'])!=expected:
            raise ValueError('Incomplete prediction/evaluation IDs')
        invalid={e['id'] for e in metric.get('execution_errors',[])}|{key for key,value in prediction.items() if not value.strip()}
        nonnull={key for key,value in prediction.items() if value!='null'}
        correct_sql=sum(metric['per_question'][key]=='correct' for key in answerable)
        rows[mode]={'scores':metric['scores'],'EX':100*correct_sql/len(answerable),
                    'VSR':100*len(nonnull-invalid)/len(expected),'correct':metric['correct'],'wrong':metric['wrong'],
                    'correct_answerable_sql':correct_sql,'false_abstentions':sum(prediction[key]=='null' for key in answerable),
                    'false_answers_on_unanswerable':sum(prediction[key]!='null' for key in expected-answerable),
                    'coverage':100*len(nonnull)/len(expected),'answer_precision':100*correct_sql/len(nonnull) if nonnull else None,
                    'invalid_sql_count':len(invalid),'source':source}
        outcomes[mode]=metric['per_question']
        validations[mode]={'host_score_delta':{key:metric['scores'][key]-host['variants'][mode]['scores'][key] for key in metric['scores']},
                           'same_host_per_question':metric['per_question']==host['variants'][mode]['per_question']}
    old=load(ROOT.parent/'deepseek_comparison/runs'/OLD_RUN/'FINAL_RESULTS.json')
    for key in ['full_schema_rag_agentic_gef','vanna','vanna_gef','paper']:
        rows[key]=old['rows'][key]
    old_ours=load(OURS/'runs'/OLD_RUN/'evaluation.json')['variants']['full_schema_rag_agentic_gef']['per_question']
    old_vanna=load(ROOT.parent/'vanna_ehrsql/runs'/OLD_RUN/'evaluation.json')['variants']
    paper=load(BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json')
    comparisons={name:paired_delta(reference,outcomes[PRIMARY]) for name,reference in
        [('v1_ours',old_ours),('paper',paper['per_question']),('vanna',old_vanna['vanna']['per_question']),('vanna_gef',old_vanna['vanna_gef']['per_question'])]}
    records=[json.loads(x) for x in (directory/'test/records.jsonl').read_text(encoding='utf-8').splitlines()]
    rejections=Counter(r['variants'][PRIMARY].get('rejection_reason','no_filter_or_model_null') for r in records)
    confidence_missing=sum(r['variants']['v2_verified']['sql']!='null' and r['variants']['v2_verified']['confidence']['score'] is None for r in records)
    review_errors=sum(bool(r['variants']['v2_verified'].get('review',{}).get('review_error')) for r in records)
    transitions=Counter(outcomes['v2_grounded'][key]+' -> '+outcomes['v2_verified'][key] for key in expected)
    ablation={'grounded_to_verified_transitions':dict(transitions),
              'verified_minus_grounded_RS10':rows['v2_verified']['scores']['RS10']-rows['v2_grounded']['scores']['RS10'],
              'verified_minus_grounded_EX':rows['v2_verified']['EX']-rows['v2_grounded']['EX'],
              'grounded_minus_v1_RS10':rows['v2_grounded']['scores']['RS10']-rows['full_schema_rag_agentic_gef']['scores']['RS10'],
              'grounded_minus_v1_EX':rows['v2_grounded']['EX']-rows['full_schema_rag_agentic_gef']['EX'],
              'interpretation':'Descriptive test ablation, not a replacement primary selected after test. The semantic-review/repair package harms generation in this run; do not assume more agents improve accuracy.'}
    failures=[{'id':r['id'],'question':r['question'],'outcome':outcomes[PRIMARY][r['id']],
               'sql':r['variants'][PRIMARY]['sql'],'rejection_reason':r['variants'][PRIMARY].get('rejection_reason'),
               'gold_sql':labels[r['id']]} for r in records if outcomes[PRIMARY][r['id']]!='correct']
    report={'run':args.run_name,'questions':1167,'answerable':934,'unanswerable':233,'knowledge_questions':6287,
            'primary_variant':PRIMARY,'primary_metric':'RS10','runtime':'Docker official scorer' if args.docker else 'Host official scorer',
            'research_status':protocol['research_status'],'rows':rows,'paired_RS10_deltas':comparisons,
            'calibration':{'threshold':gate['selected_threshold'],'tune':gate['tune_selected'],'audit':gate['audit_selected'],
                           'audit_ungated':gate['audit_ungated'],'confidence_quality':gate['confidence_quality'],
                           'threshold_sha256':sha(directory/'threshold.json')},
            'api_usage':{phase:usage(directory/phase) for phase in ['calibration','test']},
            'validation':validations,'rejection_counts':rejections,'accepted_sql_missing_confidence':confidence_missing,
            'malformed_or_incomplete_semantic_reviews':review_errors,
            'ablation_analysis':ablation,
            'paper_metric_note':'RS scores are published paper reference, verified with author cache. EX/VSR derived from cache, not published in the paper.',
            'references_reused_without_model_calls':True,'resume_provenance':load(directory/'resume_provenance.json') if (directory/'resume_provenance.json').exists() else None,
            'limits':['Same DeepSeek backbone as v1/Vanna; additional calls/metadata/retrieval change the system and budget.',
                      'Different LLM/fine-tuning and train+dev knowledge from the paper; not a controlled method superiority claim.',
                      'v2 design observed v1 test errors; test-informed exploratory result, no fresh untouched holdout.',
                      'Dev calibration excludes self/exact-question duplicates from retrieval; other train+dev knowledge remains.',
                      'English-to-SQL evaluation only; natural-language answer accuracy/ASR/clinical validation are not measured.']}
    dump(directory/'FINAL_RESULTS.json',report)
    dump(directory/'ABLATION_ANALYSIS.json',ablation)
    dump(directory/'ERROR_CASES.json',{'note':'Post-inference descriptive analysis; no further tuning on these cases','cases':failures})
    lines=['# Kết quả cải thiện hệ thống đề xuất v2','',
           'Đủ 1.167 câu test EHRSQL, 934 answerable + 233 unanswerable. Knowledge train+dev 6.287 câu. Model DeepSeek Flash, thinking disabled, không fine-tune.',
           'Primary đã khóa trước test: v2_calibrated, metric RS10. Chỉ chạy lại hệ thống đề xuất; số Vanna/paper/v1 đọc từ kết quả đã lưu.','',
           '## Điểm so sánh','']
    for label,key in [('Hệ thống v2 primary',PRIMARY),('v2 trước verifier/gate','v2_grounded'),('v2 sau verifier, chưa gate','v2_verified'),
                      ('Hệ thống v1','full_schema_rag_agentic_gef'),('Vanna cũ','vanna'),('Vanna + GEF cũ','vanna_gef'),('Paper ProbGate','paper')]:
        r=rows[key]
        lines.append(f'- **{label}**: RS0={r["scores"]["RS0"]:.2f}; RS5={r["scores"]["RS5"]:.2f}; RS10={r["scores"]["RS10"]:.2f}; RSN={r["scores"]["RSN"]:.2f}; EX={r["EX"]:.2f}%; VSR={r["VSR"]:.2f}%.')
    primary=rows[PRIMARY]
    lines+=['','EX/VSR của paper được tính từ prediction cache phát hành, không phải số EX/VSR paper công bố. RS của paper khớp số công bố sau làm tròn.','',
            '## Kết luận theo metric đã chọn','',
            f'Primary: {primary["correct"]} đúng, {primary["wrong"]} trả lời sai, {primary["false_abstentions"]} từ chối nhầm; trả lời sai trên câu không thể trả lời: {primary["false_answers_on_unanswerable"]}.',
            'Giảm trả lời sai có thể làm giảm EX và coverage; không dùng RS10 tăng để khẳng định mọi mặt đều tốt hơn.','']
    for name,comparison in comparisons.items():
        lines.append(f'- Chênh RS10 so với {name}: {comparison["delta_points"]:+.2f} điểm; paired bootstrap 95% {comparison["paired_bootstrap_95_percent_interval"]}.')
    lines+=['','## Bước mới nào giúp và bước nào gây hại?','',
            f'Nhánh tạo SQL v2_grounded có EX={rows["v2_grounded"]["EX"]:.2f}% ({ablation["grounded_minus_v1_EX"]:+.2f} điểm so với v1), RS10={rows["v2_grounded"]["scores"]["RS10"]:.2f} ({ablation["grounded_minus_v1_RS10"]:+.2f} điểm so với v1). Đây là kết quả mô tả của nhánh generation, không đổi primary sau test.',
            f'Thêm gói review/sửa ngữ nghĩa làm EX thay đổi {ablation["verified_minus_grounded_EX"]:+.2f} điểm và RS10 {ablation["verified_minus_grounded_RS10"]:+.2f} điểm. '
            f'{transitions.get("correct -> abstained_answerable",0)} câu đúng bị chuyển thành từ chối; {transitions.get("correct -> wrong",0)} câu đúng bị sửa thành sai; {transitions.get("wrong -> correct",0)} câu sai được chuyển thành đúng.',
            'Không khẳng định mọi bước thêm vào đều có lợi. Chưa nên bật review/repair tự động như một cải thiện đã được chứng minh. Nhánh generation là ứng viên để kiểm chứng tiếp trên holdout mới; vẫn báo primary đã khóa và toàn bộ nhánh hiện tại.',
            'Không tách được đóng góp riêng của BM25, metadata và vai trò few-shot bằng lần chạy gộp này. Muốn kết luận riêng từng phần cần ablation được khóa trên dữ liệu phát triển.']
    lines+=['','## Calibration và tính hợp lệ','',
            f'Ngưỡng khóa từ 200 câu dev: {gate["selected_threshold"]}. Tune RS10={gate["tune_selected"]["scores"]["RS10"]:.2f}; audit 100 câu RS10={gate["audit_selected"]["scores"]["RS10"]:.2f}; audit chưa gate={gate["audit_ungated"]["scores"]["RS10"]:.2f}. Audit không dùng chọn ngưỡng.',
            'Kiểm tra chất lượng tín hiệu: '+gate['confidence_quality']['decision']+'. Logprob hằng số/thiếu không phân loại được rủi ro; gate bị tắt trong cấu hình hiện tại. Primary vì vậy trùng v2_verified; không tuyên bố tái hiện thành công ProbGate.',
            'Đã dừng lần khởi chạy đầu trước chấm gold test khi phát hiện tín hiệu suy biến trên dev; lần tiếp tục dùng lại cache API. Chi tiết trong resume_provenance.json. Quyết định tắt gate không dựa trên điểm test.',
            'Từng câu calibration bị loại chính ID và câu trùng nội dung khỏi ví dụ RAG. Final test dùng toàn bộ train+dev. Lưới ngưỡng, ID và hash nguồn được lưu trước chạy; ngưỡng không chọn theo gold test.',
            '**V2 được thiết kế sau khi xem lỗi test của v1: kết quả mang tính khám phá có tham khảo test. Cần holdout mới hoặc protocol độc lập để khẳng định cải thiện tổng quát.**',
            'Khác model fine-tuned và protocol knowledge với paper; so sánh này không tách riêng tác động phương pháp khỏi backbone.','',
            '## Tài nguyên và kiểm tra','',f'Runtime: {report["runtime"]}.',
            '13 kiểm tra tự động đã qua trước lần tiếp tục; bao gồm tín hiệu logprob hằng số, tự loại câu calibration, guard, quota và nguồn logprob sau sửa SQL.','']
    for phase,value in report['api_usage'].items():
        lines.append(f'- {phase}: {value["calls"]} calls; input {value["prompt_tokens"]:,}; output {value["completion_tokens"]:,}; failed attempts {value["failed_attempts"]}.')
    lines+=['',f'Review JSON lỗi hoặc không hoàn tất: {review_errors}; pipeline từ chối các câu này và vẫn giữ trong mẫu chấm. Không loại câu thất bại khỏi mẫu số.',
            'Không phát sinh model call để chạy lại tác giả/Vanna. Số dư trước/sau lưu riêng, không xem chênh số dư tài khoản là hóa đơn độc quyền của thí nghiệm. Các request được kế thừa cache vẫn tính trong tổng tài nguyên, không cộng thêm lần cũ một lần nữa.','',
            '## Bước tiếp theo','',
            'Dùng kết quả primary đã khóa để báo cáo, kèm EX/coverage và phân rã lỗi. Không chọn lại ngưỡng bằng lỗi test mới. Nếu tiếp tục cải thiện, dành dữ liệu chưa dùng để thiết kế và công bố rõ ngân sách suy luận.',
            'Đây là đánh giá English → SQL, không chứng minh SQL → câu trả lời tự nhiên hay độ an toàn lâm sàng.','']
    (directory/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    dump(ROOT/'STATUS.json',{'state':'complete','run':args.run_name,'completed_questions':1167,'runtime':report['runtime'],
                           'primary':primary,'report':str(directory/'FINAL_REPORT.md')})
    print(json.dumps({'primary':primary,'paired_deltas':comparisons,'usage':report['api_usage'],'validation':validations},indent=2))


if __name__=='__main__':
    main()
