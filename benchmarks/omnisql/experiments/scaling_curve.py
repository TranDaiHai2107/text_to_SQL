"""Accuracy vs number of samples, and API cost per sample (offline, no API calls).

Candidates per question (both sampling draws are used, nothing is regenerated):
  baseline  bg (greedy) + b1..b16  (Maj-8 draw 1 = b1..b8, draw 2 = b9..b16)
  Ours      og (greedy) + os1..os16 (base prompt; v9 s1..s8 + v9_noplan s1..s8) + op1..op8 (plan prompt) + ogr (repair)

Curves are vote-only (no LLM selector): for k <= pool size, mean over random k-subsets (order kept, ties go
to the first seen like the author max()); for k > pool size, bootstrap with replacement from the pool (the
empirical answer distribution taken as the model's); 'inf' is the mode of that distribution. Correctness is
set equality with the gold result (as the author evaluator) at timeout 60 s, so values approximate the
author-scored EX; the k = 8 draw-1 points are checked against the author scores in the output.

  python scaling_curve.py exec    # executes every candidate once -> results/omnisql/scaling/executions.json
  python scaling_curve.py curve   # -> results/omnisql/scaling/curve.json
  python scaling_curve.py cost    # -> results/omnisql/scaling/cost.json
"""
from __future__ import annotations

import glob
import json
import random
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CMD = sys.argv[1] if len(sys.argv) > 1 else ''
sys.argv = sys.argv[:1]
from v9_lab import _exec_job, load_jsonl, db_file, DEV, OURS  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / 'results/omnisql/gpt-4o-mini-2024-07-18'
RUNS = OURS / 'gpt-4o-mini-2024-07-18'
OUT = ROOT / 'results/omnisql/scaling'
N = 1534
R = 200  # random subsets / bootstrap replicates per question and k
PRICE = {'input': 0.15e-6, 'cached': 0.075e-6, 'output': 0.60e-6}  # gpt-4o-mini, USD per token


def candidates() -> list[list[tuple[str, str]]]:
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    greedy, d1, d2 = load(BASE / 'greedy_search.json'), load(BASE / 'major_voting.json'), load(
        BASE / 'major_voting_draw2/major_voting.json')
    v9, v9b = load_jsonl(RUNS / 'v9/predictions.jsonl'), load_jsonl(RUNS / 'v9_noplan/predictions.jsonl')
    out = []
    for i in range(N):
        a = {c['id']: c['sql'] or '' for c in v9[i]['candidates']}
        b = {c['id']: c['sql'] or '' for c in v9b[i]['candidates']}
        c = [('bg', greedy[i]['pred_sqls'][0])] + [(f'b{k + 1}', s or '') for k, s in
                                                   enumerate(d1[i]['pred_sqls'] + d2[i]['pred_sqls'])]
        c += [('og', a.get('g', ''))] + [(f'os{k}', a.get(f's{k}', '')) for k in range(1, 9)]
        c += [(f'os{k + 8}', b.get(f's{k}', '')) for k in range(1, 9)]
        c += [(f'op{k}', a.get(f'p{k}', '')) for k in range(1, 9)] + [('ogr', a.get('gr', ''))]
        out.append(c)
    return out


def cmd_exec():
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    cands = candidates()
    tasks = [(i, str(db_file(gold[i]['db_id'])), gold[i]['SQL'], cands[i]) for i in range(N)]
    OUT.mkdir(parents=True, exist_ok=True)
    with ProcessPoolExecutor(4) as pool:
        res = dict(pool.map(_exec_job, tasks, chunksize=4))
    for rows in res.values():
        for r in rows:
            r.pop('sql', None)
    (OUT / 'executions.json').write_text(json.dumps(res), encoding='utf-8')
    print('executed', len(res))


# ---- vote rules over records {'fp', 'values', 'ok'} ----
def author_vote(recs) -> int:
    """OmniSQL major_voting: every executed SQL votes (empty results too); max() keeps the first seen on ties."""
    counts, ok = {}, {}
    for r in recs:
        if r['fp'] is not None:
            counts[r['fp']] = counts.get(r['fp'], 0) + 1
            ok.setdefault(r['fp'], r['ok'])
    if not counts:
        return 0
    return int(ok[max(counts, key=counts.get)])


def ours_vote(recs) -> int:
    """Ours: candidates returning values first (fall back to all executed), largest group, first seen on ties."""
    executed = [r for r in recs if r['fp'] is not None]
    pool = [r for r in executed if r['values']] or executed
    return author_vote(pool)


def oracle(recs) -> int:
    return int(any(r['ok'] for r in recs))


def limit(pools: list[tuple[list[dict], float]], rule) -> float:
    """k -> infinity under a mixture of empirical pools (pool, weight): mode of the answer distribution."""
    w, ok, valid_w, values_w = defaultdict(float), {}, 0.0, defaultdict(float)
    for recs, weight in pools:
        for r in recs:
            if r['fp'] is None:
                continue
            p = weight / len(recs)
            w[r['fp']] += p
            ok[r['fp']] = r['ok']
            values_w[r['fp']] = r['values']
    if rule is ours_vote and any(values_w[f] for f in w):
        w = {f: v for f, v in w.items() if values_w[f]}
    if not w:
        return 0.0
    best = max(w.values())
    tied = [f for f, v in w.items() if abs(v - best) < 1e-12]
    return sum(ok[f] for f in tied) / len(tied)


def curve_point(pools: list[list[dict]], ks: list[int], rule, rng) -> float:
    """Mean vote accuracy when drawing ks[j] candidates from pools[j] (subsets if k <= size, else bootstrap)."""
    if all(k == len(p) for k, p in zip(ks, pools)):
        return float(rule([r for p in pools for r in p]))
    total = 0
    for _ in range(R):
        recs = []
        for k, p in zip(ks, pools):
            if k <= len(p):
                recs += [p[j] for j in sorted(rng.sample(range(len(p)), k))]
            else:
                recs += [p[rng.randrange(len(p))] for _ in range(k)]
        rng.shuffle(recs) if any(k > len(p) for k, p in zip(ks, pools)) else None
        total += rule(recs)
    return total / R


def cmd_curve():
    ex = json.loads((OUT / 'executions.json').read_text(encoding='utf-8'))
    split = json.loads((ROOT / 'results/omnisql/ours/splits.json').read_text())
    held = sorted(set(range(N)) - set(split['tuning']))
    by_id = [{r['id']: r for r in ex[str(i)]} for i in range(N)]
    pick = lambda i, ids: [by_id[i][c] for c in ids]
    B16 = [f'b{k}' for k in range(1, 17)]
    S16 = [f'os{k}' for k in range(1, 17)]
    P8 = [f'op{k}' for k in range(1, 9)]
    rng = random.Random(0)
    ks = [1, 2, 4, 8, 12, 16, 24, 32, 64]
    configs = {  # name -> (pools, rule, ks per pool for a total k)
        'baseline_author_vote': ([B16], author_vote, lambda k: [k]),
        'baseline_ours_vote': ([B16], ours_vote, lambda k: [k]),
        'ours_base_prompt_only': ([S16], ours_vote, lambda k: [k]),
        'ours_base_plus_plan_half_half': ([S16, P8], ours_vote, lambda k: [k - k // 2, k // 2]),
    }
    oracle_cfg = {'baseline_oracle': B16, 'ours_base_oracle': S16}
    result = {'ks': ks, 'R': R, 'curves': {}, 'oracle': {}, 'checks': {}, 'fixed': {}}
    for name, (pools, rule, split_k) in configs.items():
        per_q = {k: [] for k in ks}
        lim = []
        for i in range(N):
            qp = [pick(i, ids) for ids in pools]
            for k in ks:
                kk = split_k(k)
                if any(x == 0 for x in kk) and len(kk) > 1:
                    kk = [k] + [0] * (len(kk) - 1)
                use = [(p, x) for p, x in zip(qp, kk) if x > 0]
                per_q[k].append(curve_point([p for p, _ in use], [x for _, x in use], rule, rng))
            weights = [x / sum(split_k(1000)) for x in split_k(1000)]
            lim.append(limit(list(zip(qp, weights)), rule))
        result['curves'][name] = {
            'all': {str(k): round(100 * sum(v) / N, 2) for k, v in per_q.items()} | {'inf': round(100 * sum(lim) / N, 2)},
            'held_out': {str(k): round(100 * sum(v[i] for i in held) / len(held), 2) for k, v in per_q.items()}
                        | {'inf': round(100 * sum(lim[i] for i in held) / len(held), 2)}}
        print(name, result['curves'][name]['all'], flush=True)
    for name, ids in oracle_cfg.items():
        pts = {}
        for k in [1, 2, 4, 8, 16]:
            pts[str(k)] = round(100 * sum(curve_point([pick(i, ids)], [k], oracle, rng) for i in range(N)) / N, 2)
        result['oracle'][name] = pts
        print(name, pts, flush=True)
    fixed = {  # exact candidate sets (no sampling)
        'baseline_maj8_draw1': (B16[:8], author_vote), 'baseline_maj8_draw2': (B16[8:], author_vote),
        'baseline_maj16': (B16, author_vote), 'baseline_g_plus_16': (['bg'] + B16, author_vote),
        'ours_at8_draw1': (S16[:8], ours_vote), 'ours_at8_draw2': (S16[8:], ours_vote),
        'ours_at16_base_prompt': (S16, ours_vote),
        'ours_v9_vote_only_no_selector': (['og'] + S16[:8] + P8 + ['ogr'], ours_vote),
        'ours_v9_plus_draw2_base_26': (['og'] + S16 + P8 + ['ogr'], ours_vote),
        'oracle_baseline_g_plus_16': (['bg'] + B16, oracle), 'oracle_ours_all_26': (['og'] + S16 + P8 + ['ogr'], oracle),
    }
    for name, (ids, rule) in fixed.items():
        v = [rule(pick(i, ids)) for i in range(N)]
        result['fixed'][name] = {'all': round(100 * sum(v) / N, 2), 'held_out': round(100 * sum(v[i] for i in held) / len(held), 2)}
    result['checks'] = {'author_scored_baseline_maj8_draw1': 61.99, 'author_scored_ours_at8_draw1': 63.62,
                        'author_scored_v9_with_selector': 65.06}
    (OUT / 'curve.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result['fixed'], indent=1))


def cmd_cost():
    def usd(prompt, cached, completion):
        return (prompt - cached) * PRICE['input'] + cached * PRICE['cached'] + completion * PRICE['output']

    out = {}
    for name, path in [('baseline_greedy', BASE / 'greedy_search.jsonl'), ('baseline_8_samples_draw1', BASE / 'major_voting.jsonl'),
                       ('baseline_8_samples_draw2', BASE / 'major_voting_draw2/major_voting.jsonl')]:
        p = c = o = 0
        for line in path.read_text(encoding='utf-8').splitlines():
            u = json.loads(line)['usage']
            p += u['prompt_tokens']; o += u['completion_tokens']
            c += (u.get('prompt_tokens_details') or {}).get('cached_tokens') or 0
        out[name] = {'calls': N, 'prompt_tokens': p, 'cached_tokens': c, 'completion_tokens': o, 'usd': round(usd(p, c, o), 3)}
    for run in ('v9', 'v9_noplan'):
        agg = defaultdict(lambda: {'calls': 0, 'prompt_tokens': 0, 'cached_tokens': 0, 'completion_tokens': 0, 'usd': 0.0})
        for f in glob.glob(str(RUNS / run / 'traces/*.jsonl')):
            for line in open(f, encoding='utf-8'):
                r = json.loads(line)
                if r.get('stage') != 'model.response':
                    continue
                a, u = agg[f"{r.get('operation')}_n{r.get('n')}"], r.get('usage', {})
                a['calls'] += 1; a['usd'] += r.get('usd', 0)
                a['prompt_tokens'] += u.get('prompt_tokens', 0); a['completion_tokens'] += u.get('completion_tokens', 0)
                a['cached_tokens'] += u.get('cached_tokens', 0)
        out[f'ours_{run}'] = {k: v | {'usd': round(v['usd'], 3)} for k, v in agg.items()}
        out[f'ours_{run}']['total_usd'] = round(sum(v['usd'] for v in agg.values()), 3)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'cost.json').write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    {'exec': cmd_exec, 'curve': cmd_curve, 'cost': cmd_cost}.get(CMD, lambda: print(__doc__))()
