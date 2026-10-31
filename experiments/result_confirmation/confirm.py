"""Re-execute frozen predictions on the existing EHRSQL test; no model calls."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parents[1]
BASELINE = WORKSPACE / 'baselines/probgate_ehrsql_2024'
EXPERIMENTS = ROOT.parent
sys.path.insert(1, str(BASELINE))
from baseline_core import execute_readonly, score_answers


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    lock = load(EXPERIMENTS/'research_validation/V5_LOCK.json')
    for relative, digest in lock['files'].items():
        if sha(WORKSPACE/relative) != digest:
            raise ValueError('Frozen source changed: '+relative)
    manifest = load(BASELINE/'source_manifest.json')
    db = BASELINE/manifest['database_path']
    inputs = load(BASELINE/'data/inputs/test.json')['data']
    gold = load(BASELINE/'data/gold/test/answer.json')
    labels = load(BASELINE/'data/gold/test/label.json')
    expected = {r['id'] for r in inputs}
    if len(inputs)!=1167 or len(expected)!=1167 or set(gold)!=expected or set(labels)!=expected:
        raise ValueError('Exact original 1167-question test required')
    answerable = {k for k in gold if gold[k]!='null'}
    if len(answerable)!=934 or {k for k in labels if labels[k]!='null'}!=answerable:
        raise ValueError('Original answerability partition differs')
    v5 = EXPERIMENTS/'ours_improved_v5/runs/deepseek_flash_v5_20261029_r1'
    vanna = EXPERIMENTS/'vanna_ehrsql/runs/deepseek_flash_train_dev_20261028_v1'
    paper = BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef'
    vanna_eval = load(vanna/'evaluation.json')
    vanna_records = [json.loads(line) for line in (vanna/'records.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(vanna_records)!=1167 or {r['id'] for r in vanna_records}!=expected:
        raise ValueError('Vanna generation incomplete or duplicated')
    sources = {
        'V5': (v5/'test/v5_selected.prediction.json', load(v5/'test/evaluation.json')['variants']['v5_selected']),
        'Vanna': (vanna/'vanna.prediction.json', vanna_eval['variants']['vanna']),
        'Vanna_GEF': (vanna/'vanna_gef.prediction.json', vanna_eval['variants']['vanna_gef']),
        'ProbGate_paper_cache': (paper/'prediction.json', load(paper/'scores_official.json')),
    }
    answer_cache = {}
    results = {}
    started = time.monotonic()
    for name, (source, previous) in sources.items():
        sqls = load(source)
        if set(sqls)!=expected or any(not isinstance(s,str) for s in sqls.values()):
            raise ValueError('Wrong prediction mapping: '+name)
        if name.startswith('Vanna'):
            variant = 'vanna' if name=='Vanna' else 'vanna_gef'
            def exported_sql(record):
                # Match the frozen evaluator's export contract: invalid SQL is
                # exported as an empty string and remains WRONG, never null.
                if record.get('gef_filtered') or record['execution']['abstained']:
                    return 'null'
                return record['sql'] if record['execution']['valid'] else ''
            if any(sqls[r['id']]!=exported_sql(r['variants'][variant]) for r in vanna_records):
                raise ValueError('Vanna export differs from generated records')
        predicted = {}
        errors = 0
        for key, sql in sqls.items():
            if sql=='null':
                predicted[key] = 'null'
                continue
            if not sql.strip():
                # SQLite accepts an empty statement and returns [], but that
                # is not successfully executed SQL under the export contract.
                predicted[key] = 'error_pred'
                errors += 1
                continue
            if sql not in answer_cache:
                try:
                    answer_cache[sql] = execute_readonly(sql,db,30)
                except Exception:
                    answer_cache[sql] = 'error_pred'
            predicted[key] = answer_cache[sql]
            errors += predicted[key]=='error_pred'
        score = score_answers(gold,predicted,'official')
        if score['per_question']!=previous['per_question'] or score['scores']!=previous['scores']:
            raise ValueError('Fresh execution does not match historical result: '+name)
        nonnull = {k for k in sqls if sqls[k]!='null'}
        correct_sql = sum(score['per_question'][k]=='correct' for k in answerable)
        entry = {k:v for k,v in score.items() if k!='per_question'}
        entry.update(EX=100*correct_sql/len(answerable),
                     VSR=100*(len(nonnull)-errors)/len(inputs),
                     coverage=100*len(nonnull)/len(inputs),
                     answer_precision=100*correct_sql/len(nonnull) if nonnull else None,
                     correct_answerable_sql=correct_sql,
                     correct_abstentions=score['correct']-correct_sql,
                     execution_errors=errors,
                     matches_historical_per_question=True,
                     prediction_source=str(source.relative_to(WORKSPACE)),
                     prediction_sha256=sha(source))
        previous_ex = previous.get('EX', previous.get('answerable_ex'))
        previous_vsr = previous.get('VSR', previous.get('vsr_all_questions'))
        if (previous_ex is not None and abs(entry['EX']-previous_ex)>1e-10) or (
                previous_vsr is not None and abs(entry['VSR']-previous_vsr)>1e-10):
            raise ValueError('Fresh EX/VSR differs from stored result: '+name)
        if name=='ProbGate_paper_cache':
            targets={'RS0':81.92,'RS5':78.06,'RS10':74.21,'RSN':-818.08}
            if any(round(score['scores'][k],2)!=v for k,v in targets.items()):
                raise ValueError('Paper scores do not reproduce published two-decimal values')
            entry.update(published_RS_match=True, EX_and_VSR_computed_from_released_cache_not_published_columns=True)
        results[name] = entry
        print(name,entry['scores'],'EX',entry['EX'],'VSR',entry['VSR'],flush=True)
    report={'state':'existing_results_numerically_confirmed', 'date':'2026-10-29',
            'questions':1167, 'answerable':934, 'unanswerable':233,
            'scope':'Existing English-to-SQL benchmark only; no new dataset or translation evaluation',
            'new_model_API_calls':0, 'frozen_source_files_verified':len(lock['files']),
            'database_sha256':sha(db), 'scorer_sha256':sha(BASELINE/'baseline_core.py'),
            'runtime':{'execution':'fresh host execution with official scorer', 'sqlite':sqlite3.sqlite_version,
                       'fresh_Docker_execution':False,
                       'note':'Docker daemon unavailable this session. V5 and paper have previous Docker-verified scores; fresh host per-question results match those stored results.'},
            'systems':results, 'elapsed_seconds':time.monotonic()-started,
            'research_superiority_proven':False,
            'research_note':'Test-informed V5 development, unequal inference budgets/backbones versus references; this audit verifies numbers, not independent generalization or causal method superiority.'}
    ROOT.mkdir(exist_ok=True)
    (ROOT/'CONFIRMED_RESULTS.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    lines=['# Xác nhận kết quả hiện tại — EHRSQL 2024', '',
           'Đã thực thi lại prediction của cả bốn nhánh trên cùng 1.167 câu test, 934 answerable và 233 unanswerable, cùng SQLite database và official scorer. Từng nhãn chấm của cả bốn nhánh khớp kết quả đã lưu. Không gọi lại model/API, không sửa V5 hoặc gold.', '',
           '## Kết quả đã xác nhận', '']
    for name, r in results.items():
        s=r['scores']
        lines.append(f"- **{name}**: RS0={s['RS0']:.2f}; RS5={s['RS5']:.2f}; RS10={s['RS10']:.2f}; RSN={s['RSN']:.2f}; EX={r['EX']:.2f}%; VSR={r['VSR']:.2f}%; sai={r['wrong']}.")
    lines += ['', 'RS là metric paper. EX tính trên 934 câu answerable; VSR tính SQL thực thi thành công trên toàn bộ 1.167 câu. EX/VSR của paper được tính bổ sung từ prediction tác giả phát hành, không phải hai cột công bố trong paper.', '',
              'Paper là replay prediction tác giả, chưa chạy lại model tác giả. Vanna là cấu hình legacy SQL/RAG trong Vanna 2.0.2, dùng DeepSeek Flash và train+dev làm knowledge. V5 cũng dùng DeepSeek Flash, nhưng có ba nhánh generation/selection nên chưa phải đối chứng cùng ngân sách.', '',
              '## Kết luận đúng phạm vi', '',
              'Có thể xác nhận các số trên là kết quả đo được của cấu hình hiện tại. V5 nhỉnh hơn ProbGate về RS10 quan sát và cao hơn Vanna trong cấu hình đã chạy. Paper vẫn ít câu trả lời sai hơn và có RSN tốt hơn. Chưa chứng minh ưu thế phương pháp hay tổng quát hóa độc lập.', '',
              'V5 giữ nguyên làm bản chốt. Mở rộng database/dữ liệu, chuyển ngữ và xác nhận độc lập để bước tiếp theo theo yêu cầu của người dùng. Kết quả này chỉ English→SQL, không đánh giá ASR hoặc SQL→text.', '',
              'Lần kiểm tra này chạy official scorer trên host. Docker daemon hiện chưa chạy nên không gán nhãn fresh Docker verified cho cả bốn nhánh; V5/paper có đối soát Docker từ vòng trước và kết quả fresh host khớp từng câu.', '',
              '[Paper ProbGate](https://aclanthology.org/2024.clinicalnlp-1.65/). Chi tiết hash/provenance: `CONFIRMED_RESULTS.json`.', '']
    (ROOT/'RESULTS_VI.md').write_text('\n'.join(lines),encoding='utf-8')
    return report


if __name__=='__main__':
    main()
