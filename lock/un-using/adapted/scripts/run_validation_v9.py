"""CLINSQL validation run v9 (190 questions): Ours v9 and CLINSQL CoT on all questions; CoT and SDE-SQL complete
the questions the v6 attempt did not finish. Completed v6 baseline predictions are imported
unchanged (same code, model, prompts and scorer), so every method covers the same 190 questions.

Ours v8 lite = v7 fixes (decompose fail-open, validator star expansion and composite-key
lineage, tolerant selector audits, reference-patient coverage) + a cost-bounded flow borrowed
from CLINSQL: no decomposer, one full-schema candidate, a second independent candidate only when
the first fails or returns no values, no LLM selector. Same model and reasoning effort as the baselines.

Scope is validation only (152 development + 38 internal-check). The 443-question
test split is never loaded. Every method uses gpt-5-mini-2025-08-07 with the same
bounded transport retry, the same BigQuery reader/limits and result-row egress
disabled.

Authorization: the experiment lead chose option A on 2026-11-17 (fix Ours, re-run Ours on
190, finish the baselines; OpenAI total raised to <= USD 75 incl. judge across all validation
attempts; BigQuery <= 14 TiB
in a dedicated validation ledger; valid until the current credit/price evidence
expires). The operational limits (reader principal, per-SQL bytes cap, timeout,
retention, IAM risk acceptance) are copied unchanged from the Task 8 Ours approval.

Scoring per prediction, right after inference:
* Tier 1 - deterministic execution accuracy vs the gold result CSV (local, no model).
* Tier 2 - CLINSQL rubric SQL Score with the adapted gpt-5-mini judge (``medium``
  default effort, config SHA 129e16b6...), SQL tree only, no result rows sent.
  A prediction with SQL but no executed result is SQL-scored (results 0); a
  prediction without SQL scores 0. Infrastructure failures are censored (not
  scored) and can be re-run with ``--retry-blocked``.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT), str(ROOT / 'scripts')]

from run import load_research_env  # noqa: E402

METHODS = ('clinsql_cot', 'sde_sql', 'ours')
PROFILE = 'validation_v9'
PHASE = 'validation_v9_190'
VALIDATION_COUNT = 190
TIB = 1024 ** 4
# Option A (2026-11-17): OpenAI <= USD 75 total incl. judge across validation attempts,
# BigQuery <= 14 TiB. Spend of earlier attempts (pending reservations at their cap) is
# subtracted so the totals hold across attempts.
V6_ROOT = 'validation_v6_503b7c46d4b79ffd'
PRIOR_ATTEMPT = {'roots': ['validation_v6_4e1d29417c303881', V6_ROOT, 'validation_v7_60538e946ca2627c',
                           'validation_v8_c823cd29f135915e', 'validation_v8_618166a07b87f512',
                           'validation_v8_14eaca67d21ff058'],
                 'openai_usd': '46.16',
                 'bigquery_bytes': 25_590_497_280 + 5_320_702_164_992 + 8_263_827_456 + 26_159_874_048
                                   + 34_633_416_704 + 27_727_495_168,
                 'stop_reason': 'v8 pruned-schema 20-question pilot (ablation): RAG scope missed gold tables; '
                                'this attempt uses the full schema'}
# CoT is re-run on all 190 questions with the shared 32k output cap (the v6 adapter capped it at
# 8192 tokens; the source sets none); only unaffected SDE-SQL predictions are imported.
IMPORTED_METHODS = ('sde_sql',)
# One output cap for every method: above OpenAI's >= 25k recommendation for reasoning models and
# far above observed outputs (3-6k); it bounds per-call budget reservations under concurrency.
OUTPUT_CAP = 32768
OURS_FLAGS = None  # set in build(): ProposedFlags(adaptive_single=True)
CAPS = {
    'openai_usd_total': '28.84',
    'openai_usd_by_method': {'ours': '7', 'sde_sql': '8.8', 'clinsql_cot': '3'},
    'judge_max_leaf_calls': 5150,
    'bigquery_bytes_total': 14 * TIB - PRIOR_ATTEMPT['bigquery_bytes'],
    'bigquery_bytes_per_question': 1 * TIB,
    'bigquery_calls_per_question': 256,
}
API_CALLS = {'ours': VALIDATION_COUNT * 16, 'sde_sql': VALIDATION_COUNT * 16, 'clinsql_cot': VALIDATION_COUNT * 4}
INFRASTRUCTURE = {'INCOMPLETE_RESULT', 'PERMISSION_DENIED', 'BUDGET_EXCEEDED', 'RESOURCE_BUDGET_BLOCKED',
                  'TIMEOUT', 'INFRASTRUCTURE_ERROR', 'MODEL_REQUEST_OUTCOME_UNKNOWN', 'MODEL_USAGE_UNKNOWN',
                  'RESTRICTED_EVIDENCE_EGRESS', 'MODEL_MISMATCH'}
STOP_FAILURES = {'BUDGET_EXCEEDED', 'RESOURCE_BUDGET_BLOCKED', 'PERMISSION_DENIED', 'MODEL_MISMATCH'}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pin_json(path: Path, data) -> str:
    content = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode('utf-8')
    if path.exists():
        if path.read_bytes() != content:
            raise PermissionError(f'Existing pinned file differs: {path.name}')
    else:
        with path.open('xb') as stream:
            stream.write(content)
    return sha(content)


def atomic_json(path: Path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    temporary.replace(path)


def build(args):
    from ehrqa.agentic.trace import digest
    from ehrqa.cli import four_method_pilot as cli
    from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
    from ehrqa.clinsql.dataset import load_official_questions
    from ehrqa.clinsql.metadata import verify_schema_manifest
    from ehrqa.clinsql.public_terminology import PublicClinicalCatalog
    from ehrqa.clinsql.retrieval_manifest import FROZEN_CORPUS_SHA256, load_frozen_fewshot_index
    from ehrqa.clinsql.rubric_judge import ADAPTED, JudgeConfig
    from ehrqa.clinsql.schema_index import SchemaIndex
    from score_clinsql_recovery import LABEL

    benchmark = ROOT / 'external/clinsql_official'
    master = cli.read_json(ROOT / 'data/clinsql/master_experiment_pre_freeze_v2.json')
    historical = cli.read_json(ROOT / 'data/clinsql/master_experiment_pre_freeze_v1.json')
    cli.verify_pre_freeze_manifest(master)
    manifest = cli.read_json(ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json')
    verify_schema_manifest(manifest)
    index = SchemaIndex.load(ROOT / 'data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json', manifest)
    if master['schema_sha256'] != manifest['sha256'] or master['schema_index_sha256'] != index.index['sha256']:
        raise PermissionError('Schema differs from the pinned experiment')
    fewshot = load_frozen_fewshot_index(ROOT / 'data/clinsql/retrieval/fewshot_development_v1.json', historical)
    catalog = PublicClinicalCatalog(ROOT / 'data/clinsql/public_terminology')
    questions, validation_sha = load_official_questions(benchmark, split='validation')
    if len(questions) != VALIDATION_COUNT or validation_sha != master['validation_question_tree_sha256']:
        raise PermissionError('Validation cohort differs from the experiment')
    partition = {**{c: 'development' for c in master['development_case_ids']},
                 **{c: 'internal_check' for c in master['internal_check_case_ids']}}
    if set(partition) != {q.query_id for q in questions}:
        raise PermissionError('Partition does not cover the validation cohort')
    cot_api = cli.read_json(ROOT / 'docs/PHASE_C1_API_BUDGET_V2.json')
    cot_options = {'max_output_tokens': OUTPUT_CAP, 'reasoning_effort': 'medium',
                   'timeout_seconds': 180, 'transport_retries': 2}
    judge_cfg = JudgeConfig(ADAPTED, cli.MODEL, 'https://api.openai.com/v1', cli.MODEL, '0.25', '2.00',
                            'https://developers.openai.com/api/docs/models/gpt-5-mini',
                            cached_input_usd_per_million='0.025', adapted_max_completion_tokens=None)
    code = {name: cli.sha256_file(ROOT / name) for name in (
        'src/ehrqa/agentic/pipeline.py', 'src/ehrqa/agentic/contracts.py', 'src/ehrqa/agentic/schema.py',
        'src/ehrqa/agentic/prompts.py', 'src/ehrqa/clinsql/proposed.py', 'src/ehrqa/clinsql/openai_provider.py',
        'src/ehrqa/clinsql/chat_multi_provider.py', 'src/ehrqa/clinsql/clinical_catalog.py',
        'src/ehrqa/clinsql/four_method_runner.py', 'scripts/run_validation_v9.py')}
    global OURS_FLAGS
    from ehrqa.clinsql.proposed import ProposedFlags
    OURS_FLAGS = ProposedFlags(adaptive_single=True)
    scope = {'profile': PROFILE, 'phase': PHASE, 'model': cli.MODEL, 'methods': list(METHODS),
             'split': 'validation', 'validation_question_sha256': validation_sha, 'test_loaded': False,
             'schema_sha256': manifest['sha256'], 'index_sha256': index.index['sha256'],
             'master_sha256': master['sha256'], 'public_corpus_sha256': catalog.sha256,
             'few_shot_sha256': FROZEN_CORPUS_SHA256, 'cot_settings': cot_options,
             'sde': 'grouped_3x3_uncapped', 'ours': 'v9_lite_full_schema_clinsql_conventions', 'prompt_version': 'mimic_iv31_full_agentic_20261118_v9', 'max_output_tokens_all_methods': OUTPUT_CAP, 'imported_v6': list(IMPORTED_METHODS),
             'baseline_adapter_fixes': ['sde_guard_rejection_as_feedback', 'cot_shared_whitelisted_error_classes',
                                        'cot_output_cap_32768_was_8192'],
             'transport_retries': 2, 'judge': LABEL, 'judge_config_sha256': judge_cfg.sha256,
             'results_egress': False, 'caps': CAPS, 'prior_attempt': PRIOR_ATTEMPT, 'code_sha256': code}
    return SimpleNamespace(cli=cli, digest=digest, BenchmarkExecutionApproval=BenchmarkExecutionApproval,
                           benchmark=benchmark, manifest=manifest, index=index, fewshot=fewshot,
                           catalog=catalog, questions=questions, partition=partition,
                           cot_options=cot_options, judge_cfg=judge_cfg, scope=scope,
                           scope_hash=digest(scope))


def run(args):
    ctx = build(args)
    cli = ctx.cli
    print(json.dumps({'scope_sha256': ctx.scope_hash, 'questions': len(ctx.questions),
                      'tasks': len(ctx.questions) * len(METHODS), 'caps': CAPS}), flush=True)
    if not args.execute:
        return 0
    from ehrqa.clinsql.benchmark_backend import make_benchmark_database
    from ehrqa.clinsql.chat_multi_provider import OpenAIChatMultiProvider
    from ehrqa.clinsql.cot_runner import ClinSQLCoT
    from ehrqa.clinsql.evaluator import prepare_official_sample
    from ehrqa.clinsql.execution_budget import PersistentSQLBudgetLedger, SQLBudgetLimits
    from ehrqa.clinsql.execution_errors import IncompleteResultError
    from ehrqa.clinsql.execution_modes import BenchmarkExecutionConfig
    from ehrqa.clinsql.four_method_runner import _StopOnSecurityViolation, _failure, execute_method
    from ehrqa.clinsql.openai_provider import ModelGenerationFailure, OpenAIModelProvider
    from ehrqa.clinsql.pilot_api_budget import PersistentAPIBudgetLedger, PilotAPIBudget
    from ehrqa.clinsql.public_terminology import PublicTerminologyModelProvider
    from ehrqa.clinsql.real_cot_runner import _CaptureCompleteExecution
    from ehrqa.clinsql.rubric_evaluation import LeafLedger, create_scorer
    from ehrqa.clinsql.rubric_judge import ChatJudge, JudgeIncomplete, parse_adapted_grade
    from ehrqa.cli.clinsql_rubric import LOCK, private_sample_directory
    from ehrqa.text2sql.logging import MeteredDatabase, MeteredModel, Pricing, RunLog
    from score_execution_accuracy import ex_relaxed, ex_strict, reference

    if os.environ.get('SEND_RESULTS_TO_LLM', '').lower() != 'false':
        raise PermissionError('Result row transmission must remain disabled')
    cli.require_benchmark_model(os.environ.get('OPENAI_MODEL'))
    store = cli.ResultArtifactStore(ROOT / 'results/restricted', verify_private_acl=cli._private_acl)
    evidence = store.root / 'four_method_pilot/task8_20261115'
    prior = cli.FourMethodApproval.from_file(evidence / 'ours_approval_20261122_0900.json')
    config = cli.BigQueryConfig.from_env()
    credit = cli._credit(SimpleNamespace(credit=evidence / 'credit_20261122_0900.json'), prior, config)

    root = store.root / f'{PROFILE}_{ctx.scope_hash[:16]}'
    cli._protected_root(store, root)
    pin_json(root / 'configuration_freeze.json', ctx.scope)
    # CAPPED policy needs token caps too; they follow from the USD cap at list prices
    # (output at $2/M bounds spend on its own; input gets the same dollar bound at $0.25/M).
    token_caps = {m: (int(Decimal(c) / Decimal('0.25') * 1_000_000), int(Decimal(c) / Decimal('2') * 1_000_000))
                  for m, c in CAPS['openai_usd_by_method'].items()}
    api_budgets = {m: {'max_calls': API_CALLS[m], 'max_input_tokens': token_caps[m][0],
                       'max_output_tokens': token_caps[m][1],
                       'max_cost_usd': CAPS['openai_usd_by_method'][m], 'input_per_million_usd': '0.25',
                       'output_per_million_usd': '2', 'policy': 'CAPPED'} for m in METHODS}
    sql_budget = {'max_calls_per_question': CAPS['bigquery_calls_per_question'],
                  'max_probes_per_question': CAPS['bigquery_calls_per_question'],
                  'max_bytes_per_question': CAPS['bigquery_bytes_per_question'],
                  'max_bytes_per_experiment': CAPS['bigquery_bytes_total']}
    api_sha = pin_json(root / 'api_budgets.json', api_budgets)
    sql_sha = pin_json(root / 'sql_budget.json', sql_budget)
    case_ids = tuple(f'validation/{q.query_id}' for q in ctx.questions)

    @dataclass(frozen=True)
    class ValidationApproval(ctx.BenchmarkExecutionApproval):
        expected_phase = PHASE

        def _valid_case_scope(self):
            return (self.case_ids == case_ids and len(set(self.case_ids)) == VALIDATION_COUNT
                    and not any(c.startswith('test/') for c in self.case_ids))

    authorization_path = root / 'authorization.json'
    activation = (datetime.fromisoformat(cli.read_json(authorization_path)['valid_from_utc'])
                  if authorization_path.exists() else datetime.now(timezone.utc))
    limits = {k: asdict(prior)[k] for k in ctx.BenchmarkExecutionApproval.__dataclass_fields__}
    limits.update(phase=PHASE, case_ids=case_ids, approval_id=f'validation_v9_{ctx.scope_hash[:16]}',
                  valid_from_utc=activation, pilot_manifest_sha256=ctx.scope['validation_question_sha256'],
                  api_budget_sha256=api_sha, sql_budget_sha256=sql_sha)
    approval = ValidationApproval(**limits)
    approval.verify_active()
    cli.verify_reader_adc()
    pin_json(authorization_path, {
        **asdict(approval), 'valid_from_utc': approval.valid_from_utc.isoformat(),
        'valid_until_utc': approval.valid_until_utc.isoformat(), 'scope_sha256': ctx.scope_hash,
        'authorization_basis': ('Experiment lead chose option A on 2026-11-17 (fix Ours, re-run on all '
                                '190) and then asked to cut Ours cost: run Ours v8 lite on the 190 validation '
                                'questions (152 development + 38 '
                                'internal-check) and finish CoT/SDE-SQL; OpenAI <= USD 75 incl. judge '
                                'across all validation attempts; BigQuery <= 14 TiB; test stays sealed; '
                                'no result rows to any LLM. Caps reduced by the spend of earlier attempts.'),
        'prior_attempt': PRIOR_ATTEMPT,
        'attestation_extension': {'base': prior.policy_reference, 'from_case_count': 5,
                                  'to_case_count': VALIDATION_COUNT, 'data_policy_unchanged': True},
        'credit_valid_until': str(getattr(credit, 'valid_until', None))})
    execution = BenchmarkExecutionConfig(approval.max_bytes_billed_per_sql, approval.timeout_seconds,
                                         approval.max_rows, approval.max_result_bytes)
    sql_limits = SQLBudgetLimits(**sql_budget)
    sql_ledgers = {m: PersistentSQLBudgetLedger(root / 'validation_sql.sqlite', sql_limits, method=m, credit=credit)
                   for m in METHODS}
    api_ledgers = {m: PersistentAPIBudgetLedger(root / f'{m}_api.sqlite', PilotAPIBudget(
        b['max_calls'], b['max_input_tokens'], b['max_output_tokens'], Decimal(b['max_cost_usd']),
        Decimal('0.25'), Decimal('2'), 'CAPPED'))
        for m, b in api_budgets.items()}
    models = {
        'clinsql_cot': OpenAIModelProvider(api_ledgers['clinsql_cot'], **ctx.cot_options),
        'sde_sql': OpenAIChatMultiProvider(api_ledgers['sde_sql'], timeout_seconds=180,
                                          max_completion_tokens=OUTPUT_CAP, group_nine=True, transport_retries=2),
        'ours': PublicTerminologyModelProvider(api_ledgers['ours'], public_catalog=ctx.catalog,
                                               timeout_seconds=180, reasoning_effort='medium',
                                               max_output_tokens=OUTPUT_CAP, transport_retries=2),
    }
    judge = ChatJudge(ctx.judge_cfg)
    receipt_path = root / 'judge_preflight.json'
    if receipt_path.is_file():
        judge.verified = True
    else:
        pin_json(receipt_path, judge.verify())
    leaf_ledger = LeafLedger(root / 'judge.sqlite', max_calls=CAPS['judge_max_leaf_calls'], retry_limit=3,
                             grade_parser=parse_adapted_grade, retry_invalid_response=True,
                             retain_invalid_response=True)

    lock = threading.Lock()
    stop = threading.Event()
    state_path = root / 'state.sqlite'
    with sqlite3.connect(state_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS cases (method TEXT, case_id TEXT, status TEXT, '
                   'sha256 TEXT, attempt INTEGER, PRIMARY KEY (method, case_id))')

    def state(sql, params=()):
        with lock, sqlite3.connect(state_path, timeout=30) as db:
            return db.execute(sql, params).fetchall()

    def score(q, method, record):
        grade = {'method': method, 'case_id': q.query_id, 'partition': ctx.partition[q.query_id],
                 'difficulty': q.difficulty, 'domain': q.domain, 'status': record['status'],
                 'ex_strict': False, 'ex_relaxed': False, 'pred_shape': None, 'ref_shape': None,
                 'sql_score': None, 'sql_status': None, 'execution_score': None,
                 'execution_status': 'UNSCORED_DATA_EGRESS'}
        if record['status'] == 'INFRASTRUCTURE_BLOCKED':
            grade['sql_status'] = 'INFRASTRUCTURE_CENSORED'
            return grade
        ref_columns, ref_rows, _ = reference('validation', q.query_id)
        grade['ref_shape'] = [len(ref_rows), len(ref_columns)]
        result = None
        if record['status'] == 'EXECUTED':
            artifact = record['artifact']
            result = store.load(artifact['artifact_id'], expected_sha256=artifact['sha256'])
            columns, rows = list(result.columns), [list(r) for r in result.rows]
            grade['pred_shape'] = [len(rows), len(columns)]
            grade['ex_strict'] = ex_strict(columns, rows, ref_columns, ref_rows)
            grade['ex_relaxed'] = grade['ex_strict'] or ex_relaxed(columns, rows, ref_columns, ref_rows)
        sql = record.get('sql')
        if not sql or not str(sql).strip() or str(sql).strip().lower() == 'null':
            grade.update(sql_score=0.0, sql_status='NO_SQL_SCORED_ZERO')
            return grade
        scorer, _ = create_scorer(ctx.benchmark, LOCK, judge, leaf_ledger, scope=method,
                                  authorize=approval.verify_active)
        with private_sample_directory(root) as staging:
            sample = prepare_official_sample(staging, ctx.benchmark, q, sql, result)
            try:
                grade['sql_score'] = scorer.score_sql_without_results(sample)
                grade['sql_status'] = 'GRADED' if result is not None else 'GRADED_SQL_ONLY'
            except JudgeIncomplete as exc:
                grade['sql_status'] = str(exc)
        return grade

    def task(q, method):
        if stop.is_set():
            return None
        key = f'validation/{q.query_id}'
        prefix = ctx.digest([ctx.scope_hash, key, method])
        path, score_path = root / f'{prefix}.json', root / f'{prefix}.score.json'
        row = state('SELECT status, sha256, attempt FROM cases WHERE method=? AND case_id=?', (method, q.query_id))
        attempt = 1
        if row and row[0][0] == 'IMPORTED':
            return json.loads((root / f'imported_{prefix}.score.json').read_text(encoding='utf-8'))
        if row:
            status, digest_, attempt = row[0]
            redo = status == 'STARTED' or (args.retry_blocked and status == 'INFRASTRUCTURE_BLOCKED')
            if not redo:
                if score_path.is_file():
                    return json.loads(score_path.read_text(encoding='utf-8'))
                record = json.loads(path.read_text(encoding='utf-8'))
                grade = score(q, method, record)
                atomic_json(score_path, grade)
                return grade
            for old in (path, score_path):  # keep the censored attempt for the audit trail
                if old.is_file():
                    old.replace(old.with_name(old.name.replace('.json', f'.attempt{attempt}.json')))
            attempt += 1
            state('UPDATE cases SET status=?, sha256=NULL, attempt=? WHERE method=? AND case_id=?',
                  ('STARTED', attempt, method, q.query_id))
        else:
            state('INSERT INTO cases VALUES (?,?,?,?,?)', (method, q.query_id, 'STARTED', None, 1))
        approval.verify_active()
        log = RunLog(q.query_id, method, Pricing(0.25, 2))
        database = make_benchmark_database(config, ctx.manifest, ctx.index, execution, case_id=key,
                                           budget_scope=f'{PROFILE}:{method}:{key}', ledger=sql_ledgers[method],
                                           approval=approval)
        # The SQL Guard still blocks every query; SDE-SQL now receives the rejection as
        # execution feedback (as in the native loop) instead of the case being stopped.
        db = MeteredDatabase(database, log)
        model = MeteredModel(models[method], log)
        record = {'method': method, 'case_id': q.query_id, 'split': 'validation', 'attempt': attempt,
                  'partition': ctx.partition[q.query_id], 'sql': None, 'configuration_freeze_sha256': ctx.scope_hash,
                  'model_id': cli.MODEL, 'question_sha256': sha(q.text.encode())}
        try:
            if method == 'clinsql_cot':
                capture = _CaptureCompleteExecution(db)
                schema_text = '\n'.join(r['ddl'] for r in db.schema_metadata())
                pred = ClinSQLCoT(model, capture, schema_text).run(q.query_id, q.text)
                if pred.status == 'executed' and pred.sql != capture.last_sql:
                    raise IncompleteResultError('Saved CoT result differs from final SQL')
                prediction = {'sql': pred.sql, 'status': pred.status,
                              'result': capture.last_result if pred.status == 'executed' else None}
            else:
                prediction = execute_method(method, q, model, db, variant='grouped_3x3' if method == 'sde_sql'
                                            else 'dictionary_rag', schema_index=ctx.index, clinical=ctx.catalog,
                                            few_shot=ctx.fewshot, trace_root=root / 'traces',
                                            ours_flags=OURS_FLAGS if method == 'ours' else None)
            sql, result = prediction['sql'], prediction['result']
            record.update(sql=sql, inference_status=prediction['status'], fallbacks=prediction.get('fallbacks', []),
                          trace_path=prediction.get('trace_path'), inference_reason=prediction.get('reason'))
            if prediction['status'] in {'corrected_unexecuted', 'judge_modified_unexecuted'}:
                result = db.execute(sql)
            if result is None:
                reason = prediction.get('reason')
                record['status'] = 'INFRASTRUCTURE_BLOCKED' if reason in INFRASTRUCTURE else 'NO_COMPLETE_RESULT'
                if reason in INFRASTRUCTURE:
                    record['failure'] = reason
            else:
                if not result.complete or not sql or not result.job_id:
                    raise IncompleteResultError('Final output is incomplete')
                artifact = store.save(f'val9_{prefix}_a{attempt}', result)
                expiry = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                log.add('result_artifact', **artifact, artifact_expires_at_utc=expiry)
                record.update(status='EXECUTED', artifact=artifact, artifact_expires_at_utc=expiry)
        except (ValueError, ModelGenerationFailure) as exc:
            record.update(status='NO_COMPLETE_RESULT', error_type=type(exc).__name__)
        except PermissionError as exc:
            if str(exc) == 'SECURITY_REJECTED':
                # The read-only SQL Guard rejected SQL the method generated (e.g. a
                # misspelled dataset). That is the method's invalid SQL, not an
                # infrastructure gate: score it as a failed prediction, keep running.
                record.update(status='NO_COMPLETE_RESULT', error_type='SecurityRejected',
                              failure='MODEL_SQL_REJECTED_BY_GUARD')
            else:
                record.update(status='INFRASTRUCTURE_BLOCKED', error_type=type(exc).__name__,
                              failure=_failure(exc))
        except Exception as exc:  # noqa: BLE001 - censored, recorded, never scored as a wrong answer
            record.update(status='INFRASTRUCTURE_BLOCKED', error_type=type(exc).__name__, failure=_failure(exc),
                          cause_type=getattr(exc, 'cause_type', None), http_status=getattr(exc, 'http_status', None))
        record.update(usage=log.summary(), events=log.events)
        atomic_json(path, record)
        state('UPDATE cases SET status=?, sha256=? WHERE method=? AND case_id=?',
              (record['status'], sha(path.read_bytes()), method, q.query_id))
        if record['status'] == 'INFRASTRUCTURE_BLOCKED' and record.get('failure') in STOP_FAILURES:
            stop.set()  # a budget/permission gate: stop scheduling, never push past a cap
        grade = score(q, method, record)
        atomic_json(score_path, grade)
        print(json.dumps({'method': method, 'case_id': q.query_id, 'status': record['status'],
                          'ex_strict': grade['ex_strict'], 'sql_score': grade['sql_score'],
                          'failure': record.get('failure'), 'fallbacks': record.get('fallbacks'),
                          'latency': record['usage'].get('total_latency_seconds')}), flush=True)
        return grade

    imported = import_v6_baselines(store.root / V6_ROOT, root, ctx, state)
    print(json.dumps({'imported_v6_predictions': imported}), flush=True)
    questions = ctx.questions[:args.limit] if args.limit else ctx.questions
    if args.case_ids:
        wanted_ids = set(Path(args.case_ids).read_text(encoding='utf-8').split())
        questions = [q for q in ctx.questions if q.query_id in wanted_ids]
    if args.methods:
        wanted = args.methods.split(',')
    else:
        wanted = list(METHODS)
    tasks = [(q, m) for q in questions for m in wanted]
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 8))) as pool:
        futures = [pool.submit(task, q, m) for q, m in tasks]
        for future in as_completed(futures):
            future.result()
    summarize(root, ctx)
    return 2 if stop.is_set() else 0


def import_v6_baselines(v6_root, root, ctx, state):
    """Copy completed (non-censored) v6 CoT/SDE predictions and grades, with provenance."""
    count = 0
    for score_path in sorted(v6_root.glob('*.score.json')):
        if '.attempt' in score_path.name:
            continue
        grade = json.loads(score_path.read_text(encoding='utf-8'))
        if grade['method'] not in IMPORTED_METHODS or grade['sql_status'] == 'INFRASTRUCTURE_CENSORED':
            continue
        record_path = score_path.with_name(score_path.name.replace('.score.json', '.json'))
        record = json.loads(record_path.read_text(encoding='utf-8'))
        if record.get('status') == 'INFRASTRUCTURE_BLOCKED':
            continue
        # v8 baseline adapter fixes change behaviour only after a guard rejection (SDE-SQL:
        # rejection is now execution feedback instead of a stop) or a database error
        # (CoT: same whitelisted error classes as the other methods). Re-run exactly those.
        if record.get('failure') == 'MODEL_SQL_REJECTED_BY_GUARD':
            continue
        if grade['method'] == 'clinsql_cot' and any(
                (e.get('error') or e.get('valid') is False) for e in record.get('events', []) if e.get('stage') != 'llm'):
            continue
        prefix = ctx.digest([ctx.scope_hash, f"validation/{grade['case_id']}", grade['method']])
        target = root / f'imported_{prefix}.score.json'
        if not target.is_file():
            provenance = {'imported_from': f'{v6_root.name}/{score_path.name}',
                          'source_record_sha256': sha(record_path.read_bytes()),
                          'source_score_sha256': sha(score_path.read_bytes())}
            atomic_json(root / f'imported_{prefix}.json', {**record, **provenance})
            atomic_json(target, {**grade, **provenance})
        if not state('SELECT 1 FROM cases WHERE method=? AND case_id=?', (grade['method'], grade['case_id'])):
            state('INSERT INTO cases VALUES (?,?,?,?,?)', (grade['method'], grade['case_id'], 'IMPORTED',
                                                           sha(target.read_bytes()), 0))
        count += 1
    return count


def summarize(root, ctx=None):
    """Aggregate both tiers by method, partition and difficulty; paired tests vs Ours."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from score_execution_accuracy import bootstrap_ci, mcnemar_exact
    grades = [json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.score.json')
              if '.attempt' not in p.name]
    by = {}
    for g in grades:
        by.setdefault(g['method'], {})[g['case_id']] = g

    def block(rows):
        scored = [r for r in rows if r['sql_status'] != 'INFRASTRUCTURE_CENSORED']
        n = len(scored)
        sql = [r['sql_score'] or 0.0 for r in scored if r['sql_score'] is not None or r['sql_status'] == 'NO_SQL_SCORED_ZERO']
        return {'n': n, 'censored': len(rows) - n,
                'executed': sum(r['status'] == 'EXECUTED' for r in scored),
                'ex_strict': sum(r['ex_strict'] for r in scored) / n if n else None,
                'ex_relaxed': sum(r['ex_relaxed'] for r in scored) / n if n else None,
                'ex_strict_ci95': bootstrap_ci([r['ex_strict'] for r in scored]),
                'sql_score': sum(sql) / len(sql) if sql else None,
                'sql_score_ci95': _bootstrap_mean(sql)}

    summary = {}
    for method, cases in by.items():
        rows = list(cases.values())
        summary[method] = {'all': block(rows)}
        for key in ('partition', 'difficulty'):
            for value in sorted({r[key] for r in rows}):
                summary[method][f'{key}={value}'] = block([r for r in rows if r[key] == value])
    paired = {}
    if 'ours' in by:
        for other in by:
            if other == 'ours':
                continue
            common = sorted(c for c in set(by['ours']) & set(by[other])
                            if 'INFRASTRUCTURE_CENSORED' not in (by['ours'][c]['sql_status'], by[other][c]['sql_status']))
            entry = {'n': len(common)}
            for variant in ('ex_strict', 'ex_relaxed'):
                entry[variant] = mcnemar_exact([by['ours'][c][variant] for c in common],
                                               [by[other][c][variant] for c in common])
            diffs = [(by['ours'][c]['sql_score'] or 0.0) - (by[other][c]['sql_score'] or 0.0) for c in common]
            entry['sql_score_mean_diff'] = sum(diffs) / len(diffs) if diffs else None
            entry['sql_score_diff_ci95'] = _bootstrap_mean(diffs)
            entry['sql_score_wins_ties_losses'] = [sum(d > 0 for d in diffs), sum(d == 0 for d in diffs),
                                                   sum(d < 0 for d in diffs)]
            paired[f'ours_vs_{other}'] = entry
    report = {'label': 'Tier1 deterministic EX (supplementary) + Tier2 adapted rubric SQL Score; '
                       'Execution Score UNSCORED_DATA_EGRESS', 'summary': summary, 'paired': paired,
              'generated_at_utc': datetime.now(timezone.utc).isoformat()}
    atomic_json(root / 'evaluation_summary.json', report)
    print(json.dumps({m: v['all'] for m, v in summary.items()}, indent=1))
    print(json.dumps(paired, indent=1))
    return report


def _bootstrap_mean(values, iterations=10000, seed=20261117):
    import random
    if not values:
        return [None, None]
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iterations))
    return [means[int(0.025 * iterations)], means[int(0.975 * iterations) - 1]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--workers', type=int, default=6)
    parser.add_argument('--limit', type=int, default=0, help='first N questions only (smoke test)')
    parser.add_argument('--methods', default='', help='comma-separated subset of methods')
    parser.add_argument('--retry-blocked', action='store_true',
                        help='re-run infrastructure-censored predictions; earlier attempts are kept')
    parser.add_argument('--summarize-only', type=Path, default=None)
    parser.add_argument('--case-ids', default='', help='file with whitespace-separated query ids (subset run)')
    args = parser.parse_args()
    if args.summarize_only:
        summarize(args.summarize_only)
        return 0
    load_research_env(ROOT / '.env', os.environ)
    return run(args)


if __name__ == '__main__':
    raise SystemExit(main())
