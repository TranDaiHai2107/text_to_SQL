"""Paired comparison of Ours vs the reconstructed baselines on BIRD dev (no API).

Split (fixed before any full Ours result was seen): a 300-question *tuning* split, used for
error analysis and choosing improvements, and the remaining 1,234 *held-out* questions, used
only for reporting. The split contains the 30-question pilot rows. Significance: exact
two-sided McNemar test on discordant pairs.
"""
from __future__ import annotations

import argparse
import json
from math import comb
from pathlib import Path
import random

from verify_assets import DATA, ROOT

SEED, PILOT, TUNING = 20261119, 30, 300
SPLIT_FILE = ROOT / 'results' / 'omnisql' / 'ours' / 'splits.json'
BASE = ROOT / 'results' / 'omnisql' / 'gpt-4o-mini-2024-07-18'


def splits(n: int = 1534) -> dict:
    if SPLIT_FILE.exists():
        return json.loads(SPLIT_FILE.read_text(encoding='utf-8'))
    pilot = sorted(random.Random(SEED).sample(range(n), PILOT))
    rest = [i for i in range(n) if i not in set(pilot)]
    tuning = sorted(pilot + random.Random(SEED + 1).sample(rest, TUNING - PILOT))
    result = {'seed': SEED, 'tuning': tuning, 'held_out': [i for i in range(n) if i not in set(tuning)]}
    SPLIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SPLIT_FILE.write_text(json.dumps(result) + '\n', encoding='utf-8')
    return result


def mcnemar(b: int, c: int) -> float:
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(0, min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(ours: list[int], base: list[int], rows: list[int]) -> dict:
    o, b = [ours[i] for i in rows], [base[i] for i in rows]
    ours_only = sum(x and not y for x, y in zip(o, b))
    base_only = sum(y and not x for x, y in zip(o, b))
    return {'n': len(rows), 'ours_ex': round(100 * sum(o) / len(rows), 2), 'base_ex': round(100 * sum(b) / len(rows), 2),
            'ours_only': ours_only, 'base_only': base_only, 'mcnemar_p': round(mcnemar(ours_only, base_only), 4)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('ours_per_question', type=Path)
    args = parser.parse_args()
    ours = json.loads(args.ours_per_question.read_text(encoding='utf-8'))
    gold = json.loads((DATA / 'dev_20240627' / 'dev.json').read_text(encoding='utf-8'))
    split = splits(len(gold))
    report = {}
    for mode in ('greedy_search', 'major_voting'):
        base = json.loads((BASE / f'{mode}_score_per_question.json').read_text(encoding='utf-8'))
        groups = {'all': list(range(len(gold))), 'tuning': split['tuning'], 'held_out': split['held_out']}
        for level in ('simple', 'moderate', 'challenging'):
            groups[level] = [i for i, g in enumerate(gold) if g['difficulty'] == level]
        report[mode] = {name: compare(ours, base, rows) for name, rows in groups.items()}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
