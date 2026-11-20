"""Tuning-only: (1) repair every error/empty sample before the vote; (2) column-alignment rule prompt."""
import json, sys, threading
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CMD = sys.argv[1] if len(sys.argv) > 1 else ''; sys.argv = sys.argv[:1]
from v9_lab import context, chat, tuning_ids, load_jsonl, LAB, DEV, OURS, ROOT, _exec_job, groups_of, db_file
from ehrqa.bird.ours_v8 import parse_sql, repair_prompt
from compare_ours import compare

RULE = ("- Column alignment: list the items the question asks for and return exactly one column per item, in the "
        "order the question mentions them. Do not add columns that were only used to filter, sort, rank or join "
        "(for example the count or score used in ORDER BY) unless the question also asks for that value. If the "
        "question asks for several items (for example 'name and address' or 'list X along with Y'), return all of them.\n")
ANCHOR = '- Before generating the final SQL query'
OUT = LAB / 'fix_exp'; OUT.mkdir(exist_ok=True)
EMPTY = 'The query executed but returned no rows (or only NULL values).'

def sources():
    v9 = load_jsonl(OURS/'gpt-4o-mini-2024-07-18/v9/predictions.jsonl')
    v8 = load_jsonl(OURS/'gpt-4o-mini-2024-07-18/v8/predictions.jsonl')
    base = {r['row_index']: r for r in json.loads((ROOT/'results/omnisql/gpt-4o-mini-2024-07-18/major_voting.json').read_text(encoding='utf-8'))}
    pick = lambda rows: {i: [c['sql'] for c in rows[i]['candidates'] if c['id'] in {f's{k}' for k in range(1, 9)}] for i in tuning_ids()}
    src = {'ours_A_v9': pick(v9), 'ours_B_v8': pick(v8), 'base': {i: base[i]['pred_sqls'] for i in tuning_ids()}}
    col = load_jsonl(OUT/'colrule_samples.jsonl')
    if col: src['ours_colrule'] = {i: col[i]['sqls'] for i in tuning_ids() if i in col}
    return src

def main():
    gold, database, enriched = context()
    prompts = json.loads((ROOT/'data/benchmarks/bird/omnisql_dev_bird.json').read_text(encoding='utf-8'))
    def prompt_for(name, i):
        if name == 'base': return prompts[i]['input_seq']
        p = enriched(i)
        return p.replace(ANCHOR, RULE + ANCHOR, 1) if name == 'ours_colrule' else p
    if CMD == 'gen':
        out = OUT/'colrule_samples.jsonl'; done = load_jsonl(out); model, tr = chat(1.2); lock = threading.Lock()
        assert ANCHOR in enriched(tuning_ids()[0])
        def run(i):
            r = model.sample_text('generate_samples', [{'role': 'user', 'content': prompt_for('ours_colrule', i)}], 2048, n=8, temperature=0.8)
            with lock, out.open('a', encoding='utf-8') as f:
                f.write(json.dumps({'row_index': i, 'sqls': [parse_sql(t) for t in r['contents']]}, ensure_ascii=False) + '\n')
        with ThreadPoolExecutor(8) as p: list(p.map(run, [i for i in tuning_ids() if i not in done]))
        print('gen usd', round(tr.spent, 4)); return
    if CMD == 'repair':
        model, tr = chat(1.0); lock = threading.Lock()
        for name, src in sources().items():
            out = OUT/f'repair_{name}.jsonl'; done = load_jsonl(out)
            def run(i):
                db, fixed, n = database(i), [], 0
                for sql in src[i]:
                    fb = None
                    if not sql: fb = 'No SQL query was found in the answer.'
                    else:
                        try:
                            res = db.execute(sql)
                            if not any(v is not None for r in res.rows for v in r): fb = EMPTY
                        except ValueError as e: fb = str(e)[:500]
                    if fb is None: fixed.append(sql); continue
                    text = model.complete_text('repair', [{'role': 'user', 'content': repair_prompt(prompt_for(name, i), sql or '', fb)}], 2048)['content']
                    fixed.append(parse_sql(text) or sql); n += 1
                with lock, out.open('a', encoding='utf-8') as f:
                    f.write(json.dumps({'row_index': i, 'sqls': fixed, 'repairs': n}, ensure_ascii=False) + '\n')
            with ThreadPoolExecutor(8) as p: list(p.map(run, [i for i in tuning_ids() if i not in done]))
            print(name, 'repairs', sum(r['repairs'] for r in load_jsonl(out).values()), 'usd so far', round(tr.spent, 4))
        return

if __name__ == '__main__':
    main() if CMD in ('gen', 'repair') else None
    if CMD == 'eval':
        gold = json.loads((DEV/'dev.json').read_text(encoding='utf-8'))
        src = sources()
        for name in list(src):
            rep = load_jsonl(OUT/f'repair_{name}.jsonl')
            if rep: src[name + '+repair'] = {i: rep[i]['sqls'] for i in rep}
        tasks = [(f'{name}|{i}', str(db_file(gold[i]['db_id'])), gold[i]['SQL'], [(f's{k+1}', s) for k, s in enumerate(sqls)])
                 for name, s in src.items() for i, sqls in s.items()]
        with ProcessPoolExecutor(8) as p: ex = dict(p.map(_exec_job, tasks, chunksize=8))
        ids = tuning_ids(); votes = {}
        import statistics
        for name in src:
            v = [0]*1534; per = 0; bad = 0
            for i in ids:
                c = ex[f'{name}|{i}']; g = groups_of(c); v[i] = int(bool(g) and g[0][0]['ok'])
                per += sum(x['ok'] for x in c)/len(c); bad += sum(x['fp'] is None or not x['values'] for x in c)
            votes[name] = v
            print(f"{name:24s} vote {sum(v[i] for i in ids)}/300  mean-sample {per:.1f}  bad samples {bad}")
        pairs = [('ours_A_v9+repair', 'ours_A_v9'), ('ours_B_v8+repair', 'ours_B_v8'), ('base+repair', 'base'),
                 ('ours_colrule', 'ours_A_v9'), ('ours_colrule', 'ours_B_v8'), ('ours_colrule+repair', 'ours_A_v9+repair'),
                 ('ours_colrule+repair', 'base+repair'), ('ours_A_v9+repair', 'base+repair')]
        for a, b in pairs:
            if a in votes and b in votes:
                r = compare(votes[a], votes[b], ids); print(f'{a} vs {b}: {r["ours_only"]}/{r["base_only"]} p={r["mcnemar_p"]:.3f}')
        (OUT/'tuning_votes.json').write_text(json.dumps({k: [v[i] for i in ids] for k, v in votes.items()}))
