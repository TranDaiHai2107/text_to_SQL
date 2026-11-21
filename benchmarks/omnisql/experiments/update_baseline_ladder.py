"""update_baseline ladder table: one change per rung, paired McNemar between consecutive rungs (no API).

Every rung is scored with the author evaluator (num_cpus 4, timeout 60, PYTHONUTF8=1) by
draws_and_budget.py; this script only reads the per-question files and builds the table.

  rung              per-question file (results/omnisql/draws_and_budget/)       produced by
  ub0_baseline      baseline_maj8_draw1                                      draws_and_budget.py score
  ub1_vote          baseline_samples_oursvote_draw1                          draws_and_budget.py score
  ub2_context       ours_at8_draw1                                           draws_and_budget.py score
  ub3_repair        ub3_repair                                               draws_and_budget.py score ub3_repair
  ub4_plan          ub4_plan                                                 draws_and_budget.py score ub4_plan
  ub5_select        ours_v9 (= Ours v9, author-scored 65.06)                 draws_and_budget.py score (copy)
  ub6/ub7           need new runs (run_ours_bird.py --variant ub6_value_check / ub7_pairwise)

  python update_baseline_ladder.py   # -> results/omnisql/draws_and_budget/update_baseline_ladder.json
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from compare_ours import compare  # noqa: E402
from ehrqa.bird.update_baseline import STEPS  # noqa: E402

OUT = ROOT / 'results/omnisql/draws_and_budget'
FILES = {'ub0_baseline': 'baseline_maj8_draw1', 'ub1_vote': 'baseline_samples_oursvote_draw1',
         'ub2_context': 'ours_at8_draw1', 'ub3_repair': 'ub3_repair', 'ub4_plan': 'ub4_plan',
         'ub5_select': 'ours_v9', 'ub6_value_check': 'ub6_value_check', 'ub7_pairwise': 'ub7_pairwise'}


def main():
    gold = json.loads((ROOT / 'data/benchmarks/bird/dev_20240627/dev.json').read_text(encoding='utf-8'))
    split = json.loads((ROOT / 'results/omnisql/ours/splits.json').read_text())
    groups = {'all': list(range(len(gold))),
              'held_out': [i for i in range(len(gold)) if i not in set(split['tuning'])]}
    rows, prev, base = [], None, None
    for name, change, _ in STEPS:
        path = OUT / f'{FILES[name]}_per_question.json'
        if not path.exists():
            rows.append({'rung': name, 'change': change, 'status': 'missing', 'file': path.name})
            prev = None
            continue
        per = json.loads(path.read_text())
        row = {'rung': name, 'change': change}
        for g, ids in groups.items():
            row[f'ex_{g}'] = round(100 * sum(per[i] for i in ids) / len(ids), 2)
            if prev is not None:
                row[f'vs_previous_{g}'] = compare(per, prev, ids)
            if base is not None:
                row[f'vs_baseline_{g}'] = compare(per, base, ids)
        rows.append(row)
        prev = per
        base = per if base is None else base
    (OUT / 'update_baseline_ladder.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
    for r in rows:
        if r.get('status') == 'missing':
            print(f"{r['rung']:16s} missing ({r['file']})")
            continue
        step = r.get('vs_previous_all')
        delta = f"  {step['ours_only']:3d}/{step['base_only']:3d}  p={step['mcnemar_p']}" if step else ''
        print(f"{r['rung']:16s} {r['ex_all']:6.2f}  held-out {r['ex_held_out']:6.2f}{delta}  {r['change']}")


if __name__ == '__main__':
    main()
