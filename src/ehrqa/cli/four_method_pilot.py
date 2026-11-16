"""Plan and run approved pilot methods with a common result contract."""
import argparse
from dataclasses import asdict
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import os
import sqlite3
from pathlib import Path
import subprocess
import tempfile
import uuid

from ehrqa.agentic.trace import digest
from ehrqa.agentic.schema import Schema
from ehrqa.clinsql.baselines.mac_sampling import column_sample_queries, format_examples
from ehrqa.clinsql.baselines.mac_sql import _bird_schema_text, _key_columns, verify_bird_description
from ehrqa.clinsql.benchmark_backend import make_benchmark_database
from ehrqa.clinsql.catalog_export import catalog_queries, export_catalog
from ehrqa.clinsql.chat_multi_provider import (
    MAC_MODEL_PARAMETER_ADAPTATION, MACSQLChatProvider, OpenAIChatMultiProvider,
)
from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
from ehrqa.clinsql.config import BigQueryConfig
from ehrqa.clinsql.dataset import load_official_questions
from ehrqa.clinsql.execution_budget import PersistentSQLBudgetLedger, SQLBudgetLimits
from ehrqa.clinsql.execution_budget import (
    DATABASE_PREPROCESSING_BUDGET, RESEARCH_CREDIT_AWARE, ResearchCreditEnvelope,
)
from ehrqa.clinsql.execution_errors import IncompleteResultError, ResourceBudgetBlocked
from ehrqa.clinsql.execution_control import verify_reader_adc
from ehrqa.clinsql.execution_modes import BenchmarkExecutionConfig
from ehrqa.clinsql.experiment_state import METHODS, ExperimentState, verify_pre_freeze_manifest
from ehrqa.clinsql.four_method_runner import (FourMethodApproval, MODEL, VARIANTS, read_json,
    reuse_cot, run_case, sha256_file, stage_saved_prediction)
from ehrqa.clinsql.pilot_api_budget import PersistentAPIBudgetLedger, PilotAPIBudget
from ehrqa.clinsql.result_artifacts import ResultArtifactStore, verify_windows_private_acl
from ehrqa.clinsql.retrieval_manifest import FROZEN_CORPUS_SHA256, load_frozen_fewshot_index
from ehrqa.clinsql.schema_index import SchemaIndex
from ehrqa.clinsql.task8_attestation import verify_task8_attestation


ROOT = Path(__file__).resolve().parents[3]
BENCHMARK = ROOT / 'external/clinsql_official'
STORE = ROOT / 'results/restricted'
STATE = STORE / 'four_method_pilot'
HISTORICAL_MASTER = ROOT / 'data/clinsql/master_experiment_pre_freeze_v1.json'
MASTER = ROOT / 'data/clinsql/master_experiment_pre_freeze_v2.json'
PILOT = ROOT / 'data/clinsql/pilot_5_validation_development_v1.json'
MANIFEST = ROOT / 'data/schema/manifests/mimiciv_3_1_20261112T143303Z.json'
INDEX = ROOT / 'data/schema/indexes/schema_lexical_v1_46a816c289178f5b.json'
CORPUS = ROOT / 'data/clinsql/retrieval/fewshot_development_v1.json'


def _credit(args, approval, config, *, check_expiry=True):
    if args.credit is None:
        raise PermissionError('CREDIT_BALANCE_UNVERIFIED: supply an approved credit envelope')
    raw = args.credit.read_bytes()
    if hashlib.sha256(raw).hexdigest() != approval.credit_sha256:
        raise PermissionError('Credit envelope differs from approval')
    data = json.loads(raw)
    if data.pop('mode') != RESEARCH_CREDIT_AWARE:
        raise ValueError('Research credit-aware policy required')
    for old, new in (('verified_credit_usd', 'verified_credit'),
                     ('approved_spend_usd', 'approved_spend'), ('usd_per_tib', 'price_per_tib')):
        if old in data:
            if data.get('currency', 'USD') != 'USD' or new in data:
                raise ValueError('Legacy USD fields cannot be mixed with currency-aware fields')
            data[new] = data.pop(old)
    for name in ('verified_credit', 'approved_spend', 'price_per_tib', 'reserve'):
        if name not in data and name == 'reserve':
            continue
        data[name] = Decimal(str(data[name]))
    data['expires_at'] = datetime.fromisoformat(data['expires_at'])
    for field in ('price_valid_until', 'credit_observed_at', 'credit_valid_until'):
        if data.get(field) is not None:
            data[field] = datetime.fromisoformat(data[field])
    credit = ResearchCreditEnvelope(**data)
    if credit.currency == 'VND' and credit.credit_valid_until is None:
        raise PermissionError('VND execution requires a dated credit snapshot')
    if (credit.project != config.project_id or config.billing_project != credit.project or
        credit.billing_account != '013047-311AC0-9ADD4D'):
        raise PermissionError('Credit envelope does not cover the configured billing project/account')
    if check_expiry:
        _ = credit.ceiling
    return credit


def _task6_synthetic(store, *, diagnose_n9=False):
    root = STATE / 'sde_transport'
    _protected_root(store, root)
    budget = PilotAPIBudget(1 if diagnose_n9 else 2, 4096, 6144, None, Decimal('0.25'), Decimal('2'),
                            'UNLIMITED_RESEARCH_NOV_2026')
    budget.verify_active()
    prefix = 'task7_diagnostic' if diagnose_n9 else 'task6'
    ledger = PersistentAPIBudgetLedger(root / f'{prefix}_synthetic.sqlite', budget)
    transport = OpenAIChatMultiProvider(ledger, model_id=MODEL, max_completion_tokens=512)
    metadata = []
    for n in ((9,) if diagnose_n9 else (9, 3)):
        path = root / f'{prefix}_n{n}.json'
        if path.exists():
            record = read_json(path)
        else:
            with path.with_suffix('.started').open('x', encoding='utf-8'):
                pass
            try:
                replies = transport.generate('sde.synthetic_transport', 'Return exactly: SELECT 1', n=n)
                record = {'requested': n, 'received': len(replies), 'response_id': replies[0]['response_id'],
                          'model': replies[0]['model_snapshot'], 'usage': replies[0]['usage'], 'status': 'PASS'}
            except Exception as exc:
                record = {'requested': n, 'status': 'FAILED', 'error_type': type(exc).__name__,
                          'http_status': getattr(exc, 'http_status', None),
                          'cause_type': getattr(exc, 'cause_type', None),
                          'provider': getattr(exc, 'provider_details', {}),
                          'rejected_before_generation': getattr(exc, 'rejected_before_generation', False),
                          'usage': getattr(exc, 'usage', {}), 'response_id': getattr(exc, 'response_id', None),
                          'incomplete_reason': getattr(exc, 'incomplete_reason', None)}
            with path.open('x', encoding='utf-8') as stream:
                json.dump(record, stream)
        metadata.append(record)
    print(json.dumps({'requests': metadata, 'ledger': ledger.snapshot()}))
    if diagnose_n9:
        return int(metadata[0]['status'] != 'PASS')
    if any(row['status'] != 'PASS' for row in metadata):
        return 1
    with (root / 'verified.json').open('w', encoding='utf-8') as stream:
        json.dump({'model': MODEL, 'choices': [9, 3], 'responses': metadata,
                   'configuration_sha256': configuration('sde_transport', 'synthetic_only')}, stream)
    return 0


def _verify_grouped_sde(store):
    root = STATE / 'sde_transport'
    _protected_root(store, root)
    verified = root / 'verified_grouped_3x3.json'
    pin = _grouped_transport_pin()
    if verified.exists():
        saved = read_json(verified)
        if not _grouped_transport_verified(verified, saved):
            raise PermissionError('Grouped transport evidence differs from current implementation')
        print(json.dumps(saved))
        return 0
    diagnostic = read_json(root / 'task7_diagnostic_n9.json')
    error = diagnostic.get('provider', {})
    if (diagnostic.get('http_status'), error.get('code'), error.get('param')) != (
        400, 'integer_above_max_value', 'n'
    ):
        raise PermissionError('Grouped transport requires evidence of a provider n limit')
    budget = PilotAPIBudget(3, 4096, 4608, None, Decimal('0.25'), Decimal('2'),
                            'UNLIMITED_RESEARCH_NOV_2026')
    budget.verify_active()
    ledger = PersistentAPIBudgetLedger(root / 'task7_grouped.sqlite', budget)
    transport = OpenAIChatMultiProvider(ledger, model_id=MODEL, max_completion_tokens=512,
                                       group_nine=True)
    with verified.with_suffix('.started').open('x', encoding='utf-8'):
        pass
    replies = transport.generate('sde.synthetic_transport', 'Return exactly: SELECT 1', n=9)
    groups = [row for row in replies if row['choice_index'] == 0]
    if len(replies) != 9 or len({row['response_id'] for row in groups}) != 3:
        raise ValueError('Expected nine choices across three provider requests')
    record = {'model': MODEL, 'choices': [3, 3, 3], 'configuration_sha256': pin,
              'responses': [{'response_id': row['response_id'], 'usage': row['usage']} for row in groups],
              'ledger': ledger.snapshot()}
    with verified.open('x', encoding='utf-8') as stream:
        json.dump(record, stream)
    print(json.dumps(record))
    return 0


def _grouped_transport_pin():
    return digest({name: sha256_file(ROOT / 'src/ehrqa/clinsql' / name)
                   for name in ('chat_multi_provider.py', 'openai_provider.py')})


def _grouped_transport_verified(path, smoke):
    if smoke.get('configuration_sha256') == _grouped_transport_pin():
        return True
    # The Task 7 observation predates the narrower provider-only fingerprint.
    return (sha256_file(path) == '35ee73dafcfaf957638178eecb73ce87d7bc6b766f278553d88b6a269ff3e71a'
            and sha256_file(ROOT / 'src/ehrqa/clinsql/chat_multi_provider.py') ==
            '2cfb7331945c4bc6f651de800c85acd66f07331917e13ba1c66d61c2d3ce8267'
            and sha256_file(ROOT / 'src/ehrqa/clinsql/openai_provider.py') ==
            '01c53925454e3d5a6db0c5c457e9cd433c8f9bc02a89be8e40cb9aa26d9067cc')


def _scope():
    master, pilot, manifest = map(read_json, (MASTER, PILOT, MANIFEST))
    verify_pre_freeze_manifest(master)
    index = SchemaIndex.load(INDEX, manifest)
    pilot_digest = hashlib.sha256(json.dumps(
        {key: value for key, value in pilot.items() if key != 'sha256'},
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (master['schema_sha256'] != manifest['sha256'] or
        master['schema_index_sha256'] != index.index['sha256'] or
        master['pilot_manifest_sha256'] != pilot['sha256'] or pilot['sha256'] != pilot_digest):
        raise ValueError('Experiment scope pins do not match')
    return master, pilot, manifest, index


def configuration(method, variant, catalog_sha256=None):
    if variant not in VARIANTS.get(method, {}):
        raise ValueError('Invalid method variant')
    project_files = ['clinsql/' + name for name in (
        'four_method_runner.py', 'benchmark_approval.py', 'benchmark_backend.py', 'bigquery_adapter.py',
        'bigquery_client.py', 'execution_budget.py', 'execution_control.py', 'execution_errors.py',
        'execution_modes.py', 'experiment_state.py', 'result_artifacts.py', 'pilot_api_budget.py',
        'task8_attestation.py')]
    project_files += ['cli/four_method_pilot.py', 'text2sql/logging.py']
    project_files += ['clinsql/benchmark_model.py']
    project_files += ['clinsql/' + name for name in ('metadata.py', 'config.py', 'schema_index.py', 'dataset.py')]
    method_files = {
        'mac_sql': ('baselines/mac_sql.py', 'baselines/mac_sampling.py', 'source_templates.py',
                    'chat_multi_provider.py', 'openai_provider.py'),
        'sde_sql': ('baselines/sde_sql.py', 'baselines/sde_judge.py', 'baselines/sde_subqueries.py',
                    'baselines/sde_refine_policy.py', 'source_templates.py', 'chat_multi_provider.py'),
        'ours': ('proposed.py', 'proposed_runner.py', 'openai_provider.py', 'clinical_catalog.py',
                 'schema_index.py', 'retrieval.py', 'retrieval_manifest.py', 'linking_format.py'),
        'catalog_export': ('catalog_export.py', 'clinical_catalog.py'),
        'sde_transport': ('chat_multi_provider.py', 'openai_provider.py'),
    }
    project_files += ['clinsql/' + name for name in method_files[method]]
    if method in {'mac_sql', 'ours'}:
        project_files.extend(('agentic/schema.py', 'clinsql/evidence_router.py'))
    if method == 'ours':
        from ehrqa.clinsql.proposed import PROPOSED_VERSION, ProposedFlags
        project_files.extend('agentic/' + name for name in
                             ('pipeline.py', 'prompts.py', 'retrieval.py', 'contracts.py',
                              'database.py', 'evidence.py', 'trace.py'))
    lock = read_json(ROOT / 'PAPER_SOURCE_LOCK.json').get(method)
    payload = {'method': method, 'variant': variant, 'model': MODEL, 'reasoning_effort': 'medium',
               'timeout_seconds': 180, 'max_tokens_per_choice': 512 if method == 'sde_transport' else None,
               'source_lock': lock, 'catalog_sha256': catalog_sha256,
               'implementation': {name: sha256_file(ROOT / 'src/ehrqa' / name) for name in project_files}}
    if method == 'ours':
        payload.update(version=PROPOSED_VERSION, flags=asdict(ProposedFlags()),
                       fewshot_sha256=FROZEN_CORPUS_SHA256)
    if method == 'mac_sql':
        payload.update(reasoning_effort=None, omitted_source_parameters={'temperature': 0.1},
                       model_parameter_adaptation=MAC_MODEL_PARAMETER_ADAPTATION,
                       transport='openai.chat.completions')
    return digest(payload)


def _source_check(method):
    lock = read_json(ROOT / 'PAPER_SOURCE_LOCK.json').get(method)
    if lock is None:
        return
    checkout = ROOT / lock['path']
    commit = subprocess.check_output(['git', '-C', str(checkout), 'rev-parse', 'HEAD'], text=True).strip()
    changed = subprocess.check_output(['git', '-C', str(checkout), 'status', '--porcelain',
                                       '--untracked-files=no'], text=True).strip()
    if commit != lock['commit'] or changed or any(
        sha256_file(checkout / path) != expected for path, expected in lock['key_files'].items()
    ):
        raise PermissionError('Official source differs from the pinned checkout')


def _load_frozen_fewshot(master):
    historical = read_json(HISTORICAL_MASTER)
    scope_fields = ('schema_sha256', 'schema_index_sha256', 'validation_question_tree_sha256',
                    'pilot_manifest_sha256', 'pilot_case_ids', 'development_case_ids',
                    'internal_check_case_ids')
    if any(master[key] != historical[key] for key in scope_fields):
        raise PermissionError('Active experiment changed the frozen retrieval scope')
    return load_frozen_fewshot_index(CORPUS, historical)


def _sample_count(index):
    records = index.schema_records()
    schema = Schema.from_records(records, dialect='bigquery')
    return sum(1 for _ in column_sample_queries(schema, _key_columns(schema, records)))


def _budgets(approval, api_path, sql_path, *, sample_count=0, previous_calls=0):
    sql = None
    if approval.method != 'sde_transport':
        sql_raw = sql_path.read_bytes()
        if hashlib.sha256(sql_raw).hexdigest() != approval.sql_budget_sha256:
            raise PermissionError('SQL budget differs from approved bytes')
        sql = SQLBudgetLimits(**json.loads(sql_raw))
    if approval.method == 'mac_sql' and (sql.max_probes_per_question < sample_count or
                                        sql.max_calls_per_question < sample_count + 4):
        raise ValueError('SQL budget does not cover MAC sampling and final execution')
    if approval.method == 'sde_sql' and (
        sql.max_probes_per_question < 2 or sql.max_calls_per_question < 13 + sql.max_probes_per_question
    ):
        raise ValueError('SQL budget does not cover SDE candidate/refinement and probe capacity')
    if approval.method == 'catalog_export' and sql.max_calls_per_question < 4:
        raise ValueError('SQL budget does not cover all four dictionaries')
    api = None
    if approval.method != 'catalog_export':
        api_data = api_path.read_bytes() if api_path is not None else b''
        if hashlib.sha256(api_data).hexdigest() != approval.api_budget_sha256:
            raise PermissionError('API budget differs from approved bytes')
        api_raw = json.loads(api_data)
        for key in ('max_cost_usd', 'input_per_million_usd', 'output_per_million_usd'):
            if api_raw[key] is not None:
                api_raw[key] = Decimal(str(api_raw[key]))
        api = PilotAPIBudget(**api_raw)
        if approval.method == 'sde_sql' and approval.variant == 'grouped_3x3' and api.max_calls + previous_calls < 130:
            raise ValueError('Grouped SDE budget must cover up to 26 requests per case')
        api.verify_active()
    return api, sql


def _protected_root(store, path):
    if not store.verify_private_acl(store.root):
        raise PermissionError('Restricted artifact root ACL failed')
    path.mkdir(parents=True, exist_ok=True)
    if not store.verify_private_acl(path):
        raise PermissionError('Restricted run root ACL failed')


def _private_acl(path):
    path = Path(path).absolute()
    if path == STORE:
        return verify_windows_private_acl(STORE)
    if not path.is_relative_to(STORE) or not path.resolve().is_relative_to(STORE.resolve()):
        return False
    current = path
    while current != STORE:
        if current.is_symlink() or current.is_junction():
            return False
        current = current.parent
    return verify_windows_private_acl(STORE) and verify_windows_private_acl(path, allow_safe_inherited=True)


def _ledger_root(store, root, approval):
    path = root / approval.approval_id
    _protected_root(store, path)
    pin = path / 'approval.sha256'
    expected = digest(approval.__dict__)
    try:
        with pin.open('x', encoding='utf-8') as stream:
            stream.write(expected)
    except FileExistsError:
        if pin.read_text(encoding='utf-8') != expected:
            raise PermissionError('An existing approval ID cannot reset its ledger scope') from None
    return path


def _approval(args, manifest, index):
    approval = FourMethodApproval.from_file(args.approval)
    approval.verify_active()
    verify_task8_attestation(approval, ROOT, read_json(PILOT))
    if (approval.manifest_sha256 != manifest['sha256'] or approval.index_sha256 != index.index['sha256'] or
        configuration(approval.method, approval.variant, approval.catalog_sha256) != approval.configuration_sha256):
        raise PermissionError('Approved method configuration differs from current code or schema')
    return approval


def _database(approval, manifest, index, case_id, ledger, config, **transport):
    return make_benchmark_database(config, manifest, index,
        BenchmarkExecutionConfig(approval.max_bytes_billed_per_sql, approval.timeout_seconds,
                                 approval.max_rows, approval.max_result_bytes),
        case_id=case_id, ledger=ledger, approval=approval, **transport)


def _prepare_mac_samples(approval, manifest, index, ledger, config):
    if approval.method != 'mac_sql' or approval.variant != 'column_samples':
        raise PermissionError('Database preprocessing requires the approved MAC sample scope')
    if ledger.pending_jobs():
        raise PermissionError('Reconcile existing MAC-SQL jobs before resuming sampling')
    from google.cloud import bigquery

    reader = verify_reader_adc(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    client = bigquery.Client(project=config.billing_project, location=config.location, credentials=reader)
    first_case = approval.case_ids[0]
    prep = _database(approval, manifest, index, first_case, ledger, config, client=client,
                     pinned_reader=True, budget_scope=DATABASE_PREPROCESSING_BUDGET)
    records = index.schema_records()
    schema = Schema.from_records(records, dialect='bigquery')
    keys = _key_columns(schema, records)
    settled = ledger.settled_mac_probes(approval.case_ids)
    caches, missing = [], []
    for current, original in zip(column_sample_queries(schema, keys),
                                 column_sample_queries(schema, keys, bounded=False), strict=True):
        table, column, kind, sql = current
        for candidate in dict.fromkeys((sql, original[3])):
            saved = settled.get(hashlib.sha256(candidate.encode()).hexdigest())
            if saved is not None:
                caches.append((table, column, kind, candidate, *saved))
                break
        else:
            missing.append(current)
    available_slots = ledger.remaining_probe_slots(DATABASE_PREPROCESSING_BUDGET)
    if len(missing) > available_slots:
        raise ResourceBudgetBlocked('Database preprocessing probe allocation exhausted')
    estimates = [prep.research_quote(sql, prep.dry_run(sql)) for _, _, _, sql in missing]
    maximum = sum(cap for cap, _ in estimates)
    available = ledger.remaining_research_bytes(DATABASE_PREPROCESSING_BUDGET)
    print(json.dumps({'stage': 'mac_preprocessing_plan', 'cached_slots': len(caches),
                      'new_slots': len(missing), 'estimated_billed_bytes': sum(b for _, b in estimates),
                      'maximum_bytes_billed': maximum, 'remaining_bytes_budget': available,
                      'maximum_cost_vnd': str(ledger.credit.price_per_tib * Decimal(maximum) /
                                              Decimal(1 << 40))}), flush=True)
    if maximum > available:
        raise ResourceBudgetBlocked('MAC sample plan exceeds approved database, method or credit ceiling',
                                    estimated_bytes=maximum, cap_bytes=available)
    samples = {table: {} for table in schema.tables}
    backends = {DATABASE_PREPROCESSING_BUDGET: prep}
    for table, column, kind, sql, scope, job_id in caches:
        if scope not in backends:
            backends[scope] = _database(approval, manifest, index, scope, ledger, config,
                                        client=client, pinned_reader=True)
        samples[table][column] = backends[scope].recover_sample(sql, job_id, kind)
    print(json.dumps({'stage': 'mac_preprocessing_cache_verified', 'slots': len(caches)}), flush=True)
    billed = 0
    for number, (table, column, kind, sql) in enumerate(missing, 1):
        result = prep.probe(sql)
        if not result.complete:
            raise IncompleteResultError(f'MAC sample cannot be scored for {table}.{column}')
        samples[table][column] = format_examples([row[0] for row in result.rows], kind)
        billed += result.bytes_billed
        if number % 10 == 0:
            print(json.dumps({'stage': 'mac_preprocessing_progress', 'new_slots_recovered': number,
                              'billed_bytes': billed}), flush=True)
    verify_bird_description(schema, samples, records)
    description = _bird_schema_text(schema, {}, samples, records=records)
    print(json.dumps({'stage': 'mac_preprocessing_complete', 'cached_slots': len(caches),
                      'new_slots_recovered': len(missing), 'billed_bytes': billed,
                      'source_renderer_parity': True,
                      'description_sha256': hashlib.sha256(description.encode()).hexdigest()}), flush=True)
    return samples


def _questions(pilot, master):
    questions, question_digest = load_official_questions(BENCHMARK, split='validation')
    if question_digest != master['validation_question_tree_sha256']:
        raise ValueError('Validation question tree differs from the pinned scope')
    questions = {question.query_id: question for question in questions}
    return [questions[case['case_id']] for case in pilot['cases']]


from ehrqa.clinsql.benchmark_model import ModelMismatch, require_benchmark_model


def _pilot_state(path, master):
    if path.is_file():
        historical = read_json(HISTORICAL_MASTER)
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as db:
            pin = db.execute('SELECT sha256 FROM scope_lock WHERE id=1').fetchone()
        if pin and pin[0] == historical['sha256']:
            master = historical
    return ExperimentState(path, master)


def _run(args, store, master, pilot, manifest, index):
    approval = _approval(args, manifest, index)
    if approval.method not in {'sde_sql', 'ours'}:
        raise PermissionError('Approval cannot authorize pilot inference')
    approval.verify_pilot(pilot)
    if getattr(args, 'case_id', None) and args.case_id not in approval.case_ids:
        raise PermissionError('Case is outside the approved pilot')
    if any(getattr(args, flag, None) for flag in ('local_model', 'restricted_local_model',
                                                  'retry_evidence', 'structured_retry', 'backend_retry')):
        raise ModelMismatch()
    require_benchmark_model(os.environ.get('OPENAI_MODEL'))
    retry_uncapped = getattr(args, 'retry_uncapped_sde', False)
    resume_probe = getattr(args, 'resume_incomplete_probe', False)
    if resume_probe and not retry_uncapped:
        raise PermissionError('Probe recovery requires the uncapped SDE pilot')
    if retry_uncapped and (approval.method != 'sde_sql' or
                           not approval.policy_reference.startswith('task8-user-attestation:')):
        raise PermissionError('Uncapped retry is scoped to the attested SDE pilot')
    previous_calls = 0
    if retry_uncapped:
        import sqlite3
        prior = STATE / 'sde_sql' / approval.approval_id / 'api.sqlite'
        if not store.verify_private_acl(prior.parent) or not prior.is_file():
            raise PermissionError('Previous SDE ledger is required for retry accounting')
        with sqlite3.connect(prior) as previous:
            previous_calls = previous.execute('SELECT count(*) FROM api_calls').fetchone()[0]
    api, sql = _budgets(approval, args.api_budget, args.sql_budget, previous_calls=previous_calls,
                        sample_count=_sample_count(index) if approval.variant == 'column_samples' else 0)
    if retry_uncapped and api.max_calls + previous_calls != 130:
        raise PermissionError('Retry must share the original SDE request budget')
    if os.environ.get('SEND_RESULTS_TO_LLM', '').lower() != 'false':
        raise PermissionError('Raw-result transmission must remain disabled')
    if not os.environ.get('OPENAI_API_KEY'):
        raise PermissionError('OpenAI API key is unavailable')
    config = BigQueryConfig.from_env()
    if (config.project_id != approval.project_id or config.location.upper() != approval.location.upper()
        or set(config.allowed_datasets) != set(approval.datasets)):
        raise PermissionError('BigQuery environment differs from approval')
    credit = _credit(args, approval, config)
    _source_check(approval.method)
    verify_reader_adc()
    clinical = fewshot = None
    if approval.method == 'ours':
        if args.catalog is None:
            raise PermissionError('The pinned clinical catalog is required')
        clinical = ClinicalCatalog.load(args.catalog, expected_sha256=approval.catalog_sha256,
                                        schema_sha256=manifest['sha256'])
        fewshot = _load_frozen_fewshot(master)
    if approval.method == 'sde_sql':
        grouped = approval.variant == 'grouped_3x3'
        smoke_path = STATE / 'sde_transport' / ('verified_grouped_3x3_uncapped.json' if retry_uncapped else
                                                'verified_grouped_3x3.json' if grouped else 'verified.json')
        smoke = read_json(smoke_path) if smoke_path.is_file() else {}
        if (smoke.get('model') != MODEL or smoke.get('choices') != ([3, 3, 3] if grouped else [9, 3]) or
            not (_grouped_transport_verified(smoke_path, smoke) if grouped else
                 smoke.get('configuration_sha256') == configuration('sde_transport', 'synthetic_only'))):
            raise PermissionError('Run the approved synthetic SDE transport check first')
    root = STATE / ('sde_sql_uncapped' if retry_uncapped else approval.method)
    _protected_root(store, STATE)
    _protected_root(store, root)
    recovered = {}
    continuation = root / 'source_aligned_next_run' if approval.method in {'mac_sql', 'ours'} else root
    _protected_root(store, continuation)
    if resume_probe:
        prior_state = _pilot_state(root / 'state.sqlite', master)
        for checkpoint in prior_state.checkpoints('FOUR_METHOD_PILOT_5'):
            path = root / (digest([approval.method, checkpoint.case_id]) + '.json')
            if not path.is_file() or sha256_file(path) != checkpoint.artifact_sha256:
                raise PermissionError('Saved SDE checkpoint integrity check failed')
            previous = read_json(path)
            probes = [event for event in previous['events'] if event['stage'] == 'probe'
                      and event.get('complete') is False and event.get('job_id')]
            if (previous.get('status') != 'INCOMPLETE_RESULT' or len(probes) != 1 or
                    [event['operation'] for event in previous['events'] if event['stage'] == 'llm'] != ['sde.explore1']):
                raise PermissionError('Checkpoint is not a recoverable first-stage probe')
            recovered[checkpoint.case_id] = probes[0]['sql'], probes[0]['job_id']
        if not recovered:
            raise PermissionError('No saved SDE probe checkpoint to recover')
        continuation = root / 'probe_continuation'
        _protected_root(store, continuation)
    ledgers = _ledger_root(store, root, approval)
    api_ledger = PersistentAPIBudgetLedger(ledgers / 'api.sqlite', api)
    sql_ledger = PersistentSQLBudgetLedger(STATE / 'research_sql.sqlite', sql,
                                           method=approval.method, credit=credit)
    if approval.method == 'mac_sql':
        model = MACSQLChatProvider(api_ledger, model_id=MODEL, timeout_seconds=180)
    elif approval.method == 'ours':
        from ehrqa.clinsql.proposed_runner import ProposedModelProvider
        model = ProposedModelProvider(api_ledger, model_id=MODEL, timeout_seconds=180,
                                      reasoning_effort='medium', max_output_tokens=None)
    else:
        model = OpenAIChatMultiProvider(api_ledger, model_id=MODEL, timeout_seconds=180,
                                        reasoning_effort='medium', max_completion_tokens=None,
                                        group_nine=approval.variant == 'grouped_3x3')
    state_path = (STATE / 'state.sqlite' if approval.method == 'sde_sql' and not retry_uncapped
                  else continuation / 'state.sqlite')
    state = _pilot_state(state_path, master)
    existing = {row.case_id: row for row in state.checkpoints('FOUR_METHOD_PILOT_5')
                if row.method == approval.method}
    approved_sampler = None
    if approval.variant == 'column_samples':
        samples = None

        def approved_sampler(tracked, schema, keys):
            nonlocal samples
            if samples is None:
                samples = _prepare_mac_samples(approval, manifest, index, sql_ledger, config)
            return samples
    for question in _questions(pilot, master):
        if getattr(args, 'case_id', None) and args.case_id != question.query_id:
            continue
        prior = existing.get(question.query_id)
        if prior and prior.status == 'MODEL_GENERATION_FAILURE':
            path = continuation / (digest([approval.method, question.query_id]) + '.json')
            if not path.is_file() or sha256_file(path) != prior.artifact_sha256:
                raise PermissionError('Prior failure checkpoint hash mismatch')
            print(json.dumps({'case_id': question.query_id, 'status': prior.status, 'resumed': True}))
            continue
        record = run_case(question, state=state, approval=approval, pilot=pilot, schema_index=index,
                          store=store, output_root=continuation, model=model, clinical=clinical, few_shot=fewshot,
                          recovered_probe=recovered.get(question.query_id),
                          approved_sampler=approved_sampler,
                          database=_database(approval, manifest, index, question.query_id, sql_ledger, config))
        print(json.dumps({'case_id': question.query_id, 'status': record['status']}))
        if record['status'] not in {'EXECUTED', 'MODEL_SQL_ERROR', 'MODEL_ABSTAINED', 'MODEL_GENERATION_FAILURE'}:
            return 1
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    plan = commands.add_parser('plan')
    plan.add_argument('--method', choices=[method for method in VARIANTS
                                           if method in (*METHODS, 'catalog_export', 'sde_transport')], required=True)
    plan.add_argument('--variant', required=True)
    plan.add_argument('--catalog', type=Path)
    commands.add_parser('reuse-cot')
    commands.add_parser('task6-synthetic-sde')
    commands.add_parser('task7-diagnose-sde-n9')
    commands.add_parser('task7-verify-grouped-sde')
    retention = commands.add_parser('retention')
    retention.add_argument('--delete-expired', action='store_true')
    execute = commands.add_parser('execute')
    prepare_mac = commands.add_parser('prepare-mac')
    prepare_mac.add_argument('--api-budget', type=Path, required=True)
    export = commands.add_parser('export-catalog')
    for command in (execute, export, prepare_mac):
        command.add_argument('--approval', type=Path, required=True)
        command.add_argument('--sql-budget', type=Path, required=True)
        command.add_argument('--credit', type=Path, required=True)
    execute.add_argument('--api-budget', type=Path, required=True)
    execute.add_argument('--catalog', type=Path)
    execute.add_argument('--local-model', help='Model alias from llama.cpp listening on 127.0.0.1:18082')
    execute.add_argument('--restricted-local-model', help='Use loopback inference for restricted evidence')
    execute.add_argument('--restricted-local-port', type=int, default=18082, help='Loopback inference port')
    execute.add_argument('--retry-evidence', action='store_true', help='Retry settled evidence-stage failures')
    execute.add_argument('--structured-retry', action='store_true', help='Retry a settled evidence failure')
    execute.add_argument('--backend-retry', action='store_true', help='Retry Ours with an alternate loopback model')
    execute.add_argument('--case-id', help='Run just this pinned pilot case')
    execute.add_argument('--retry-uncapped-sde', action='store_true')
    execute.add_argument('--resume-incomplete-probe', action='store_true')
    reconcile = commands.add_parser('reconcile-sql')
    reconcile.add_argument('--approval', type=Path, required=True)
    reconcile.add_argument('--sql-budget', type=Path, required=True)
    reconcile.add_argument('--credit', type=Path, required=True)
    export.add_argument('--destination', required=True)
    smoke = commands.add_parser('check-sde-transport')
    smoke.add_argument('--approval', type=Path, required=True)
    smoke.add_argument('--api-budget', type=Path, required=True)
    stage = commands.add_parser('check-staging')
    stage.add_argument('--record', type=Path, required=True)
    args = parser.parse_args()
    master, pilot, manifest, index = _scope()
    if args.command == 'plan':
        cat = sha256_file(args.catalog) if args.catalog else None
        print(json.dumps({'method': args.method, 'variant': args.variant,
                          'configuration_sha256': configuration(args.method, args.variant, cat),
                          'catalog_sha256': cat, 'schema_sha256': manifest['sha256'],
                          'index_sha256': index.index['sha256'], 'pilot_sha256': pilot['sha256'],
                          'case_ids': [args.method] if args.method in {'catalog_export', 'sde_transport'}
                          else master['pilot_case_ids'],
                          'mac_column_sample_queries_per_case': _sample_count(index) if args.method == 'mac_sql' else None,
                          'queries': catalog_queries(manifest) if args.method == 'catalog_export' else None}, indent=2))
        return 0
    store = ResultArtifactStore(STORE, verify_private_acl=_private_acl)
    if args.command == 'task6-synthetic-sde':
        return _task6_synthetic(store)
    if args.command == 'task7-diagnose-sde-n9':
        return _task6_synthetic(store, diagnose_n9=True)
    if args.command == 'task7-verify-grouped-sde':
        return _verify_grouped_sde(store)
    if args.command == 'retention':
        from ehrqa.clinsql.pilot_retention import inspect_or_delete_expired
        for method in ('mac_sql', 'sde_sql', 'ours'):
            root = STATE / method
            if root.is_dir():
                _protected_root(store, root)
                print(json.dumps(inspect_or_delete_expired(root, STORE,
                    delete_expired=args.delete_expired), indent=2))
        return 0
    if args.command == 'prepare-mac':
        approval = _approval(args, manifest, index)
        approval.verify_pilot(pilot)
        if approval.method != 'mac_sql' or approval.variant != 'column_samples':
            raise PermissionError('Database preprocessing requires the approved MAC sample scope')
        config = BigQueryConfig.from_env()
        credit = _credit(args, approval, config)
        _, limits = _budgets(approval, args.api_budget, args.sql_budget, sample_count=_sample_count(index))
        _source_check('mac_sql')
        _protected_root(store, STATE)
        ledger = PersistentSQLBudgetLedger(STATE / 'research_sql.sqlite', limits, method='mac_sql', credit=credit)
        _prepare_mac_samples(approval, manifest, index, ledger, config)
        return 0
    if args.command == 'execute':
        return _run(args, store, master, pilot, manifest, index)
    if args.command == 'reconcile-sql':
        from google.cloud import bigquery
        approval = FourMethodApproval.from_file(args.approval)
        if approval.method == 'sde_transport' or approval.manifest_sha256 != manifest['sha256']:
            raise PermissionError('SQL reconciliation requires the original BigQuery scope')
        config = BigQueryConfig.from_env()
        credit = _credit(args, approval, config, check_expiry=False)
        raw = args.sql_budget.read_bytes()
        if hashlib.sha256(raw).hexdigest() != approval.sql_budget_sha256:
            raise PermissionError('SQL budget differs from original approval')
        ledger_path = STATE / 'research_sql.sqlite'
        if not ledger_path.is_file():
            raise FileNotFoundError('No research SQL ledger')
        _protected_root(store, STATE)
        ledger = PersistentSQLBudgetLedger(ledger_path, SQLBudgetLimits(**json.loads(raw)),
                                           method=approval.method, credit=credit)
        credentials = verify_reader_adc()
        client = bigquery.Client(project=config.billing_project, location=config.location,
                                 credentials=credentials)
        for job_id in ledger.pending_jobs():
            try:
                status = ledger.reconcile_job(job_id, client=client, project=config.billing_project,
                                              location=config.location)
            except Exception as exc:
                status = f'UNKNOWN_BILLING:{type(exc).__name__}'
            print(json.dumps({'job_id': job_id, 'status': status}))
        return 0
    if args.command == 'check-sde-transport':
        approval = _approval(args, manifest, index)
        if approval.method != 'sde_transport' or os.environ.get('OPENAI_MODEL') != MODEL:
            raise PermissionError('Synthetic transport scope and pinned model required')
        api, _ = _budgets(approval, args.api_budget, None)
        root = STATE / 'sde_transport'
        _protected_root(store, root)
        ledgers = _ledger_root(store, root, approval)
        ledger = PersistentAPIBudgetLedger(ledgers / 'api.sqlite', api)
        model = OpenAIChatMultiProvider(ledger, model_id=MODEL, max_completion_tokens=512)
        with (root / (approval.approval_id + '.started')).open('x', encoding='utf-8'):
            pass
        for n in (9, 3):
            replies = model.generate('sde.synthetic_transport', 'Return exactly: SELECT 1', n=n)
            print(json.dumps({'model': MODEL, 'requested': n, 'received': len(replies)}))
        with tempfile.NamedTemporaryFile(mode='w', dir=root, delete=False, encoding='utf-8') as stream:
            json.dump({'model': MODEL, 'choices': [9, 3],
                       'configuration_sha256': approval.configuration_sha256}, stream)
            verified = Path(stream.name)
        verified.replace(root / 'verified.json')
        return 0
    if args.command == 'export-catalog':
        approval = _approval(args, manifest, index)
        if approval.method != 'catalog_export' or not args.destination.endswith('.json') or (
            Path(args.destination).name != args.destination or ':' in args.destination
        ):
            raise PermissionError('Dictionary-only approval and a safe JSON basename required')
        _, sql = _budgets(approval, None, args.sql_budget)
        verify_reader_adc()
        root = STATE / 'catalog'
        _protected_root(store, root)
        destination = root / args.destination
        if destination.exists():
            raise FileExistsError(destination)
        ledgers = _ledger_root(store, root, approval)
        config = BigQueryConfig.from_env()
        credit = _credit(args, approval, config)
        ledger = PersistentSQLBudgetLedger(STATE / 'research_sql.sqlite', sql,
                                           method=approval.method, credit=credit)
        db = _database(approval, manifest, index, 'catalog_export', ledger, config)
        with (root / (approval.approval_id + '.started')).open('x', encoding='utf-8') as stream:
            stream.write(args.destination)
        exported = export_catalog(db, manifest, destination,
                                  source=f"BigQuery {manifest['project_id']} MIMIC-IV 3.1",
                                  authorization=approval.policy_reference)
        ClinicalCatalog.load(destination, expected_sha256=exported['sha256'], schema_sha256=manifest['sha256'])
        with (ledgers / 'export_receipt.json').open('x', encoding='utf-8') as stream:
            json.dump(exported, stream, indent=2)
        print(json.dumps(exported))
        return 0
    questions = _questions(pilot, master)
    if args.command == 'reuse-cot':
        root = STATE / 'clinsql_cot'
        _protected_root(store, STATE)
        _protected_root(store, root)
        state = _pilot_state(STATE / 'state.sqlite', master)
        audit = read_json(ROOT / 'results/phase_c1_pilot_audit.json')
        for question in questions:
            record = reuse_cot(question, state=state, audit=audit, store=store, output_root=root)
            print(json.dumps({'case_id': question.query_id, 'status': record['status']}))
        return 0
    record = read_json(args.record)
    question = next(q for q in questions if q.query_id == record['case_id'])
    _protected_root(store, STATE)
    state = _pilot_state(STATE / 'state.sqlite', master)
    checkpoint = next((row for row in state.checkpoints('FOUR_METHOD_PILOT_5')
                       if row.method == record['method'] and row.case_id == question.query_id), None)
    if checkpoint is None or checkpoint.artifact_sha256 != sha256_file(args.record):
        raise PermissionError('Staging requires the verified saved checkpoint')
    import shutil
    target = STATE / ('staging_' + uuid.uuid4().hex)
    target.mkdir()
    try:
        _protected_root(store, target)
        stage_saved_prediction(record, question, store=store, root=target, benchmark_root=BENCHMARK)
    finally:
        shutil.rmtree(target)
    print('Local staging verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
