"""Import verified Phase C.1 case artifacts into a durable Phase C.2 ledger.

This command reads local evidence only. It never generates SQL, calls an API,
executes BigQuery, unlocks test, or marks an unrun experiment complete.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))

from audit_phase_c1_pilot import audit
from ehrqa.clinsql.experiment_state import ExperimentState, verify_pre_freeze_manifest

RUN_ROOTS = [
    ROOT / 'results/phase_c1_runs_e4cb022c47e1_phase_c1_v4_20261113T185128Z_ef381a50',
    ROOT / 'results/phase_c1_runs_e4cb022c47e1_phase_c1_v5_20261114T005101Z_55f1fb96',
]

PHASE_ORDER = (
    'PILOT_EVALUATION', 'BASELINE_FIDELITY', 'FOUR_METHOD_LIVE_PILOT',
    'VALIDATION_152', 'INTERNAL_CHECK_38', 'CONFIG_FREEZE', 'TEST_443',
    'OFFICIAL_SCORING', 'FINAL_REPORT',
)


def checkpoint() -> dict:
    master = json.loads((ROOT / 'data/clinsql/master_experiment_pre_freeze_v1.json').read_text(encoding='utf-8'))
    verify_pre_freeze_manifest(master)
    verified = audit(RUN_ROOTS)
    diagnostic = json.loads((ROOT / 'results/phase_c1_pilot_diagnostic.json').read_text(encoding='utf-8'))
    staging = json.loads((ROOT / 'results/phase_c1_staging_check.json').read_text(encoding='utf-8'))
    if (diagnostic['case_count'] != 5 or staging['case_count'] != 5 or
        not staging['temporary_stage_deleted'] or
        diagnostic['official_sql_score'] is not None or
        diagnostic['official_execution_score'] is not None):
        raise ValueError('Pilot diagnostic/scorer staging evidence is inconsistent')
    ledger = ExperimentState(ROOT / 'results/restricted/phase_c2_state.sqlite', master)
    existing = {row.case_id: row for row in ledger.checkpoints('PILOT_5')}
    for case_id, case in verified['cases'].items():
        sha = case['artifact_sha256']
        if case_id in existing:
            prior = existing[case_id]
            if prior.status != 'EXECUTED' or prior.artifact_sha256 != sha:
                raise ValueError('Conflicting or interrupted imported pilot checkpoint')
            continue
        ledger.claim('PILOT_5', 'clinsql_cot', case_id)
        ledger.finish('PILOT_5', 'clinsql_cot', case_id,
                      status='EXECUTED', artifact_sha256=sha)
    complete = ledger.checkpoints('PILOT_5')
    if len(complete) != 5 or any(row.status != 'EXECUTED' for row in complete):
        raise ValueError('Pilot ledger is not exactly five executed cases')
    states = {
        'PILOT_EVALUATION': 'DIAGNOSTIC_COMPLETE_OFFICIAL_JUDGE_BLOCKED',
        'BASELINE_FIDELITY': 'IN_PROGRESS_OFFLINE',
        'FOUR_METHOD_LIVE_PILOT': 'BLOCKED_FIDELITY_DATA_POLICY_AND_APPROVAL',
        'VALIDATION_152': 'NOT_STARTED',
        'INTERNAL_CHECK_38': 'NOT_STARTED',
        'CONFIG_FREEZE': 'NOT_STARTED',
        'TEST_443': 'SEALED_NOT_STARTED',
        'OFFICIAL_SCORING': 'BLOCKED_RESULT_TRANSFER_NOT_APPROVED',
        'FINAL_REPORT': 'NOT_STARTED',
    }
    return {'master_manifest_sha256': master['sha256'],
            'phase_order': list(PHASE_ORDER), 'phase_states': states,
            'pilot_cases_checkpointed': len(complete),
            'pilot_status': verified['status'],
            'official_score_status': 'NOT_AVAILABLE',
            'network_calls': 0, 'bigquery_jobs': 0,
            'ledger_path': 'results/restricted/phase_c2_state.sqlite'}


def main() -> None:
    state = checkpoint()
    output = ROOT / 'results/phase_c2_status.json'
    # A status snapshot may evolve, while the SQLite case ledger remains
    # immutable for completed case/artifact pairs.
    output.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n',
                      encoding='utf-8')
    print(json.dumps({'pilot_cases_checkpointed': state['pilot_cases_checkpointed'],
                      'official_score_status': state['official_score_status'],
                      'test_status': state['phase_states']['TEST_443']}))


if __name__ == '__main__':
    main()
