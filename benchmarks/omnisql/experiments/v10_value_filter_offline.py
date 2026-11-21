"""Free screen of v10's value_filter on the stored v9 candidates (no API calls).

Re-votes v9's executed candidates (g, s1..s8, p1..p8, gr; results/.../v9/candidate_executions.json) with
and without the v10 tier that drops candidates comparing a column with a literal not stored in it,
and counts how often each candidate kind carries such a literal. Vote-only (no selector), so the
numbers are compared with each other, not with the author-scored 65.06. Report the tuning split
first; look at held-out only for the configuration chosen on tuning.

  python v10_value_filter_offline.py            # tuning split
  python v10_value_filter_offline.py held_out   # after the choice is fixed
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
SPLIT = sys.argv[1] if len(sys.argv) > 1 else 'tuning'
sys.argv = sys.argv[:1]
from ehrqa.bird.database import BirdDatabase  # noqa: E402
from ehrqa.bird.ours_v10 import literal_mismatches  # noqa: E402
from compare_ours import compare  # noqa: E402

DATA = ROOT / 'data/benchmarks/bird'
DEV = DATA / 'dev_20240627'
V9 = ROOT / 'results/omnisql/ours/gpt-4o-mini-2024-07-18/v9'


def vote(cands, prefer_clean):
    executed = [c for c in cands if c['fp'] is not None]
    pool = [c for c in executed if c['values']] or executed
    if prefer_clean:
        pool = [c for c in pool if not c['mismatch']] or pool
    counts, ok = {}, {}
    for c in pool:
        counts[c['fp']] = counts.get(c['fp'], 0) + 1
        ok.setdefault(c['fp'], c['ok'])
    return int(ok[max(counts, key=counts.get)]) if counts else 0


def main():
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
    split = json.loads((ROOT / 'results/omnisql/ours/splits.json').read_text())
    ids = split['tuning'] if SPLIT == 'tuning' else sorted(set(range(len(gold))) - set(split['tuning']))
    ex = json.loads((V9 / 'candidate_executions.json').read_text(encoding='utf-8'))
    dbs, base, clean, flagged, flagged_ok = {}, [], [], Counter(), Counter()
    for i in ids:
        db_id = gold[i]['db_id']
        if db_id not in dbs:
            dbs[db_id] = BirdDatabase(DEV / 'dev_databases' / db_id / f'{db_id}.sqlite', prompts[i]['input_seq'],
                                      value_index_dir=DATA / 'ours_value_index')
        cands = ex[str(i)]
        for c in cands:
            c['mismatch'] = literal_mismatches(c['sql'], dbs[db_id].values) if c['fp'] is not None else []
            if c['mismatch']:
                kind = c['id'].rstrip('0123456789')
                flagged[kind] += 1
                flagged_ok[kind] += int(c['ok'])
        base.append(vote(cands, False))
        clean.append(vote(cands, True))
    n = len(ids)
    result = {'split': SPLIT, 'questions': n, 'vote_only_v9': round(100 * sum(base) / n, 2),
              'vote_only_value_filter': round(100 * sum(clean) / n, 2),
              'flagged_candidates': dict(flagged), 'flagged_but_correct': dict(flagged_ok),
              'paired': compare(clean, base, list(range(n)))}
    out = V9 / f'v10_value_filter_{SPLIT}.json'
    out.write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
