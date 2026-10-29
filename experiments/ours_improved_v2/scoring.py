"""Official EHRSQL scoring; evaluation labels are accessed after inference."""
import json
import sqlite3
from common import BASELINE,DB,load,dump,execute_readonly,post_process_sql,score_answers
from evaluate import scoring_sql,reliability_diagnostics,paired_delta


def answers(rows,mode):
    result={}
    for row in rows:
        record=row['variants'][mode]
        sql=scoring_sql(record)
        if sql=='null':
            result[row['id']]='null'
        elif not sql:
            result[row['id']]='error_pred'
        else:
            try:
                result[row['id']]=execute_readonly(post_process_sql(sql),DB,30)
            except Exception:
                result[row['id']]='error_pred'
    return result


def score_records(directory,rows,split,modes):
    if len({r['id'] for r in rows})!=len(rows):
        raise ValueError('Duplicate evaluated question IDs')
    all_gold=load(BASELINE/'data/gold'/split/'answer.json')
    gold={r['id']:all_gold[r['id']] for r in rows}
    variants={}
    for mode in modes:
        predicted=answers(rows,mode)
        metric=score_answers(gold,predicted,'official')
        denominator=sum(v!='null' for v in gold.values())
        metric.update(answerable_ex=100*sum(metric['per_question'][key]=='correct' for key in gold if gold[key]!='null')/denominator,
                      answerable_ex_denominator=denominator,
                      vsr_all_questions=100*sum(isinstance(v,list) for v in predicted.values())/len(rows),
                      reliability=reliability_diagnostics(gold,predicted,metric['per_question']))
        variants[mode]=metric
        dump(directory/(mode+'.prediction.json'),{r['id']:scoring_sql(r['variants'][mode]) for r in rows})
    events_path=directory/'api_events.jsonl'
    events=[json.loads(x) for x in events_path.read_text(encoding='utf-8').splitlines()] if events_path.exists() else []
    success=[e for e in events if e['kind']=='success']
    report={'split':split,'completed_questions':len(rows),'full_benchmark_complete':split=='test' and len(rows)==1167,
            'primary_variant':'v2_calibrated','primary_metric':'RS10','runtime_sqlite':sqlite3.sqlite_version,
            'variants':variants,'successful_api_calls':len(success),
            'api_usage':{key:sum(e['usage'].get(key,0) or 0 for e in success) for key in ['prompt_tokens','completion_tokens','total_tokens']}}
    dump(directory/'evaluation.json',report)
    return report
