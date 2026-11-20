"""Tuning-only: score the BIRD-description samples (descriptions_exp.py) against two no-description draws."""
import json, sys
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.argv=['x']
from v9_lab import _exec_job, groups_of, load_jsonl, db_file, LAB, DEV, OURS, tuning_ids
from compare_ours import compare
if __name__ == '__main__':
    gold = json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
    d = load_jsonl(LAB/'desc_samples_n8.jsonl')
    tasks = [(i, str(db_file(gold[i]['db_id'])), gold[i]['SQL'], [(f's{k+1}', s) for k, s in enumerate(d[i]['sqls'])]) for i in tuning_ids()]
    with ProcessPoolExecutor(8) as p: desc = dict(p.map(_exec_job, tasks, chunksize=4))
    (LAB/'desc_executions.json').write_text(json.dumps(desc))
    v8 = {int(k): v for k, v in json.loads((LAB/'executions_n8.json').read_text()).items()}
    v9 = {int(k): v for k, v in json.loads((OURS/'gpt-4o-mini-2024-07-18/v9/candidate_executions.json').read_text()).items()}
    maj = json.loads((OURS.parent/'gpt-4o-mini-2024-07-18/major_voting_score_per_question.json').read_text())
    ids = tuning_ids(); S = {f's{k}' for k in range(1, 9)}
    def stats(src):
        vote, per, orc = [0]*1534, 0, 0
        for i in ids:
            c = [x for x in src[i] if x['id'] in S]
            g = groups_of(c); vote[i] = int(bool(g) and g[0][0]['ok'])
            per += sum(x['ok'] for x in c) / 8; orc += any(x['ok'] for x in c)
        return vote, per, orc
    res = {}
    for name, src in (('no-desc draw A (v8 run)', v8), ('no-desc draw B (v9 run)', v9), ('WITH descriptions', desc)):
        vote, per, orc = stats(src); res[name] = vote
        print(f"{name:26s} vote {sum(vote[i] for i in ids)}/300  mean single-sample {per:.1f}/300  oracle {orc}/300")
    print('baseline majority-8 (tuning)', sum(maj[i] for i in ids))
    for k in ('no-desc draw A (v8 run)', 'no-desc draw B (v9 run)'):
        print('desc vs', k, compare(res['WITH descriptions'], res[k], ids))
