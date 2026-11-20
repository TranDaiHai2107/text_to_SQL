"""Number of output columns of gold and v8-lab candidates (tuning) -> v9_lab/ncols.json (column-count error analysis)."""
import json, sqlite3, time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
LAB=ROOT/'results/omnisql/ours/v9_lab'
DEV=ROOT/'data/benchmarks/bird/dev_20240627'
def nc(db,sql):
    con=sqlite3.connect(f'file:{db}?mode=ro',uri=True); t=time.monotonic()
    con.set_progress_handler(lambda: 1 if time.monotonic()-t>20 else 0, 10000)
    try:
        cur=con.execute(sql); return len(cur.description or [])
    except Exception: return None
    finally: con.close()
def job(a):
    i,db,gold,c=a
    return i,{'gold':nc(db,gold),**{x['id']:nc(db,x['sql']) if x['sql'] else None for x in c}}
if __name__=='__main__':
    ex=json.loads((LAB/'executions_n8.json').read_text())
    g=json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
    t=[(int(i),str(DEV/'dev_databases'/g[int(i)]['db_id']/(g[int(i)]['db_id']+'.sqlite')),g[int(i)]['SQL'],c) for i,c in ex.items()]
    with ProcessPoolExecutor(8) as p: r=dict(p.map(job,t,chunksize=4))
    (LAB/'ncols.json').write_text(json.dumps(r)); print('ok')
