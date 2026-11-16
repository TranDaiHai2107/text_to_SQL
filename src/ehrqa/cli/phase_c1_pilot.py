"""Plan offline; execute exactly one approved CLINSQL validation case."""
from __future__ import annotations

import argparse

from ehrqa.clinsql.benchmark_model import BENCHMARK_LLM, require_benchmark_model
from decimal import Decimal
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys

from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
from ehrqa.clinsql.benchmark_backend import make_benchmark_database
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.cot import generation_prompt
from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.execution_budget import PersistentSQLBudgetLedger, SQLBudgetLimits
from ehrqa.clinsql.execution_control import verify_reader_adc
from ehrqa.clinsql.execution_modes import BenchmarkExecutionConfig
from ehrqa.clinsql.metadata import schema_records_from_manifest, verify_schema_manifest
from ehrqa.clinsql.openai_provider import OpenAIModelProvider
from ehrqa.clinsql.pilot_api_budget import PersistentAPIBudgetLedger, PilotAPIBudget
from ehrqa.clinsql.pilot_cases import verify_pilot_cases
from ehrqa.clinsql.real_cot_runner import run_real_cot_case, load_real_cot_checkpoint
from ehrqa.clinsql.result_artifacts import ResultArtifactStore
from ehrqa.clinsql.schema_index import SchemaIndex
from ehrqa.clinsql.evaluator import prepare_saved_run_sample
from ehrqa.clinsql.pilot_retention import inspect_or_delete_expired
from ehrqa.text2sql.logging import Pricing

ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / 'external/clinsql_official'
PILOT = ROOT / 'data/clinsql/pilot_5_validation_development_v1.json'
MANIFEST = ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json'
INDEX = ROOT / 'data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json'
HISTORICAL_PILOT = 'HISTORICAL_PILOT'
SOURCE_ALIGNED_NEXT_RUN = 'SOURCE_ALIGNED_NEXT_RUN'
PROFILES = (HISTORICAL_PILOT, SOURCE_ALIGNED_NEXT_RUN)


def _run_root(api_budget_sha256: str, approval_id: str | None = None,
              *, profile=HISTORICAL_PILOT) -> Path:
    if len(api_budget_sha256) != 64:
        raise ValueError('Pinned API budget SHA-256 required for run directory')
    suffix = f'_{approval_id}' if approval_id is not None else ''
    if approval_id is not None and not re.fullmatch(r'[A-Za-z0-9_-]+', approval_id):
        raise ValueError('Unsafe approval identifier for run directory')
    prefix = 'phase_c1_runs_source_aligned' if profile == SOURCE_ALIGNED_NEXT_RUN else 'phase_c1_runs'
    return ROOT / 'results' / f'{prefix}_{api_budget_sha256[:12]}{suffix}'


def _profile_request_settings(profile, api):
    if profile == SOURCE_ALIGNED_NEXT_RUN:
        if api['max_output_tokens_per_call'] != 2048:
            raise ValueError('Source-aligned CoT requires max_output_tokens=2048')
        return {'max_output_tokens': 2048, 'reasoning_effort': None}
    if profile != HISTORICAL_PILOT:
        raise ValueError('Unknown CoT experiment profile')
    return {'max_output_tokens': api['max_output_tokens_per_call'],
            'reasoning_effort': os.environ.get('OPENAI_REASONING_EFFORT')}


def _load_scope():
    pilot = verify_pilot_cases(PILOT, BENCHMARK)
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    verify_schema_manifest(manifest)
    index = SchemaIndex.load(INDEX, manifest)
    return pilot, manifest, index


def plan(api_budget_path: Path | None = None, sql_budget_path: Path | None = None,
         *, profile=HISTORICAL_PILOT) -> dict:
    pilot, manifest, index = _load_scope()
    questions, _ = load_official_questions(BENCHMARK)
    by_id = {q.query_id: q for q in questions}
    schema_text = '\n'.join(r['ddl'] for r in schema_records_from_manifest(manifest))
    cases = []
    for row in pilot['cases']:
        prompt = generation_prompt(by_id[row['case_id']].text, schema_text)
        cases.append({'case_id': row['case_id'], 'difficulty': row['difficulty'],
                      'question_sha256': row['question_sha256'],
                      'generation_prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                      'input_token_upper_bound': len(prompt.encode('utf-8')) + 128})
    output = {'mode': 'PLAN_ONLY', 'profile': profile, 'pilot_manifest_sha256': pilot['sha256'],
            'schema_manifest_sha256': manifest['sha256'],
            'schema_index_sha256': index.index['sha256'],
            'model_id': BENCHMARK_LLM, 'cases': cases,
            'max_inference_calls_if_all_refine_twice': 15,
            'api_key_present': bool(os.environ.get('OPENAI_API_KEY')),
            'bigquery_patient_queries_executed': 0, 'openai_requests_sent': 0}
    if api_budget_path is not None and sql_budget_path is not None:
        api_config, _, api_budget, sql_limits, execution, api_sha, sql_sha = _read_budgets(
            api_budget_path, sql_budget_path)
        output['model_id'] = api_config['model_id']
        output['request_settings'] = _profile_request_settings(profile, api_config)
        maximum_sql_bytes = min(sql_limits.max_bytes_per_experiment,
                                5 * sql_limits.max_calls_per_question * execution.max_bytes_billed)
        output['budget_preview'] = {
            'api_budget_sha256': api_sha, 'sql_budget_sha256': sql_sha,
            'api_policy': api_budget.policy,
            'maximum_approved_api_cost_usd': (
                str(api_budget.max_cost_usd) if api_budget.max_cost_usd is not None else None),
            'cost_at_full_token_caps_usd': str(api_budget.cost(
                api_budget.max_input_tokens, api_budget.max_output_tokens)),
            'maximum_sql_bytes_billed': maximum_sql_bytes,
            'on_demand_sql_cost_at_bytes_cap_usd': str(
                Decimal(maximum_sql_bytes) * Decimal('6.25') / Decimal(2**40)),
            'sql_price_source': 'https://cloud.google.com/bigquery/pricing',
            'note': 'Estimates before free tier, billing plan and tax; dry-run only after approved SQL exists.'}
    return output


def _read_budgets(api_path: Path, sql_path: Path):
    api_raw, sql_raw = api_path.read_bytes(), sql_path.read_bytes()
    api, sql = json.loads(api_raw), json.loads(sql_raw)
    required_api = {'model_id', 'max_calls', 'max_input_tokens', 'max_output_tokens',
                    'max_cost_usd', 'input_per_million_usd', 'output_per_million_usd',
                    'pricing_source', 'max_output_tokens_per_call', 'timeout_seconds'}
    required_sql = {'max_calls_per_question', 'max_probes_per_question',
                    'max_bytes_per_question', 'max_bytes_per_experiment',
                    'max_bytes_billed_per_sql', 'timeout_seconds', 'max_rows',
                    'max_result_bytes'}
    if set(api) not in (required_api, required_api | {'policy'}) or set(sql) != required_sql:
        raise ValueError('Budget file fields differ from Phase C.1 schema')
    if api['model_id'] != BENCHMARK_LLM:
        raise ValueError('Pilot must use requested GPT-5-mini')
    if api['pricing_source'] != 'https://developers.openai.com/api/docs/models/gpt-5-mini':
        raise ValueError('Official GPT-5-mini pricing source required')
    if (Decimal(str(api['input_per_million_usd'])) != Decimal('0.25') or
        Decimal(str(api['output_per_million_usd'])) != Decimal('2.00')):
        raise ValueError('GPT-5-mini rate differs from verified official model page; recheck pricing')
    cap = api['max_cost_usd']
    api_budget = PilotAPIBudget(api['max_calls'], api['max_input_tokens'],
                                api['max_output_tokens'],
                                None if cap is None else Decimal(str(cap)),
                                Decimal(str(api['input_per_million_usd'])),
                                Decimal(str(api['output_per_million_usd'])),
                                api.get('policy', 'CAPPED'))
    sql_limits = SQLBudgetLimits(sql['max_calls_per_question'], sql['max_probes_per_question'],
                                  sql['max_bytes_per_question'], sql['max_bytes_per_experiment'])
    execution = BenchmarkExecutionConfig(sql['max_bytes_billed_per_sql'],
                                         sql['timeout_seconds'], sql['max_rows'],
                                         sql['max_result_bytes'])
    if (not 16 <= api['max_output_tokens_per_call'] <= 128000 or
        api_budget.max_calls < 15 or
        api_budget.max_output_tokens < 15 * api['max_output_tokens_per_call'] or
        sql_limits.max_calls_per_question < 3 or
        sql_limits.max_bytes_per_question < 3 * execution.max_bytes_billed):
        raise ValueError('Budgets must support all three native CoT attempts')
    api_budget.verify_active()
    return api, sql, api_budget, sql_limits, execution, hashlib.sha256(api_raw).hexdigest(), hashlib.sha256(sql_raw).hexdigest()


def execute_one(case_id: str, *, approval_path: Path, api_budget_path: Path,
                sql_budget_path: Path, profile=HISTORICAL_PILOT) -> dict:
    pilot, manifest, index = _load_scope()
    api, sql, budget, sql_limits, execution, api_sha, sql_sha = _read_budgets(
        api_budget_path, sql_budget_path)
    request_settings = _profile_request_settings(profile, api)
    approval = BenchmarkExecutionApproval.from_file(approval_path)
    approval.verify_pilot(pilot)
    approval.verify_active()
    if (approval.api_budget_sha256 != api_sha or approval.sql_budget_sha256 != sql_sha or
        approval.model_id != api['model_id'] or
        approval.max_bytes_billed_per_sql != execution.max_bytes_billed or
        approval.timeout_seconds != execution.timeout_seconds or
        approval.max_rows != execution.max_rows or
        approval.max_result_bytes != execution.max_result_bytes or
        case_id not in approval.case_ids):
        raise PermissionError('Approval, model, budget or case differs from pinned pilot')
    if not os.environ.get('OPENAI_API_KEY'):
        raise RuntimeError('OPENAI_API_KEY is unavailable; no paid request was sent')
    require_benchmark_model(os.environ.get('OPENAI_MODEL'))
    if os.environ.get('SEND_RESULTS_TO_LLM', '').lower() != 'false':
        raise PermissionError('Patient results must not be sent to the LLM')
    store = ResultArtifactStore(ROOT / 'results/restricted')
    if not store.verify_private_acl(store.root):
        raise PermissionError('Restricted storage ACL is not verified')
    verify_reader_adc()
    source_check = subprocess.run([sys.executable, str(ROOT / 'paper_sources.py')],
                                  cwd=ROOT, capture_output=True, text=True, timeout=30)
    if source_check.returncode != 0:
        raise RuntimeError('Locked paper source verification failed')
    config = BigQueryConfig.from_env()
    if (config.project_id != approval.project_id or config.location.upper() != 'US' or
        set(config.allowed_datasets) != set(approval.datasets)):
        raise PermissionError('BigQuery environment differs from approval')
    questions, _ = load_official_questions(BENCHMARK)
    question = next(q for q in questions if q.query_id == case_id)
    output_root = _run_root(api_sha, approval.approval_id, profile=profile)
    state = ROOT / 'results/restricted/phase_c1_state'
    state.mkdir(parents=True, exist_ok=True)
    api_ledger = PersistentAPIBudgetLedger(
        state / f'api_{api_sha[:12]}_{approval.approval_id}.sqlite', budget)
    sql_ledger = PersistentSQLBudgetLedger(state / 'sql.sqlite', sql_limits)
    model = OpenAIModelProvider(api_ledger, model_id=api['model_id'],
                                timeout_seconds=api['timeout_seconds'], **request_settings)
    database = make_benchmark_database(config, manifest, index, execution,
                                       case_id=case_id, ledger=sql_ledger,
                                       approval=approval)
    code_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
                                          cwd=ROOT, text=True).strip()
    return run_real_cot_case(question, pilot_manifest=pilot, approval=approval,
                             model=model, database=database, schema_index=index,
                             result_store=store, output_root=output_root,
                             model_id=api['model_id'],
                             pricing=Pricing(float(budget.input_per_million_usd),
                                             float(budget.output_per_million_usd)),
                             code_commit=code_commit,
                             api_budget_sha256=api_sha, sql_budget_sha256=sql_sha,
                             source_aligned=profile == SOURCE_ALIGNED_NEXT_RUN)


def execute_batch(*, approval_path: Path, api_budget_path: Path,
                  sql_budget_path: Path, profile=HISTORICAL_PILOT) -> dict:
    """Run the pinned five sequentially; never replay a started case."""
    pilot, _, index = _load_scope()
    api_sha = hashlib.sha256(api_budget_path.read_bytes()).hexdigest()
    approval = BenchmarkExecutionApproval.from_file(approval_path)
    approval.verify_pilot(pilot)
    approval.verify_active()
    output_root = _run_root(api_sha, approval.approval_id, profile=profile)
    questions, _ = load_official_questions(BENCHMARK)
    by_id = {q.query_id: q for q in questions}
    completed = []
    for row in pilot['cases']:
        case_id = row['case_id']
        path = output_root / (case_id.replace('/', '__') + '.json')
        marker = path.with_suffix('.started')
        if marker.exists():
            checkpoint = load_real_cot_checkpoint(
                by_id[case_id], pilot_manifest=pilot, schema_index=index,
                output_root=output_root)
            completed.append({'case_id': case_id, 'status': checkpoint['status'],
                              'source': 'checkpoint'})
            continue
        if path.exists():
            raise ValueError('Prediction exists without start marker; inspect manually')
        outcome = execute_one(case_id, approval_path=approval_path,
                              api_budget_path=api_budget_path,
                              sql_budget_path=sql_budget_path,
                              **({'profile': profile} if profile != HISTORICAL_PILOT else {}))
        completed.append({'case_id': case_id, 'status': outcome['status'],
                          'source': 'new_execution'})
    return {'phase': 'PILOT_5', 'completed': completed,
            'case_count': len(completed)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    planned = sub.add_parser('plan')
    planned.add_argument('--api-budget', type=Path)
    planned.add_argument('--sql-budget', type=Path)
    resume = sub.add_parser('resume')
    resume.add_argument('--case-id', required=True)
    resume.add_argument('--api-budget', type=Path)
    resume.add_argument('--approval', type=Path)
    stage = sub.add_parser('stage')
    stage.add_argument('--case-id', required=True)
    stage.add_argument('--api-budget', type=Path)
    stage.add_argument('--approval', type=Path)
    retention = sub.add_parser('retention')
    retention.add_argument('--delete-expired', action='store_true')
    run = sub.add_parser('execute')
    run.add_argument('--case-id', required=True)
    run.add_argument('--approval', type=Path, required=True)
    run.add_argument('--api-budget', type=Path, required=True)
    run.add_argument('--sql-budget', type=Path, required=True)
    run.add_argument('--execute-approved', action='store_true')
    batch = sub.add_parser('execute-batch')
    batch.add_argument('--approval', type=Path, required=True)
    batch.add_argument('--api-budget', type=Path, required=True)
    batch.add_argument('--sql-budget', type=Path, required=True)
    batch.add_argument('--execute-approved', action='store_true')
    for command in (planned, resume, stage, run, batch):
        command.add_argument('--profile', choices=PROFILES, default=HISTORICAL_PILOT)
    args = parser.parse_args(argv)
    if args.mode == 'plan':
        if (args.api_budget is None) != (args.sql_budget is None):
            raise ValueError('Provide both budget files for a cost preview')
        print(json.dumps(plan(args.api_budget, args.sql_budget, profile=args.profile), ensure_ascii=False, indent=2))
        return 0
    if args.mode == 'retention':
        roots = [ROOT / 'results/phase_c1_runs',
                 *sorted((ROOT / 'results').glob('phase_c1_runs_*'))]
        records = [record for root in roots if root.is_dir()
                   for record in inspect_or_delete_expired(
                       root, ROOT / 'results/restricted',
                       delete_expired=args.delete_expired)]
        print(json.dumps(records, ensure_ascii=False, indent=2))
        return 0
    if args.mode in {'resume', 'stage'}:
        if args.profile == SOURCE_ALIGNED_NEXT_RUN and not args.api_budget:
            raise ValueError('Source-aligned checkpoint lookup requires its pinned API budget')
        pilot, _, index = _load_scope()
        questions, _ = load_official_questions(BENCHMARK)
        question = next(q for q in questions if q.query_id == args.case_id)
        if args.approval and not args.api_budget:
            raise ValueError('Versioned resume requires both approval and API budget')
        approval_id = (BenchmarkExecutionApproval.from_file(args.approval).approval_id
                       if args.approval else None)
        output_root = (_run_root(hashlib.sha256(args.api_budget.read_bytes()).hexdigest(),
                                 approval_id, profile=args.profile)
                       if args.api_budget else ROOT / 'results/phase_c1_runs')
        checkpoint = load_real_cot_checkpoint(
            question, pilot_manifest=pilot, schema_index=index,
            output_root=output_root)
        if args.mode == 'resume':
            print(json.dumps(checkpoint, ensure_ascii=False, default=str))
            return 0
        if checkpoint['status'] != 'executed' or not checkpoint['artifact']:
            raise ValueError('Only a complete executed prediction can be staged')
        store = ResultArtifactStore(ROOT / 'results/restricted')
        if not store.verify_private_acl(store.root):
            raise PermissionError('Restricted storage ACL is not verified')
        artifact = checkpoint['artifact']
        target = prepare_saved_run_sample(
            Path(checkpoint['log_path']), ROOT / 'results/restricted/phase_c1_staged',
            BENCHMARK, question, result_store=store,
            artifact_id=artifact['artifact_id'], artifact_sha256=artifact['sha256'])
        print(json.dumps({'mode': 'STAGED_ONLY_NO_JUDGE', 'case_id': args.case_id,
                          'path': str(target)}, ensure_ascii=False))
        return 0
    if not args.execute_approved:
        raise PermissionError('Explicit --execute-approved required; plan mode sends no requests')
    if args.mode == 'execute-batch':
        print(json.dumps(execute_batch(approval_path=args.approval,
                                       api_budget_path=args.api_budget,
                                       sql_budget_path=args.sql_budget, profile=args.profile),
                         ensure_ascii=False, default=str))
        return 0
    print(json.dumps(execute_one(args.case_id, approval_path=args.approval,
                                 api_budget_path=args.api_budget,
                                 sql_budget_path=args.sql_budget, profile=args.profile), ensure_ascii=False, default=str))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
