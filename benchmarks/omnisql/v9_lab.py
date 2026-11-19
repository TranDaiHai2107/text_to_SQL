"""v9 design experiments on the 300-question tuning split only (held-out rows are refused).

Reuses the v8 candidates (greedy, 8 baseline-prompt samples, repair) already generated for
these rows and adds only the new v9 parts, so each design choice costs a fraction of a run:

  gen     plan-prompt samples (n per question, one request each)       -> plan_samples.jsonl
  exec    execute every candidate and the gold SQL locally              -> executions.json
  eval    EX of vote configurations (local set comparison = BIRD EX)
  select  margin-gated LLM selector on the vote's top groups            -> select_<tag>.jsonl

Gold SQL is used only by ``exec`` to score locally; it never reaches a prompt.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

from verify_assets import DATA, ROOT

sys.path.insert(0, str(ROOT / 'src'))
from ehrqa.bird.ours_v8 import enrich_prompt, parse_sql  # noqa: E402
from ehrqa.bird.ours_v9 import (V9Config, needs_selection, parse_choice, plan_prompt,  # noqa: E402
                                select_prompt, set_fingerprint)

DEV = DATA / 'dev_20240627'
OURS = ROOT / 'results' / 'omnisql' / 'ours'
V8 = OURS / 'gpt-4o-mini-2024-07-18' / 'v8'
LAB = OURS / 'v9_lab'
MODEL = 'gpt-4o-mini-2024-07-18'


def tuning_ids() -> list[int]:
    return [int(x) for x in (OURS / 'tuning_ids.txt').read_text().split()]


def load_jsonl(path: Path) -> dict[int, dict]:
    rows = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            rows[row['row_index']] = row
    return rows


def db_file(db_id: str) -> Path:
    return DEV / 'dev_databases' / db_id / f'{db_id}.sqlite'


def context():
    from ehrqa.bird.database import BirdDatabase
    from ehrqa.bird.fewshot import TrainExamples
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
    examples = TrainExamples(DATA / 'bird_train.json', gold)
    databases, lock = {}, threading.Lock()

    def database(i):
        db_id = gold[i]['db_id']
        with lock:
            if db_id not in databases:
                databases[db_id] = BirdDatabase(db_file(db_id), prompts[i]['input_seq'],
                                                value_index_dir=DATA / 'ours_value_index')
            return databases[db_id]

    def enriched(i):
        cfg = V9Config()
        text = gold[i]['question'] + ' ' + (gold[i]['evidence'] or '')
        values = database(i).catalog_search(text, [])[:cfg.max_value_hints]
        return enrich_prompt(prompts[i]['input_seq'], values, examples(text)['items'])

    return gold, database, enriched


def chat(max_usd: float):
    from dotenv import load_dotenv
    from ehrqa.bird.model import ChatModel, SpendTracker
    load_dotenv(ROOT / '.env', override=False)
    if not os.getenv('OPENAI_API_KEY'):
        raise SystemExit('OPENAI_API_KEY is missing')
    tracker = SpendTracker(max_usd)
    return ChatModel(MODEL, tracker), tracker


def cmd_gen(args):
    gold, _, enriched = context()
    out = LAB / f'plan_samples_n{args.n}.jsonl'
    done = load_jsonl(out)
    targets = [i for i in tuning_ids() if i not in done]
    model, tracker = chat(args.max_usd)
    lock = threading.Lock()

    def run(i):
        result = model.sample_text('generate_plan_samples', [{'role': 'user', 'content': plan_prompt(enriched(i))}],
                                   2048, n=args.n, temperature=0.8)
        row = {'row_index': i, 'sqls': [parse_sql(t) for t in result['contents']], 'usd': result['usd'],
               'finish_reasons': result['finish_reasons'], 'outputs': result['contents']}
        with lock, out.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, targets))
    print(json.dumps({'generated': len(targets), 'usd': round(tracker.spent, 4)}))


def _run(db, sql, limit=60):
    con = sqlite3.connect(f'file:{db}?mode=ro', uri=True)
    start = time.monotonic()
    con.set_progress_handler(lambda: 1 if time.monotonic() - start > limit else 0, 10000)
    try:
        return con.execute(sql).fetchall()
    except Exception:
        return None
    finally:
        con.close()


def _exec_job(task):
    i, db, gold_sql, cands = task
    gold_rows = _run(db, gold_sql)
    gold_set = set(gold_rows) if gold_rows is not None else None
    out, seen = [], {}
    for cid, sql in cands:
        if sql not in seen:
            rows = _run(db, sql) if sql else None
            seen[sql] = None if rows is None else {
                'fp': set_fingerprint(rows), 'values': any(v is not None for r in rows for v in r),
                'ok': gold_set is not None and set(rows) == gold_set}
        out.append({'id': cid, 'sql': sql, **(seen[sql] or {'fp': None, 'values': False, 'ok': False})})
    return i, out


def cmd_exec(args):
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    v8 = load_jsonl(V8 / 'predictions.jsonl')
    plan = load_jsonl(LAB / f'plan_samples_n{args.n}.jsonl')
    tasks = []
    for i in tuning_ids():
        base = [(c['id'], c['sql']) for c in v8[i]['candidates']]
        order = [c for c in base if c[0] != 'gr'] + [(f'p{k + 1}', s) for k, s in enumerate(plan.get(i, {}).get('sqls', []))]
        order += [c for c in base if c[0] == 'gr']
        tasks.append((i, str(db_file(gold[i]['db_id'])), gold[i]['SQL'], order))
    with ProcessPoolExecutor(8) as pool:
        result = dict(pool.map(_exec_job, tasks, chunksize=4))
    (LAB / f'executions_n{args.n}.json').write_text(json.dumps(result), encoding='utf-8')
    print('executed', len(result))


def lab_candidates(row, *, base: int, plan: int, repair: bool = True):
    keep = {'g'} | {f's{k}' for k in range(1, base + 1)} | {f'p{k}' for k in range(1, plan + 1)}
    if repair:
        keep.add('gr')
    return [c for c in row if c['id'] in keep]


def groups_of(cands):
    """Same rule as ours_v9.vote_groups, on precomputed fingerprints."""
    groups = {}
    executed = [c for c in cands if c['fp'] is not None]
    pool = [c for c in executed if c['values']] or executed
    for c in pool:
        groups.setdefault(c['fp'], []).append(c)
    return sorted(groups.values(), key=len, reverse=True)


def cmd_eval(args):
    ex = {int(k): v for k, v in json.loads((LAB / f'executions_n{args.n}.json').read_text()).items()}
    v8_score = json.loads((V8 / 'greedy_search_score_per_question.json').read_text())
    maj = json.loads((ROOT / 'results/omnisql' / MODEL / 'major_voting_score_per_question.json').read_text())
    ids = sorted(ex)
    print(f"rows {len(ids)}  v8 official {sum(v8_score[i] for i in ids)}  baseline majority {sum(maj[i] for i in ids)}")
    for base, plan in [(8, 0), (8, 4), (8, 8), (4, 4), (0, 8)]:
        correct = oracle = undecided = 0
        for i in ids:
            g = groups_of(lab_candidates(ex[i], base=base, plan=plan))
            correct += bool(g) and g[0][0]['ok']
            oracle += any(c['ok'] for c in lab_candidates(ex[i], base=base, plan=plan))
            undecided += needs_selection(g, args.select_below)
        print(f'base {base} plan {plan}: vote {correct}  oracle {oracle}  selector-triggered {undecided}')


def cmd_select(args):
    gold, database, enriched = context()
    ex = {int(k): v for k, v in json.loads((LAB / f'executions_n{args.n}.json').read_text()).items()}
    out = LAB / f'select_{args.tag}.jsonl'
    done = load_jsonl(out)
    model, tracker = chat(args.max_usd)
    lock = threading.Lock()
    jobs = []
    for i in sorted(ex):
        g = groups_of(lab_candidates(ex[i], base=args.base, plan=args.plan))
        if needs_selection(g, args.select_below) and i not in done:
            top = g[:2] if args.mode == 'pair' else g[:args.groups]
            jobs.append((i, [grp[0] for grp in top], [len(grp) for grp in top]))

    def ask(prompt, ids, n=1):
        messages = [{'role': 'user', 'content': prompt}]
        if n == 1:
            texts = [model.complete_text('select', messages, 2048)['content']]
        else:
            texts = model.sample_text('select', messages, 2048, n=n, temperature=0.8)['contents']
        votes = [parse_choice(t, ids) for t in texts]
        return votes, texts

    def run(job):
        i, reps, sizes = job
        db = database(i)
        options = []
        for k, c in enumerate(reps):
            result = db.execute(c['sql'])
            options.append({'id': str(k + 1), 'sql': c['sql'], 'rows': result.rows, 'columns': result.columns})
            if args.mode == 'support':
                options[-1]['support'] = f'{sizes[k]} of {sum(sizes)}'
        ids = [o['id'] for o in options]
        if args.mode == 'pair':  # top-2 in both orders; switch only if both prefer the runner-up
            a, b = options[0], options[1]
            v1, t1 = ask(select_prompt(enriched(i), [{**a, 'id': '1'}, {**b, 'id': '2'}]), ['1', '2'])
            v2, t2 = ask(select_prompt(enriched(i), [{**b, 'id': '1'}, {**a, 'id': '2'}]), ['1', '2'])
            choice = '2' if v1[0] == '2' and v2[0] == '1' else '1'
            texts = t1 + t2
        else:
            votes, texts = ask(select_prompt(enriched(i), options), ids, n=5 if args.mode == 'sc5' else 1)
            valid = [v for v in votes if v]
            choice = max(ids, key=lambda x: (valid.count(x), -ids.index(x))) if valid else None
        row = {'row_index': i, 'options': [c['id'] for c in reps], 'choice': choice, 'output': texts}
        with lock, out.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, jobs))
    done = load_jsonl(out)
    vote_ok = sel_ok = fixed = broke = 0
    final = 0
    for i in sorted(ex):
        cands = lab_candidates(ex[i], base=args.base, plan=args.plan)
        g = groups_of(cands)
        top = bool(g) and g[0][0]['ok']
        pick = top
        if i in done:
            ids = done[i]['options']
            chosen = ids[int(done[i]['choice']) - 1] if done[i]['choice'] else ids[0]
            pick = next(c for c in cands if c['id'] == chosen)['ok']
            vote_ok += top
            sel_ok += pick
            fixed += pick and not top
            broke += top and not pick
        final += pick
    print(json.dumps({'tag': args.tag, 'selected_rows': len(done), 'vote_correct_there': vote_ok,
                      'selector_correct_there': sel_ok, 'fixed': fixed, 'broke': broke, 'final_correct': final,
                      'usd': round(tracker.spent, 4)}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('gen', 'exec', 'eval', 'select'))
    parser.add_argument('--n', type=int, default=8, help='plan samples generated per question')
    parser.add_argument('--base', type=int, default=8)
    parser.add_argument('--plan', type=int, default=8)
    parser.add_argument('--groups', type=int, default=3)
    parser.add_argument('--select-below', type=float, default=0.5)
    parser.add_argument('--tag', default='default')
    parser.add_argument('--mode', choices=('list', 'support', 'sc5', 'pair'), default='list')
    parser.add_argument('--workers', type=int, default=8)
    parser.add_argument('--max-usd', type=float, default=0.0)
    args = parser.parse_args()
    LAB.mkdir(parents=True, exist_ok=True)
    if args.command in ('gen', 'select') and args.max_usd <= 0:
        raise SystemExit('API commands need --max-usd')
    {'gen': cmd_gen, 'exec': cmd_exec, 'eval': cmd_eval, 'select': cmd_select}[args.command](args)


if __name__ == '__main__':
    main()
