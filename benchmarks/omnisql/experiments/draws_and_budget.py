"""Second sampling draws (run-to-run noise) and the 17-candidate baseline (same budget as v9). No API calls.

Inputs (all kept; nothing earlier is overwritten):
  baseline greedy      results/omnisql/gpt-4o-mini-2024-07-18/greedy_search.json
  baseline Maj-8 #1    results/omnisql/gpt-4o-mini-2024-07-18/major_voting.json
  baseline Maj-8 #2    results/omnisql/gpt-4o-mini-2024-07-18/major_voting_draw2/major_voting.json
  Ours v9 (#1)         results/omnisql/ours/gpt-4o-mini-2024-07-18/v9/predictions.jsonl       (s1..s8 = Ours@8 #1)
  Ours v9_noplan (#2)  results/omnisql/ours/gpt-4o-mini-2024-07-18/v9_noplan/predictions.jsonl (s1..s8 = Ours@8 #2)

Every system is scored with the unmodified author evaluate_bird.py (num_cpus 4, timeout 60, warm-up then
recorded run, as score_bird.py). Baseline k-sample sets use the author major_voting(); Ours@8 uses Ours'
own vote (set fingerprint, value-returning candidates first) and the chosen SQL is then scored as greedy.

  python draws_and_budget.py score [name ...]   # writes results/omnisql/draws_and_budget/*.json
  python draws_and_budget.py report    # paired McNemar table (all / tuning / held-out / difficulty)
"""
from __future__ import annotations

import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CMD = sys.argv[1] if len(sys.argv) > 1 else ''
NAMES = sys.argv[2:]
sys.argv = sys.argv[:1]
from v9_lab import _run, db_file, load_jsonl  # noqa: E402
from ehrqa.bird.ours_v9 import vote_groups  # noqa: E402

BIRD = ROOT / 'data/benchmarks/bird/dev_20240627'
BASE = ROOT / 'results/omnisql/gpt-4o-mini-2024-07-18'
OURS = ROOT / 'results/omnisql/ours/gpt-4o-mini-2024-07-18'
OUT = ROOT / 'results/omnisql/draws_and_budget'
REPLAY = OURS / 'replay'  # v10_replay.py outputs (update_baseline rungs / v10 variants on v9's candidates)


def author_eval(rows: list[dict], mode: str, name: str) -> list[int]:
    if not sys.flags.utf8_mode:  # the author evaluator reads dev.json with open() and no encoding
        raise SystemExit('set PYTHONUTF8=1 (see benchmarks/omnisql/README.md)')
    sys.path.insert(0, str(ROOT / 'benchmarks/omnisql/official/train_and_evaluate'))
    import evaluate_bird
    if not getattr(evaluate_bird, '_limits_patched', False):
        author_execute = evaluate_bird.execute_sqls_parallel
        evaluate_bird.execute_sqls_parallel = lambda f, s, num_cpus=1, timeout=1: author_execute(f, s, num_cpus=4, timeout=60)
        evaluate_bird._limits_patched = True
    pred = OUT / f'{name}_pred.json'
    # ASCII escapes: the author evaluator opens the file without an encoding (cp1252 on Windows)
    pred.write_text(json.dumps(rows), encoding='utf-8')
    for _ in range(2):  # warm-up, then the recorded run (score_bird.py convention)
        ex, _ = evaluate_bird.run_eval(str(BIRD / 'dev.json'), str(pred), str(BIRD / 'dev_databases'), mode, False,
                                       num_cpus=4, timeout=60)
    per = [r['correctness'] for r in evaluate_bird.evaluation_results]
    (OUT / f'{name}_per_question.json').write_text(json.dumps(per), encoding='utf-8')
    print(name, mode, f'{100 * ex:.2f}', flush=True)
    return per


def _vote(task):
    i, db, cands = task
    executed = [{'id': cid, 'sql': sql, 'rows': _run(db, sql) if sql else None} for cid, sql in cands]
    groups = vote_groups(executed, use_set=True)
    return i, groups[0][0]['sql'] if groups else (cands[0][1] or '')


def ours_vote(samples: list[list[str]]) -> list[dict]:
    """Ours' vote rule over the given SQL candidates per question (order = tie order); one chosen SQL each."""
    gold = json.loads((BIRD / 'dev.json').read_text(encoding='utf-8'))
    tasks = [(i, str(db_file(gold[i]['db_id'])), [(f's{k + 1}', s or '') for k, s in enumerate(samples[i])])
             for i in range(len(gold))]
    with ProcessPoolExecutor(4) as pool:  # 4: more workers next to the scorer ran out of memory
        chosen = dict(pool.map(_vote, tasks, chunksize=8))
    return [{'pred_sqls': [chosen[i]]} for i in range(len(gold))]


def ours_at8(run_dir: Path) -> list[dict]:
    rows = load_jsonl(run_dir / 'predictions.jsonl')
    if len(rows) != 1534 or any(r['status'] == 'error' for r in rows.values()):
        raise SystemExit(f'{run_dir.name} is not complete')
    samples = []
    for i in range(1534):
        cand = {c['id']: c['sql'] or '' for c in rows[i]['candidates']}
        samples.append([cand.get(f's{k}', '') for k in range(1, 9)])
    return ours_vote(samples)


def v9_pool(keep) -> list[list[str]]:
    """Stored Ours v9 candidates (order g, s1..s8, p1..p8, gr) whose id passes keep(id)."""
    rows = load_jsonl(OURS / 'v9' / 'predictions.jsonl')
    return [[c['sql'] or '' for c in rows[i]['candidates'] if keep(c['id'])] for i in range(1534)]


def score(names: list[str]):
    """Score the named systems (all when none given); each name can run in its own process."""
    OUT.mkdir(parents=True, exist_ok=True)
    load = lambda p: json.loads(p.read_text(encoding='utf-8'))
    greedy, d1, d2 = (load(BASE / 'greedy_search.json'), load(BASE / 'major_voting.json'),
                      load(BASE / 'major_voting_draw2/major_voting.json'))
    assert len(greedy) == len(d1) == len(d2) == 1534
    jobs = {
        'baseline_maj8_draw1': lambda: ([{'pred_sqls': r['pred_sqls']} for r in d1], 'major_voting'),
        'baseline_maj8_draw2': lambda: ([{'pred_sqls': r['pred_sqls']} for r in d2], 'major_voting'),
        'baseline_maj16': lambda: ([{'pred_sqls': a['pred_sqls'] + b['pred_sqls']} for a, b in zip(d1, d2)],
                                   'major_voting'),
        'baseline_g_plus_16': lambda: ([{'pred_sqls': g['pred_sqls'][:1] + a['pred_sqls'] + b['pred_sqls']}
                                        for g, a, b in zip(greedy, d1, d2)], 'major_voting'),
        'ours_at8_draw1': lambda: (ours_at8(OURS / 'v9'), 'greedy_search'),
        'ours_at8_draw2': lambda: (ours_at8(OURS / 'v9_noplan'), 'greedy_search'),
        # the baseline's own 8 samples, re-voted with Ours' rule: separates the vote rule from the context
        'baseline_samples_oursvote_draw1': lambda: (ours_vote([r['pred_sqls'] for r in d1]), 'greedy_search'),
        'baseline_samples_oursvote_draw2': lambda: (ours_vote([r['pred_sqls'] for r in d2]), 'greedy_search'),
        # update_baseline rungs 3 and 4 from the stored v9 candidates, vote only (no selector)
        'ub3_repair': lambda: (ours_vote(v9_pool(lambda c: c == 'g' or c == 'gr' or c.startswith('s'))),
                               'greedy_search'),
        'ub4_plan': lambda: (ours_vote(v9_pool(lambda c: True)), 'greedy_search'),
    }
    for name in names:
        if name not in jobs and (REPLAY / name / 'greedy_search.json').exists():
            jobs[name] = lambda n=name: ([{'pred_sqls': r['pred_sqls']} for r in load(REPLAY / n / 'greedy_search.json')],
                                         'greedy_search')
    for name in names or list(jobs):
        rows, mode = jobs[name]()
        author_eval(rows, mode, name)
    v9 = json.loads((OURS / 'v9/greedy_search_score_per_question.json').read_text())
    (OUT / 'ours_v9_per_question.json').write_text(json.dumps(v9), encoding='utf-8')


def report():
    from compare_ours import compare
    gold = json.loads((BIRD / 'dev.json').read_text(encoding='utf-8'))
    split = json.loads((ROOT / 'results/omnisql/ours/splits.json').read_text())
    groups = {'all': list(range(len(gold))), 'tuning': split['tuning'],
              'held_out': [i for i in range(len(gold)) if i not in set(split['tuning'])]}
    for level in ('simple', 'moderate', 'challenging'):
        groups[level] = [i for i, g in enumerate(gold) if g['difficulty'] == level]
    load = lambda n: json.loads((OUT / f'{n}_per_question.json').read_text())
    pairs = [('ours_at8_draw1', 'baseline_maj8_draw1'), ('ours_at8_draw2', 'baseline_maj8_draw2'),
             ('ours_at8_draw1', 'baseline_maj8_draw2'), ('ours_at8_draw2', 'baseline_maj8_draw1'),
             ('ours_at8_draw2', 'ours_at8_draw1'), ('baseline_maj8_draw2', 'baseline_maj8_draw1'),
             ('ours_v9', 'baseline_g_plus_16'), ('ours_v9', 'baseline_maj16'), ('baseline_g_plus_16', 'baseline_maj8_draw1'),
             ('baseline_samples_oursvote_draw1', 'baseline_maj8_draw1'),
             ('baseline_samples_oursvote_draw2', 'baseline_maj8_draw2'),
             ('ours_at8_draw1', 'baseline_samples_oursvote_draw1'), ('ours_at8_draw2', 'baseline_samples_oursvote_draw2'),
             # v10 parts, each paired with v9 on the same stored candidates (v10_replay.py)
             ('ub6_value_check', 'ours_v9'), ('ub7_pairwise', 'ub6_value_check'), ('ub7_pairwise', 'ours_v9'),
             ('v10_merge', 'ub6_value_check'), ('v10_early', 'ub7_pairwise'), ('v10_dc', 'ub7_pairwise'),
             ('ub7_pairwise', 'baseline_maj8_draw1'), ('ub7_pairwise', 'baseline_g_plus_16')]
    have = lambda n: (OUT / f'{n}_per_question.json').exists()
    result = {f'{a} vs {b}': {g: compare(load(a), load(b), ids) for g, ids in groups.items()}
              for a, b in pairs if have(a) and have(b)}
    (OUT / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    for key, by_group in result.items():
        print(key)
        for g, r in by_group.items():
            print(f"  {g:12s} {r['ours_ex']:6.2f} vs {r['base_ex']:6.2f}  {r['ours_only']:3d}/{r['base_only']:3d}  p={r['mcnemar_p']}")


if __name__ == '__main__':
    if CMD == 'score':
        score(NAMES)
    elif CMD == 'report':
        report()
    else:
        print(__doc__)
