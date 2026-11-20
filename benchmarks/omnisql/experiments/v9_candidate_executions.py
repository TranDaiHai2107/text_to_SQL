"""Execute every v9 candidate (g, s1..s8, p1..p8, gr) on all dev -> v9/candidate_executions.json (equal-budget analysis)."""
import json, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.argv=['x']
from v9_lab import _exec_job, load_jsonl, db_file, DEV, OURS
R = OURS/'gpt-4o-mini-2024-07-18'/'v9'
if __name__ == '__main__':
    gold = json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
    rows = load_jsonl(R/'predictions.jsonl')
    tasks = [(i, str(db_file(gold[i]['db_id'])), gold[i]['SQL'], [(c['id'], c['sql']) for c in rows[i]['candidates']]) for i in range(len(gold))]
    with ProcessPoolExecutor(8) as p: res = dict(p.map(_exec_job, tasks, chunksize=4))
    (R/'candidate_executions.json').write_text(json.dumps(res), encoding='utf-8'); print('ok', len(res))
