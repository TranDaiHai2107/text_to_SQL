"""Oracle analysis of v8 candidates: how often is ANY candidate correct (set-equality like evaluate_bird)."""
import json, sqlite3, time, sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'data/benchmarks/bird/dev_20240627'
OUT = ROOT/'results/omnisql/ours/gpt-4o-mini-2024-07-18/v8'

def run(db, sql, limit=30):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    t0 = time.monotonic()
    con.set_progress_handler(lambda: 1 if time.monotonic()-t0 > limit else 0, 10000)
    try:
        return frozenset(con.execute(sql).fetchall())
    except Exception:
        return None
    finally:
        con.close()

def job(args):
    i, db, gold, cands = args
    g = run(db, gold, 60)
    out = {}
    seen = {}
    for cid, sql in cands:
        if not sql: out[cid] = False; continue
        if sql not in seen:
            r = run(db, sql)
            seen[sql] = (g is not None and r is not None and set(r) == set(g))
        out[cid] = seen[sql]
    return i, out

if __name__ == '__main__':
    gold = json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
    rows = {}
    for line in (OUT/'predictions.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line); rows[r['row_index']] = r
    tasks = []
    for i, g in enumerate(gold):
        db = DEV/'dev_databases'/g['db_id']/f"{g['db_id']}.sqlite"
        tasks.append((i, str(db), g['SQL'], [(c['id'], c['sql']) for c in rows[i]['candidates']]))
    res = {}
    with ProcessPoolExecutor(8) as ex:
        for i, out in ex.map(job, tasks, chunksize=8):
            res[i] = out
    (OUT/'oracle_candidates.json').write_text(json.dumps(res), encoding='utf-8')
    print('done', len(res))
