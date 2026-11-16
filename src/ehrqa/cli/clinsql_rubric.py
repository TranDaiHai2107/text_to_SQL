"""Grade saved CLINSQL artifacts with an explicitly approved rubric judge."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
from uuid import uuid4

from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.evaluator import prepare_saved_run_sample
from ehrqa.clinsql.four_method_runner import stage_saved_prediction
from ehrqa.clinsql.official_scorer_source import SCORER_RELATIVE_PATH, load_verified_native_scorer
from ehrqa.clinsql.result_artifacts import ResultArtifactStore, verify_windows_private_acl
from ehrqa.clinsql.rubric_evaluation import LeafLedger, check_approval, create_scorer, evaluate_split
from ehrqa.clinsql.rubric_judge import ChatJudge, JudgeConfig, JudgeIncomplete, NATIVE, digest
from ehrqa.clinsql.experiment_state import METHODS


ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / 'external/clinsql_official'
LOCK = ROOT / 'PAPER_SOURCE_LOCK.json'


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def require_private(path):
    if not verify_windows_private_acl(path, allow_safe_inherited=True):
        raise PermissionError('Evaluation requires a verified private Windows ACL')


@contextmanager
def private_sample_directory(work):
    require_private(work)
    # On Windows, mkdtemp's mode 0700 can replace the verified inherited ACL.
    target = work / ('sample_' + uuid4().hex)
    target.mkdir()
    try:
        require_private(target)
        yield target
    finally:
        shutil.rmtree(target)


def build_cohort(manifest, store, work, staging_deadline):
    split = manifest['split']
    frozen = manifest.get('configuration_freeze_sha256', '')
    allow_test = bool(re.fullmatch(r'[a-f0-9]{64}', frozen))
    questions, _ = load_official_questions(SOURCE, split=split, allow_test=allow_test)
    by_id = {question.query_id: question for question in questions}
    case_ids = manifest['case_ids']
    if not case_ids or len(set(case_ids)) != len(case_ids) or not set(case_ids) <= by_id.keys():
        raise ValueError('Invalid expected cohort')
    entries = manifest['methods']
    if not entries or not set(entries) <= set(METHODS):
        raise ValueError('Unknown evaluation method')
    if split == 'test' and (set(case_ids) != by_id.keys() or set(entries) != set(METHODS)):
        raise ValueError('Test scoring requires all three primary methods and the complete frozen cohort')

    @contextmanager
    def stage(method, case_id):
        row = entries[method][case_id]
        path = (ROOT / row['prediction_path']).resolve()
        if not path.is_relative_to(ROOT / 'results') or file_hash(path) != row['prediction_sha256']:
            raise JudgeIncomplete('PREDICTION_HASH_MISMATCH')
        record = load_json(path)
        question = by_id[case_id]
        with private_sample_directory(work) as target:
            if row['format'] == 'phase_c1' and method == 'clinsql_cot' and split == 'validation':
                refs = [event for event in record['events'] if event['stage'] == 'result_artifact']
                if len(refs) != 1 or refs[0]['sha256'] != row['result_sha256']:
                    raise JudgeIncomplete('RESULT_REFERENCE_MISMATCH')
                ref = refs[0]
                expiry = ref['artifact_expires_at_utc']
                if staging_deadline > datetime.fromisoformat(expiry):
                    raise JudgeIncomplete('RETENTION_SCOPE_EXCEEDED')
                sample = prepare_saved_run_sample(path, target, SOURCE, question, result_store=store,
                                                  artifact_id=ref['artifact_id'], artifact_sha256=ref['sha256'])
            elif row['format'] == 'four_method' and record['method'] == method:
                if record['artifact']['sha256'] != row['result_sha256']:
                    raise JudgeIncomplete('RESULT_REFERENCE_MISMATCH')
                if staging_deadline > datetime.fromisoformat(record['artifact_expires_at_utc']):
                    raise JudgeIncomplete('RETENTION_SCOPE_EXCEEDED')
                sample = stage_saved_prediction(record, question, store=store, root=target, benchmark_root=SOURCE)
            else:
                raise JudgeIncomplete('UNSUPPORTED_PREDICTION_FORMAT')
            for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
                if file_hash(sample / name) != manifest['rubric_sha256'][case_id][name]:
                    raise JudgeIncomplete('RUBRIC_HASH_MISMATCH')
            yield sample

    return {method: {case_id: lambda m=method, c=case_id: stage(m, c) for case_id in case_ids}
            for method in entries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['config-hash', 'pilot-manifest', 'run'])
    parser.add_argument('--config', type=Path)
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--approval', type=Path)
    args = parser.parse_args()
    if args.action == 'pilot-manifest':
        from ehrqa.clinsql.pilot_cases import verify_pilot_cases
        pilot = verify_pilot_cases(ROOT / 'data/clinsql/pilot_5_validation_development_v1.json', SOURCE)
        audit = load_json(ROOT / 'results/phase_c1_pilot_audit.json')
        case_ids = [row['case_id'] for row in pilot['cases']]
        if pilot['sha256'] != audit['pilot_manifest_sha256'] or set(case_ids) != audit['cases'].keys():
            raise ValueError('Saved audit differs from the frozen pilot')
        entries, rubrics = {}, {}
        for case_id in case_ids:
            row = audit['cases'][case_id]
            path = Path(row['run_log']).resolve()
            entries[case_id] = {'format': 'phase_c1', 'prediction_path': path.relative_to(ROOT).as_posix(),
                                'prediction_sha256': file_hash(path), 'result_sha256': row['artifact_sha256']}
            case_dir = SOURCE / 'data/splits/validation' / case_id
            rubrics[case_id] = {name: file_hash(case_dir / name) for name in
                               ('sql_rubric_tree.json', 'results_rubric_tree.json')}
        print(json.dumps({'split': 'validation', 'case_ids': case_ids, 'rubric_sha256': rubrics,
                          'methods': {'clinsql_cot': entries}}, indent=2))
        return 0
    if not args.config:
        parser.error('this action requires --config')
    config = JudgeConfig(**load_json(args.config))
    config.validate()
    if args.action == 'config-hash':
        print(config.sha256)
        return 0
    if not args.approval or not args.manifest:
        parser.error('run requires --manifest and --approval')
    approval, manifest = load_json(args.approval), load_json(args.manifest)
    manifest_hash = file_hash(args.manifest)
    source_hash = file_hash(SOURCE / SCORER_RELATIVE_PATH)
    load_verified_native_scorer(SOURCE, LOCK)

    def authorize():
        if os.getenv('SEND_RESULTS_TO_LLM', '').lower() != 'true':
            raise JudgeIncomplete('RESULT_TRANSMISSION_DISABLED')
        check_approval(approval, config=config, manifest_hash=manifest_hash, source_hash=source_hash)

    authorize()
    store = ResultArtifactStore(ROOT / 'results/restricted')
    require_private(store.root)
    work = store.root / ('rubric_' + digest([manifest_hash, config.sha256])[:20])
    work.mkdir(exist_ok=True)
    require_private(work)
    expiry = datetime.fromisoformat(approval['expires_at_utc'])
    cohorts = build_cohort(manifest, store, work, expiry)
    retention_path = work / 'retention.json'
    retention = {'expires_at_utc': expiry.isoformat(), 'manifest_sha256': manifest_hash,
                 'judge_config_sha256': config.sha256}
    if retention_path.exists():
        if load_json(retention_path) != retention:
            raise JudgeIncomplete('CHECKPOINT_RETENTION_MISMATCH')
    else:
        retention_path.write_text(json.dumps(retention), encoding='utf-8')
    ledger = LeafLedger(work / 'leaves.sqlite', max_calls=approval['max_leaf_requests'])
    judge = ChatJudge(config)
    try:
        preflight = judge.verify()
    except Exception:
        print('NATIVE_JUDGE_UNAVAILABLE' if config.mode == NATIVE else 'ADAPTED_JUDGE_UNAVAILABLE')
        return 2
    with (work / 'preflight_usage.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps({'at_utc': datetime.now(timezone.utc).isoformat(),
                                 'judge_config_sha256': config.sha256, **preflight}) + '\n')
    reports = []
    for method, cohort in cohorts.items():
        scorer, module = create_scorer(SOURCE, LOCK, judge, ledger, scope=method, authorize=authorize)
        reports.append(evaluate_split(scorer, module, cohort, split=manifest['split'],
                                      method=method, judge_config=config))
    print(json.dumps(reports, indent=2))
    return 0 if all(report['status'] == 'COMPLETE' for report in reports) else 2


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except JudgeIncomplete as exc:
        raise SystemExit(str(exc)) from None
