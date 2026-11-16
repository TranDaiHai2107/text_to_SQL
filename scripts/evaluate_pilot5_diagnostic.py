"""Offline validation diagnostic for saved Phase C.1 results; never export rows.

This is deliberately separate from the official Azure GPT-5-Chat rubric judge.
It reads validation references only after inference, and emits metadata/flags.
"""
from __future__ import annotations

import argparse
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from audit_phase_c1_pilot import audit
from ehrqa.clinsql.result_artifacts import ResultArtifactStore


def _same_cell(predicted, reference: str) -> bool:
    if predicted is None:
        return reference == ''
    if reference == '':
        return False
    if isinstance(predicted, bool):
        return str(predicted).lower() == reference.lower()
    if isinstance(predicted, (int, float, Decimal)):
        if isinstance(predicted, float) and math.isnan(predicted):
            return False  # NaN is not NULL or a literal reference string.
        try:
            left, right = Decimal(str(predicted)), Decimal(reference)
        except InvalidOperation:
            return False
        if not left.is_finite() or not right.is_finite():
            return False
        return abs(left - right) <= Decimal('1e-8') + Decimal('1e-6') * max(abs(left), abs(right))
    return str(predicted) == reference


def _same_row(predicted: tuple, reference: list[str]) -> bool:
    return len(predicted) == len(reference) and all(
        _same_cell(value, text) for value, text in zip(predicted, reference))


def _unordered_multiset_equal(predicted: tuple[tuple, ...], reference: list[list[str]]) -> bool:
    """Bipartite matching preserves duplicate multiplicity with float tolerance."""
    if len(predicted) != len(reference):
        return False
    edges = [[j for j, row in enumerate(reference) if _same_row(actual, row)]
             for actual in predicted]
    matched = [-1] * len(reference)

    def assign(i: int, seen: set[int]) -> bool:
        for j in edges[i]:
            if j in seen:
                continue
            seen.add(j)
            if matched[j] < 0 or assign(matched[j], seen):
                matched[j] = i
                return True
        return False

    return all(assign(i, set()) for i in range(len(predicted)))


def evaluate(run_roots: list[Path]) -> dict:
    checked = audit(run_roots)
    store = ResultArtifactStore(ROOT / 'results/restricted')
    reference_root = ROOT / 'external/clinsql_official/data/splits/validation'
    cases = {}
    for case_id, recorded in checked['cases'].items():
        saved = json.loads(Path(recorded['run_log']).read_text(encoding='utf-8'))
        artifact = next(e for e in saved['events'] if e['stage'] == 'result_artifact')
        result = store.load(artifact['artifact_id'], expected_sha256=artifact['sha256'])
        reference_path = reference_root / case_id / f"result_{case_id.rsplit('/', 1)[1]}.csv"
        with reference_path.open(encoding='utf-8-sig', newline='') as stream:
            reader = csv.reader(stream)
            columns = next(reader)
            rows = list(reader)
        if not result.complete or len(result.rows) != recorded['row_count']:
            raise ValueError('Incomplete or changed saved result')
        same_width = len(result.columns) == len(columns)
        same_names = tuple(result.columns) == tuple(columns)
        same_count = len(result.rows) == len(rows)
        value_match = (_unordered_multiset_equal(result.rows, rows)
                       if same_width and same_count else None)
        cases[case_id] = {
            'prediction_column_count': len(result.columns),
            'reference_column_count': len(columns),
            'prediction_row_count': len(result.rows),
            'reference_row_count': len(rows),
            'column_names_equal': same_names,
            'row_counts_equal': same_count,
            'unordered_positional_values_equal': value_match,
            'strict_result_match': bool(same_names and same_count and value_match),
            'reference_csv_sha256': hashlib.sha256(reference_path.read_bytes()).hexdigest(),
            'diagnostic_only': True,
        }
    return {
        'status': 'DIAGNOSTIC_ONLY_OFFICIAL_SCORE_NOT_AVAILABLE',
        'case_count': len(cases),
        'strict_result_matches': sum(row['strict_result_match'] for row in cases.values()),
        'official_sql_score': None,
        'official_execution_score': None,
        'comparison_policy': 'docs/markdown/CLINSQL_RESULT_COMPARISON_POLICY.md',
        'cases': cases,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', type=Path, required=True, action='append')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.run_root)
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / 'results').resolve()):
        raise PermissionError('Diagnostic output must remain within project results')
    data = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if output.exists() and output.read_text(encoding='utf-8') != data:
        raise FileExistsError('Existing diagnostic differs; investigate before overwriting')
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.exists():
        output.write_text(data, encoding='utf-8')
    print(json.dumps({key: report[key] for key in
                      ('status', 'case_count', 'strict_result_matches')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
