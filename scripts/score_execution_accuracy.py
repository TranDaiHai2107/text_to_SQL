"""Tier 1 metric: deterministic execution accuracy against CLINSQL gold result CSVs.

Runs entirely locally: saved prediction results (restricted storage) are compared
with the benchmark's reference ``result_*.csv`` files. No model call, no data
leaves the machine, and only per-case booleans/shapes are written out.

Two pre-registered variants (fixed before any test-split scoring):

* ``ex_strict``  - BIRD-style execution accuracy: same row count and column count,
  rows equal as an unordered multiset with positional columns. Column names are
  ignored; numbers compare with tolerance 1e-8 + 1e-6*|x|; NULL equals only an
  empty reference cell.
* ``ex_relaxed`` - every reference column is matched, by values, to a distinct
  predicted column, and the projected rows equal the reference rows as an
  unordered multiset. Extra predicted columns and different names are allowed.

A case without an executed, stored result scores 0 in both variants and stays in
the denominator (same convention as the official scorer's missing-result 0).
This is a supplementary metric, not the official CLINSQL Execution Score.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from evaluate_pilot5_diagnostic import _same_cell, _unordered_multiset_equal  # noqa: E402
from ehrqa.clinsql.result_artifacts import ResultArtifactStore  # noqa: E402

STATE = ROOT / 'results/restricted/four_method_pilot'
SPLITS = ROOT / 'external/clinsql_official/data/splits'
PHASE = 'FOUR_METHOD_PILOT_5'
METRIC_VERSION = 'tier1_ex_v1_20261117'


# ---------------------------------------------------------------- comparison

def ex_strict(columns, rows, ref_columns, ref_rows) -> bool:
    if len(columns) != len(ref_columns) or len(rows) != len(ref_rows):
        return False
    return _unordered_multiset_equal(tuple(tuple(r) for r in rows), ref_rows)


def _column_values_match(rows, index, ref_rows, ref_index) -> bool:
    """Necessary condition: the column multisets agree (with numeric tolerance)."""
    predicted = [row[index] for row in rows]
    reference = [row[ref_index] for row in ref_rows]
    used = [False] * len(reference)
    for value in predicted:
        for j, text in enumerate(reference):
            if not used[j] and _same_cell(value, text):
                used[j] = True
                break
        else:
            return False
    return True


def ex_relaxed(columns, rows, ref_columns, ref_rows) -> bool:
    if len(rows) != len(ref_rows) or len(columns) < len(ref_columns):
        return False
    if not ref_rows:
        return True  # both empty; reference columns cannot be checked by value
    options = [[i for i in range(len(columns)) if _column_values_match(rows, i, ref_rows, j)]
               for j in range(len(ref_columns))]
    if any(not choice for choice in options):
        return False
    order = sorted(range(len(ref_columns)), key=lambda j: len(options[j]))
    mapping: dict[int, int] = {}

    def search(k: int) -> bool:
        if k == len(order):
            projected = tuple(tuple(row[mapping[j]] for j in range(len(ref_columns))) for row in rows)
            return _unordered_multiset_equal(projected, ref_rows)
        j = order[k]
        for i in options[j]:
            if i in mapping.values():
                continue
            mapping[j] = i
            if search(k + 1):
                return True
            del mapping[j]
        return False

    return search(0)


def reference(split: str, case_id: str):
    path = SPLITS / split / case_id / f"result_{case_id.rsplit('/', 1)[1]}.csv"
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.reader(stream)
        columns = next(reader)
        rows = list(reader)
    return columns, rows, hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------- predictions

def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cot_predictions(audit_path: Path):
    audit = json.loads(audit_path.read_text(encoding='utf-8'))
    out = {}
    for case_id, row in audit['cases'].items():
        log = json.loads(Path(row['run_log']).read_text(encoding='utf-8'))
        refs = [e for e in log['events'] if e['stage'] == 'result_artifact']
        if len(refs) != 1 or refs[0]['sha256'] != row['artifact_sha256']:
            raise ValueError(f'CoT artifact reference mismatch: {case_id}')
        out[case_id] = {'artifact_id': refs[0]['artifact_id'], 'sha256': refs[0]['sha256'],
                        'status': 'EXECUTED', 'prediction_sha256': _sha(Path(row['run_log']))}
    return out


def four_method_predictions(directory: Path, method: str):
    with sqlite3.connect(f'{(directory / "state.sqlite").as_uri()}?mode=ro', uri=True) as db:
        pins = dict(db.execute('SELECT case_id, artifact_sha256 FROM case_runs WHERE phase=? AND method=?',
                               (PHASE, method)))
    out = {}
    for path in directory.glob('*.json'):
        if path.name == 'profile.json':
            continue
        record = json.loads(path.read_bytes())
        if record.get('method') != method:
            continue
        if _sha(path) != pins.get(record['case_id']):
            raise ValueError(f'{method} checkpoint differs from ledger: {record["case_id"]}')
        artifact = record.get('artifact') or {}
        out[record['case_id']] = {'artifact_id': artifact.get('artifact_id'), 'sha256': artifact.get('sha256'),
                                  'status': record.get('status'), 'prediction_sha256': _sha(path)}
    return out


# ---------------------------------------------------------------- statistics

def mcnemar_exact(a: list[bool], b: list[bool]) -> dict:
    only_a = sum(x and not y for x, y in zip(a, b))
    only_b = sum(y and not x for x, y in zip(a, b))
    n = only_a + only_b
    if n == 0:
        return {'only_first': 0, 'only_second': 0, 'p_value': 1.0}
    k = min(only_a, only_b)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return {'only_first': only_a, 'only_second': only_b, 'p_value': min(1.0, 2 * tail)}


def bootstrap_ci(values: list[bool], *, iterations=10000, seed=20261117) -> list[float]:
    if not values:
        return [0.0, 0.0]
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iterations))
    return [means[int(0.025 * iterations)], means[int(0.975 * iterations) - 1]]


# ---------------------------------------------------------------- main

def evaluate(sources: dict[str, dict], case_ids: list[str], split: str) -> dict:
    store = ResultArtifactStore(ROOT / 'results/restricted')
    cases, per_method = {}, {m: {'strict': [], 'relaxed': []} for m in sources}
    for case_id in case_ids:
        ref_columns, ref_rows, ref_sha = reference(split, case_id)
        row = {'reference_sha256': ref_sha, 'reference_shape': [len(ref_rows), len(ref_columns)]}
        for method, predictions in sources.items():
            prediction = predictions.get(case_id)
            strict = relaxed = False
            shape = None
            status = prediction['status'] if prediction else 'MISSING'
            if prediction and status == 'EXECUTED' and prediction['artifact_id']:
                result = store.load(prediction['artifact_id'], expected_sha256=prediction['sha256'])
                columns, rows = list(result.columns), [list(r) for r in result.rows]
                shape = [len(rows), len(columns)]
                strict = ex_strict(columns, rows, ref_columns, ref_rows)
                relaxed = strict or ex_relaxed(columns, rows, ref_columns, ref_rows)
            row[method] = {'status': status, 'shape': shape, 'ex_strict': strict, 'ex_relaxed': relaxed,
                           'prediction_sha256': prediction['prediction_sha256'] if prediction else None}
            per_method[method]['strict'].append(strict)
            per_method[method]['relaxed'].append(relaxed)
        cases[case_id] = row
    summary = {}
    for method, values in per_method.items():
        n = len(case_ids)
        summary[method] = {
            'n': n,
            'executed': sum(cases[c][method]['status'] == 'EXECUTED' for c in case_ids),
            'ex_strict': sum(values['strict']) / n if n else None,
            'ex_relaxed': sum(values['relaxed']) / n if n else None,
            'ex_strict_ci95': bootstrap_ci(values['strict']),
            'ex_relaxed_ci95': bootstrap_ci(values['relaxed']),
        }
    pairs = {}
    if 'ours' in per_method:
        for other in per_method:
            if other == 'ours':
                continue
            pairs[f'ours_vs_{other}'] = {
                variant: mcnemar_exact(per_method['ours'][variant], per_method[other][variant])
                for variant in ('strict', 'relaxed')}
    return {'metric': METRIC_VERSION, 'label': 'SUPPLEMENTARY_DETERMINISTIC_EX_NOT_OFFICIAL_CLINSQL',
            'split': split, 'case_ids': case_ids, 'generated_at_utc': datetime.now(timezone.utc).isoformat(),
            'summary': summary, 'paired_mcnemar': pairs, 'cases': cases}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ours-root', type=Path, action='append', default=None,
                        help='Ours prediction folder; repeat for retries (later folders override '
                             'infrastructure-censored cases of earlier ones)')
    parser.add_argument('--cot-audit', type=Path, default=ROOT / 'results/phase_c1_pilot_audit.json')
    parser.add_argument('--sde-root', type=Path, default=STATE / 'sde_sql_uncapped/probe_continuation')
    parser.add_argument('--methods', default='clinsql_cot,sde_sql,ours')
    parser.add_argument('--output', type=Path, default=ROOT / 'results/evaluation/tier1_pilot5.json')
    args = parser.parse_args()
    pilot = json.loads((ROOT / 'data/clinsql/pilot_5_validation_development_v1.json').read_text(encoding='utf-8'))
    case_ids = [c['case_id'] for c in pilot['cases']]
    wanted = args.methods.split(',')
    sources = {}
    if 'clinsql_cot' in wanted:
        sources['clinsql_cot'] = cot_predictions(args.cot_audit)
    if 'sde_sql' in wanted:
        sources['sde_sql'] = four_method_predictions(args.sde_root, 'sde_sql')
    ours_roots = args.ours_root or [STATE / 'ours/public_terminology_v6']
    if 'ours' in wanted and all((root / 'state.sqlite').is_file() for root in ours_roots):
        merged = {}
        for root in ours_roots:
            for case_id, prediction in four_method_predictions(root, 'ours').items():
                merged[case_id] = {**prediction, 'source_root': root.name}
        sources['ours'] = merged
    report = evaluate(sources, case_ids, 'validation')
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'results').resolve()):
        raise PermissionError('Evaluation output must stay inside project results')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'summary': report['summary'], 'paired_mcnemar': report['paired_mcnemar']}, indent=1))
    for case_id, row in report['cases'].items():
        print(case_id, row['reference_shape'],
              {m: (v['status'], v['shape'], int(v['ex_strict']), int(v['ex_relaxed']))
               for m, v in row.items() if isinstance(v, dict)})
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
