"""Score the two saved validation cohorts with the locked, row-free SQL rubric."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import json
import os
import sqlite3

from run import load_research_env
from ehrqa.cli.clinsql_rubric import LOCK, ROOT, SOURCE, build_cohort, file_hash, require_private
from ehrqa.cli.four_method_pilot import STATE, _private_acl, _scope
from ehrqa.clinsql.benchmark_model import BENCHMARK_LLM
from ehrqa.clinsql.official_scorer_source import count_judge_leaf_calls, load_verified_native_scorer
from ehrqa.clinsql.result_artifacts import ResultArtifactStore
from ehrqa.clinsql.rubric_evaluation import LeafLedger, create_scorer
from ehrqa.clinsql.rubric_judge import ADAPTED, ChatJudge, JudgeConfig, JudgeIncomplete, digest, parse_adapted_grade


LABEL = 'ADAPTED_JUDGE_GPT5MINI_2025_08_07'
PHASE = 'FOUR_METHOD_PILOT_5'


def saved_cohort(case_ids):
    methods, expiries = {}, []
    for method, directory, state in (
        ('clinsql_cot', STATE / 'clinsql_cot', STATE / 'state.sqlite'),
        ('sde_sql', STATE / 'sde_sql_uncapped/probe_continuation',
         STATE / 'sde_sql_uncapped/probe_continuation/state.sqlite'),
    ):
        require_private(directory)
        with sqlite3.connect(f'{state.as_uri()}?mode=ro', uri=True) as db:
            pins = dict(db.execute('SELECT case_id,artifact_sha256 FROM case_runs '
                                   'WHERE phase=? AND method=? AND status=?', (PHASE, method, 'EXECUTED')))
        entries = {}
        for path in directory.glob('*.json'):
            record = json.loads(path.read_bytes())
            case_id, sha = record['case_id'], file_hash(path)
            if (case_id not in case_ids or record['method'] != method or sha != pins.get(case_id)
                    or case_id in entries or not record.get('sql')):
                raise JudgeIncomplete('PREDICTION_CHECKPOINT_MISMATCH')
            expiries.append(datetime.fromisoformat(record['artifact_expires_at_utc']))
            entries[case_id] = {'format': 'four_method', 'prediction_path': path.relative_to(ROOT).as_posix(),
                                'prediction_sha256': sha, 'result_sha256': record['artifact']['sha256']}
        if set(entries) != set(case_ids):
            raise JudgeIncomplete('INCOMPLETE_SAVED_COHORT')
        methods[method] = entries
    rubrics = {case_id: {name: file_hash(SOURCE / 'data/splits/validation' / case_id / name)
                         for name in ('sql_rubric_tree.json', 'results_rubric_tree.json')}
               for case_id in case_ids}
    return {'split': 'validation', 'case_ids': case_ids, 'methods': methods,
            'rubric_sha256': rubrics}, min(expiries)


def ledger_usage(path):
    with sqlite3.connect(path) as db:
        rows = db.execute('SELECT status,metadata FROM attempts').fetchall()
    records = [json.loads(data) for _, data in rows]
    return {'leaf_attempts': len(rows), 'graded_leaves': sum(status == 'COMPLETE' for status, _ in rows),
            'input_tokens': sum(item.get('input_tokens') or 0 for item in records),
            'output_tokens': sum(item.get('output_tokens') or 0 for item in records),
            'cached_tokens': sum(item.get('cached_tokens') or 0 for item in records),
            'estimated_cost_usd': str(sum((Decimal(item.get('estimated_cost_usd') or '0')
                                           for item in records), Decimal(0)))}


def main():
    load_research_env(ROOT / '.env', os.environ)
    master, _, _, _ = _scope()
    manifest, expiry = saved_cohort(master['pilot_case_ids'])
    config = JudgeConfig(ADAPTED, BENCHMARK_LLM, 'https://api.openai.com/v1', BENCHMARK_LLM,
                         '0.25', '2.00', 'https://developers.openai.com/api/docs/models/gpt-5-mini',
                         cached_input_usd_per_million='0.025', adapted_max_completion_tokens=None)
    store = ResultArtifactStore(ROOT / 'results/restricted', verify_private_acl=_private_acl)
    work = store.root / ('rubric_sql_recovery_' + digest([manifest, config.sha256])[:16])
    work.mkdir(exist_ok=True)
    require_private(work)
    cohort = build_cohort(manifest, store, work, expiry)
    leaf_count = count_judge_leaf_calls(SOURCE, manifest['case_ids'])['sql_leaf_calls']
    load_verified_native_scorer(SOURCE, LOCK)
    ledger = LeafLedger(work / 'leaves.sqlite', max_calls=leaf_count * len(cohort) * 2, retry_limit=3,
                        grade_parser=parse_adapted_grade, retry_invalid_response=True,
                        retain_invalid_response=True)

    def authorize():
        if datetime.now(timezone.utc) >= expiry:
            raise JudgeIncomplete('RETENTION_SCOPE_EXCEEDED')
        if os.getenv('SEND_RESULTS_TO_LLM', '').lower() != 'false':
            raise JudgeIncomplete('RESULT_TRANSMISSION_MUST_STAY_DISABLED')

    authorize()
    judge = ChatJudge(config)
    output = work / 'scores.json'
    cohort_sha = digest(manifest)
    if output.is_file():
        previous = json.loads(output.read_bytes())
        preflight = previous['preflight']
        if (previous['judge_config_sha256'] != config.sha256 or previous['cohort_sha256'] != cohort_sha
                or preflight.get('returned_model') != config.model or not preflight.get('response_id')):
            raise JudgeIncomplete('CHECKPOINT_PREFLIGHT_MISMATCH')
        preflight_runs = previous.get('preflight_runs', [preflight])
        judge.verified = True  # Replay the verified synthetic receipt for this pinned configuration.
    else:
        # A synthetic snapshot probe sends neither dataset nor benchmark data.
        preflight = judge.verify()
        preflight_runs = [preflight]
    report = {'judge': LABEL, 'judge_config_sha256': config.sha256, 'parameters': config.parameters(),
              'cohort_sha256': cohort_sha, 'expires_at_utc': expiry.isoformat(),
              'preflight': preflight, 'preflight_runs': preflight_runs, 'cases': {}}

    def save():
        report['usage'] = ledger_usage(ledger.path)
        temp = output.with_suffix('.tmp')
        temp.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temp.replace(output)

    save()
    print(f'{LABEL} preflight PASS; target {leaf_count * len(cohort)} SQL leaves', flush=True)
    def grade_case(method, stage):
        scorer, _ = create_scorer(SOURCE, LOCK, judge, ledger, scope=method, authorize=authorize)
        outcome = {'execution_status': 'UNSCORED_DATA_EGRESS', 'execution_score': None}
        try:
            with stage() as sample:
                outcome['sql_score'] = scorer.score_sql_without_results(Path(sample))
            outcome['sql_status'] = 'GRADED'
        except (JudgeIncomplete, ValueError, KeyError, PermissionError, OSError) as exc:
            outcome.update(sql_score=None, sql_status=(str(exc) if isinstance(exc, JudgeIncomplete)
                                                       else 'STAGING_UNAVAILABLE'))
        return outcome

    report['cases'] = {method: {} for method in cohort}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(grade_case, method, stage): (method, case_id)
                   for method, cases in cohort.items() for case_id, stage in cases.items()}
        for future in as_completed(futures):
            method, case_id = futures[future]
            outcome = future.result()
            report['cases'][method][case_id] = outcome
            save()
            print(method, case_id, outcome['sql_status'], outcome['sql_score'], flush=True)
    return 0 if all(row['sql_status'] == 'GRADED' for cases in report['cases'].values()
                    for row in cases.values()) else 2


if __name__ == '__main__':
    raise SystemExit(main())
