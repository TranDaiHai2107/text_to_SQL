"""Post-inference official scoring and complete, non-padded prediction exports."""
import json
import sqlite3
from infrastructure import BASELINE,DB,load,dump,execute_readonly,score_answers
from risk_v3 import select_record

MODES=['v3_direct','v3_structural','v3_plan','v3_selected']


def sql_answer(record):
    if record['sql']=='null':
        return 'null'
    if not record['sql'] or not record['execution']['valid']:
        return 'error_pred'
    try:
        return execute_readonly(record['sql'],DB,30)
    except Exception:
        return 'error_pred'


def candidate_answers(rows):
    return {row['id']:[sql_answer(r) for r in row['candidates']] for row in rows}


def api_usage(directory):
    path=directory/'api_events.jsonl'
    events=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []
    success=[e for e in events if e['kind']=='success']
    return {'calls':len(success),'failed_attempts':len(events)-len(success),
            **{key:sum(e['usage'].get(key,0) or 0 for e in success) for key in
               ['prompt_tokens','completion_tokens','total_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']}}


def evaluate(directory,rows,split,policy,*,expected_ids):
    ids={row['id'] for row in rows}
    if len(ids)!=len(rows) or ids!=set(expected_ids):
        raise ValueError('Full expected partition required; no missing rows or null padding')
    all_gold=load(BASELINE/'data/gold'/split/'answer.json')
    gold={key:all_gold[key] for key in ids}
    answers=candidate_answers(rows)
    selected={r['id']:select_record(r['candidates'],policy) for r in rows}
    variants={}
    for index,mode in enumerate(MODES):
        prediction={}
        sqls={}
        for row in rows:
            key=row['id']
            if mode=='v3_selected':
                chosen=selected[key]
                ci=chosen['selected_candidate_index']
                prediction[key]='null' if ci is None else answers[key][ci]
                sqls[key]=chosen['sql']
            else:
                prediction[key]=answers[key][index]
                sqls[key]=row['candidates'][index]['sql']
        metric=score_answers(gold,prediction,'official')
        answerable={key for key in ids if gold[key]!='null'}
        unanswerable=ids-answerable
        answered={key for key in ids if sqls[key]!='null'}
        correct_sql=sum(metric['per_question'][key]=='correct' for key in answerable)
        metric.update(EX=100*correct_sql/len(answerable) if answerable else None,
                      VSR=100*sum(isinstance(v,list) for v in prediction.values())/len(ids),
                      correct_answerable_sql=correct_sql,false_abstentions=sum(sqls[k]=='null' for k in answerable),
                      false_answers_on_unanswerable=sum(sqls[k]!='null' for k in unanswerable),
                      coverage=100*len(answered)/len(ids),
                      answer_precision=100*correct_sql/len(answered) if answered else None)
        variants[mode]=metric
        dump(directory/(mode+'.prediction.json'),sqls)
    result={'split':split,'completed_questions':len(rows),'full_expected_partition_complete':True,
            'full_benchmark_complete':split=='test' and len(rows)==1167,
            'selected_policy':policy,'primary_variant':'v3_selected','primary_metric':'RS10',
            'runtime_sqlite':sqlite3.sqlite_version,'variants':variants,'api_usage':api_usage(directory)}
    dump(directory/'evaluation.json',result)
    dump(directory/'selection.json',{key:{'selected_candidate_index':record['selected_candidate_index'],
                                          'selection':record['selection']} for key,record in selected.items()})
    return result
