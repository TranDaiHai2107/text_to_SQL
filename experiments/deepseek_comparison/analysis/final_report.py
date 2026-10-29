"""Post-inference official scoring and descriptive analysis. Never calls an LLM."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]
OURS=ROOT.parent/'apply_my_work_to_baseline'
VANNA=ROOT.parent/'vanna_ehrsql'
BASELINE=WORKSPACE/'baselines/probgate_ehrsql_2024'
sys.path.insert(0,str(OURS))
from evaluate import paired_delta


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def hash_file(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def score_prediction(name,system,mode,source,use_docker):
    expected={r['id'] for r in load(BASELINE/'data/inputs/test.json')['data']}
    prediction=load(source)
    if set(prediction)!=expected or any(not isinstance(v,str) for v in prediction.values()):
        raise ValueError('Full test SQL predictions required')
    if use_docker:
        target=BASELINE/'runs'/('deepseek_verified_'+name)/system/mode
        target.mkdir(parents=True,exist_ok=True)
        output=target/'prediction.json'
        if output.exists() and output.read_bytes()!=source.read_bytes():
            raise ValueError('Refusing to overwrite another prediction')
        output.write_bytes(source.read_bytes())
        score_path=target/'scores.json'
        if not score_path.exists():
            relative=target.relative_to(BASELINE).as_posix()
            subprocess.run(['docker','compose','exec','-T','probgate-baseline','python','reproduce.py','score',
                            '--split','test','--scorer','official','--predictions',relative+'/prediction.json',
                            '--output',relative+'/scores.json'],cwd=WORKSPACE,check=True)
        result=load(score_path)
        if result['prediction_sha256']!=hash_file(source) or result['scorer']!='official':
            raise ValueError('Docker score provenance mismatch')
        return result,prediction,str(score_path)
    report=load(source.parent/'evaluation.json')
    if not report['full_benchmark_complete'] or not report['official_normalization']:
        raise ValueError('Full official report required')
    return report['variants'][mode],prediction,str(source.parent/'evaluation.json')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name',default='deepseek_flash_train_dev_20261028_v1')
    parser.add_argument('--docker',action='store_true')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}',args.run_name):
        parser.error('Invalid run name')
    directory=ROOT/'runs'/args.run_name
    comparison=load(directory/'comparison.json')
    if not comparison['full_test_complete']:
        raise ValueError('Final report cannot be produced from a partial run')
    gold=load(BASELINE/'data/gold/test/label.json')
    answerable={key for key,sql in gold.items() if sql!='null'}
    rows={}
    all_outcomes={}
    for system,root,modes in [('ours',OURS,['full_schema_rag','full_schema_rag_agentic','full_schema_rag_agentic_gef']),
                              ('vanna',VANNA,['vanna','vanna_gef'])]:
        host=load(root/'runs'/args.run_name/'evaluation.json')
        for mode in modes:
            result,prediction,source=score_prediction(args.run_name,system,mode,
                    root/'runs'/args.run_name/(mode+'.prediction.json'),args.docker)
            outcomes=result['per_question']
            if set(outcomes)!=set(gold):
                raise ValueError('Mismatched test IDs')
            correct_sql=sum(outcomes[key]=='correct' for key in answerable)
            false_abstain=sum(prediction[key]=='null' for key in answerable)
            false_answers=sum(prediction[key]!='null' for key in set(gold)-answerable)
            invalid_ids={e['id'] for e in result.get('execution_errors',[])}
            # An empty SQL marker is not a SELECT, even if sqlite.execute('')
            # returns an empty cursor. It still receives wrong RS/EX normally.
            invalid_ids.update(key for key,sql in prediction.items() if not sql.strip())
            nonnull={key for key,sql in prediction.items() if sql!='null'}
            rows[mode]={'system':system,'scores':result['scores'],
                        'EX':100*correct_sql/len(answerable),
                        'VSR':100*len(nonnull-invalid_ids)/len(gold),
                        'correct':result['correct'],'wrong':result['wrong'],
                        'correct_answerable':correct_sql,'false_abstentions':false_abstain,
                        'false_answers_on_unanswerable':false_answers,
                        'answer_precision':100*correct_sql/len(nonnull) if nonnull else None,
                        'coverage':100*len(nonnull)/len(gold),
                        'invalid_sql_count':len(invalid_ids),'source':source,
                        'host_score_delta':{k:result['scores'][k]-host['variants'][mode]['scores'][k] for k in result['scores']}}
            all_outcomes[mode]=outcomes
    paper_dir=BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef'
    paper=load(paper_dir/'scores_official.json')
    paper_pred=load(paper_dir/'prediction.json')
    paper_correct=sum(paper['per_question'][key]=='correct' for key in answerable)
    paper_nonnull=sum(sql!='null' for sql in paper_pred.values())
    rows['paper']={'system':'authors_cached_predictions','scores':paper['scores'],
                   'EX':100*paper_correct/len(answerable),
                   'VSR':100*(paper_nonnull-len(paper['execution_errors']))/len(gold),
                   'extra_metrics_note':'EX/VSR computed from released predictions; not claimed as published paper metrics.'}
    token_usage={}
    for system,root in [('ours',OURS),('vanna',VANNA)]:
        events=[json.loads(s) for s in (root/'runs'/args.run_name/'api_events.jsonl').read_text().splitlines()]
        success=[e for e in events if e['kind']=='success']
        token_usage[system]={'calls':len(success),**{k:sum(e['usage'].get(k,0) or 0 for e in success)
                  for k in ['prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']}}
    primary=rows['full_schema_rag_agentic_gef']
    report={'run':args.run_name,'questions':len(gold),'knowledge_questions':6287,
            'runtime':'Docker official scorer' if args.docker else 'Host official scorer',
            'rows':rows,'token_usage':token_usage,
            'ours_minus_paper':{k:primary['scores'][k]-paper['scores'][k] for k in paper['scores']},
            'paired_ours_minus_paper':paired_delta(paper['per_question'],all_outcomes['full_schema_rag_agentic_gef']),
            'paired_ours_minus_vanna':paired_delta(all_outcomes['vanna'],all_outcomes['full_schema_rag_agentic_gef']),
            'paired_ours_minus_vanna_gef':paired_delta(all_outcomes['vanna_gef'],all_outcomes['full_schema_rag_agentic_gef']),
            'analysis_code_sha256':hash_file(__file__),
            'limits':['Paper used a different fine-tuned model; this run also uses dev as knowledge.',
                      'The proposed system has extra dictionary retrieval and may use repair calls.',
                      'This evaluates English-to-SQL, not natural-language answer faithfulness or ASR.']}
    (directory/'FINAL_RESULTS.json').write_text(json.dumps(report,indent=2)+'\n')
    records=[json.loads(s) for s in (OURS/'runs'/args.run_name/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    problems=Counter()
    samples=[]
    for row in records:
        key=row['id']
        outcome=all_outcomes['full_schema_rag_agentic_gef'][key]
        if outcome=='correct':
            continue
        r=row['variants']['full_schema_rag_agentic_gef']
        category=('false_abstention' if outcome=='abstained_answerable' else
                  'false_answer_unanswerable' if key not in answerable else
                  'wrong_answer_executable' if r['execution']['valid'] else 'execution_failure')
        problems[category]+=1
        samples.append({'id':key,'category':category,'question':row['question'],'gold_sql':gold[key],'predicted_sql':r['sql']})
    (directory/'ERROR_CASES.json').write_text(json.dumps({'counts':problems,'cases':samples},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Kết quả cuối — DeepSeek Flash, train+dev knowledge, test EHRSQL','',
           f'Đủ {len(gold)} câu test. Runtime: {report["runtime"]}. Không fine-tune.',
           'Primary đã cố định trước: full_schema_rag_agentic_gef. Không chọn cấu hình theo điểm test.','',
           '## Đối chiếu chính','']
    for label,key in [('Hệ thống đề xuất','full_schema_rag_agentic_gef'),('Vanna','vanna'),('Vanna + GEF','vanna_gef'),('ProbGate paper (official replay)','paper')]:
        r=rows[key]
        lines.append(f'- **{label}**: RS0={r["scores"]["RS0"]:.2f}; RS5={r["scores"]["RS5"]:.2f}; RS10={r["scores"]["RS10"]:.2f}; RSN={r["scores"]["RSN"]:.2f}; EX={r["EX"]:.2f}%; VSR={r["VSR"]:.2f}%.')
    lines += ['', 'EX/VSR của paper được tính bổ sung từ cache, không gán là số paper đã công bố.',
              '', 'Chênh lệch RS10 hệ thống đề xuất so với paper: '+f'{report["ours_minus_paper"]["RS10"]:+.4f} điểm.',
              'Khoảng tin cậy paired 95%: '+str(report['paired_ours_minus_paper']['paired_bootstrap_95_percent_interval']),
              '', '## Các bước hậu xử lý', '']
    for key in ['full_schema_rag','full_schema_rag_agentic','full_schema_rag_agentic_gef']:
        r=rows[key]
        lines.append(f'- `{key}`: RS10={r["scores"]["RS10"]:.2f}; EX={r["EX"]:.2f}%; sai={r["wrong"]}; từ chối nhầm={r["false_abstentions"]}.')
    lines += ['', '## Tài nguyên', '', json.dumps(token_usage,indent=2), '', '## Phân rã lỗi primary', '',str(dict(problems)), '',
              '## Giới hạn và hướng cải thiện', '',
              '1. Ưu tiên giảm các câu sai vẫn thực thi được; VSR cao không đảm bảo EX hoặc RS10 cao.',
              '2. Dùng logprobs đã lưu để thiết kế bộ lọc rủi ro, nhưng chọn ngưỡng trên calibration tách khỏi knowledge. Dev hiện đã là knowledge, nên không dùng lại để đo calibration có self-retrieval.',
              '3. Kiểm tra trường hợp từ chối nhầm trước khi tăng mức lọc: RS10 và coverage có đánh đổi. Chi tiết SQL trong ERROR_CASES.json.',
              '4. Thí nghiệm tiếp theo nên có train-only knowledge và calibration riêng để đối chiếu gần điều kiện paper hơn.',
              '', 'Điểm so với paper là so hệ thống trong điều kiện khác model/fine-tuning và thêm dev knowledge. Các nhánh có thêm sửa lỗi/dictionary phải báo tài nguyên.',
              'Không dùng lỗi test để sửa rồi chọn điểm test tốt nhất. Các đề xuất là hướng nghiên cứu tiếp theo; giữ kết quả gốc này.', '']
    (directory/'FINAL_REPORT.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({'runtime':report['runtime'],'primary':primary,'paper':rows['paper'],
                      'token_usage':token_usage,'error_counts':problems},indent=2))


if __name__=='__main__':
    main()
