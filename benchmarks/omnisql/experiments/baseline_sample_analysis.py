"""Execute the baseline greedy + 8 majority samples on all dev (set compare, timeout 60) -> baseline_sample_analysis.json."""
import json, sqlite3, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
DEV = ROOT/'data/benchmarks/bird/dev_20240627'
B = ROOT/'results/omnisql/gpt-4o-mini-2024-07-18'

def run(db, sql, limit=60):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    t0 = time.monotonic()
    con.set_progress_handler(lambda: 1 if time.monotonic()-t0 > limit else 0, 10000)
    try:
        r = frozenset(con.execute(sql).fetchall()); return r, time.monotonic()-t0, None
    except Exception as e:
        return None, time.monotonic()-t0, ('timeout' if time.monotonic()-t0 > limit else 'error')
    finally:
        con.close()

def job(a):
    i, db, gold, greedy, samples = a
    g, gt, _ = run(db, gold)
    out = {'gold_t': gt, 'gold_ok': g is not None}
    def ev(sql):
        r, t, err = run(db, sql)
        return {'fp': hash(r) if r is not None else None, 'ok': (g is not None and r is not None and r == g), 't': round(t,2), 'err': err}
    out['greedy'] = ev(greedy)
    out['samples'] = [ev(s) for s in samples]
    return i, out

if __name__ == '__main__':
    gold = json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
    gr = json.loads((B/'greedy_search.json').read_text(encoding='utf-8'))
    mj = json.loads((B/'major_voting.json').read_text(encoding='utf-8'))
    tasks = [(i, str(DEV/'dev_databases'/g['db_id']/f"{g['db_id']}.sqlite"), g['SQL'], gr[i]['pred_sqls'][0], mj[i]['pred_sqls']) for i, g in enumerate(gold)]
    res = {}
    with ProcessPoolExecutor(8) as ex:
        for i, o in ex.map(job, tasks, chunksize=8): res[i] = o
    (B/'baseline_sample_analysis.json').write_text(json.dumps(res), encoding='utf-8')
    print('done')
