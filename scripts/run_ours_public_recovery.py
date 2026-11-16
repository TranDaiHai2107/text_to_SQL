"""Run the five authorized development cases with an independent public corpus."""
import argparse
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from run import load_research_env
from ehrqa.cli import four_method_pilot as pilot_cli
from ehrqa.clinsql.benchmark_model import require_benchmark_model
from ehrqa.clinsql.public_terminology import (
    ARCHIVES, PROFILE, PublicClinicalCatalog, PublicTerminologyModelProvider, compare_local_records,
)


EASY_058 = 'Diagnostic_Procedures/easy_level_queries/058'
APPROVAL_SUFFIX = '20261122_0900'
V4_TRACE_SHA256 = '3b42d3526d436342971099403e2cf48fb60346c1a5adb104d315814216798fa3'
# v5: public ICD-10-PCS, per-dictionary retrieval quota, constant-false filter
# check, and fail-open fallbacks recorded per case.
V5_REVISION = 'ours_fail_open_v5_20261116'


def procedure_recovery(store, master, pilot, manifest, index):
    """Replay the accepted Easy/058 linker and stop before any network access."""
    from collections import Counter
    from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
    from ehrqa.clinsql.offline import MockBigQuery
    from ehrqa.clinsql.procedure_grounding import CodeSetBlocked, REVIEW, TOP_K_PER_VERSION, procedure_evidence
    from ehrqa.clinsql.proposed import build_pipeline

    cli = pilot_cli
    root = cli.STATE / 'ours/public_terminology_anchored_v4'
    record_path = root / (cli.digest(['ours', EASY_058]) + '.json')
    if not store.verify_private_acl(root):
        raise PermissionError('Protected checkpoint folder required')
    with sqlite3.connect((root / 'state.sqlite').as_uri() + '?mode=ro', uri=True) as db:
        saved = db.execute('SELECT artifact_sha256 FROM case_runs WHERE phase=? AND method=? AND case_id=?',
                           ('FOUR_METHOD_PILOT_5', 'ours', EASY_058)).fetchone()
    if not saved or saved[0] != cli.sha256_file(record_path):
        raise ValueError('Saved Ours prediction checkpoint differs from ledger')
    trace = Path(cli.read_json(record_path)['trace_path'])
    if (trace.is_symlink() or not trace.resolve().is_relative_to(root.resolve()) or
            not store.verify_private_acl(trace.parent) or cli.sha256_file(trace) != V4_TRACE_SHA256):
        raise ValueError('Saved Ours linker trace differs from pin')
    with trace.open(encoding='utf-8') as stream:
        events = [json.loads(line) for line in stream]
    link_input = next(e['input'] for e in events if e['stage'] == 'model.request' and e['operation'] == 'link')
    links = next(e['links'] for e in events if e['stage'] == 'schema.forward_linking')
    questions = cli._questions(pilot, master)
    ordinal = next(i for i, row in enumerate(questions) if row.query_id == EASY_058)
    question = questions[ordinal]
    if link_input['original_question'] != question.text:
        raise ValueError('Saved linker belongs to a different question')
    approved = cli.FourMethodApproval.from_file(cli.STATE / 'task8_20261115' /
                                              f'ours_approval_{APPROVAL_SUFFIX}.json')
    catalog_path = cli.STATE / 'catalog/clinical_catalog_task8_20261115.json'
    if not store.verify_private_acl(catalog_path.parent):
        raise PermissionError('Protected procedure dictionary folder required')
    local = ClinicalCatalog.load(catalog_path, expected_sha256=approved.catalog_sha256,
                                 schema_sha256=manifest['sha256'])

    class NoInference:
        def complete(self, *_args, **_kwargs):
            raise AssertionError('Procedure recovery ended before paid inference')

    blocked = []

    def ground(accepted_links):
        try:
            return procedure_evidence(local, accepted_links)
        except CodeSetBlocked as error:
            blocked.extend(error.candidates)
            raise

    public = PublicClinicalCatalog(cli.ROOT / 'data/clinsql/public_terminology')
    db = MockBigQuery(index.schema_records())
    workflow = build_pipeline(db, NoInference(), schema_index=index, icd_catalog=public,
                              procedure_grounding=ground)
    output = workflow.run(question.text, query_id=question.query_id, saved_linking=links)
    if output['model_calls'] != 0 or db.calls or not blocked:
        raise RuntimeError('Saved grounding preflight did not reach the expected offline stop')
    print(json.dumps({
        'case_id': question.query_id, 'status': output['reason'], 'api_calls': 0, 'bigquery_jobs': 0,
        'top_k_per_version': TOP_K_PER_VERSION,
        'candidates_by_version': Counter(r['icd_version'] for r in blocked),
        'official_evidence_by_version': Counter(r['icd_version'] for r in blocked if r['official_sources']),
        'legacy_ambiguous': [[r['icd_version'], r['icd_code']] for r in blocked
                             if r['status'] == 'AMBIGUOUS_LEGACY_CODE'],
        'catalog_sha256': local.sha256, 'trace_sha256': V4_TRACE_SHA256,
        'candidate_sha256': cli.digest(blocked),
    }), flush=True)
    if output['reason'] == REVIEW:
        next_question = questions[ordinal + 1]
        schema_context = workflow.rag.schema(next_question.text)
        assert schema_context.get('tables') and not db.calls
        print(json.dumps({'case_id': next_question.query_id, 'status': 'OFFLINE_SCHEMA_SMOKE_PASS',
                          'schema_tables': len(schema_context['tables']), 'api_calls': 0,
                          'bigquery_jobs': 0}), flush=True)
    return 0


def compare_saved_linker(store, catalog, master):
    root = pilot_cli.STATE / 'ours/source_aligned_next_run'
    state = pilot_cli._pilot_state(root / 'state.sqlite', master)
    checkpoint = next(row for row in state.checkpoints('FOUR_METHOD_PILOT_5')
                      if row.method == 'ours' and row.case_id == EASY_058)
    path = root / (pilot_cli.digest(['ours', EASY_058]) + '.json')
    if not store.verify_private_acl(root) or pilot_cli.sha256_file(path) != checkpoint.artifact_sha256:
        raise PermissionError('Original Easy/058 checkpoint could not be verified')
    record = pilot_cli.read_json(path)
    trace = Path(record['trace_path'])
    if (trace.is_symlink() or not trace.resolve().is_relative_to(root.resolve())
            or not store.verify_private_acl(trace.parent)):
        raise PermissionError('Original linker trace is outside restricted storage')
    with trace.open(encoding='utf-8') as stream:
        events = map(json.loads, stream)
        payload = next(row['input'] for row in events if row.get('stage') == 'model.request'
                       and row.get('operation') == 'link' and row.get('query_id') == EASY_058)
    protected = payload['catalog']
    if len(protected) != 24 or len({item['id'] for item in protected}) != 24:
        raise ValueError('Original Easy/058 linker differs from the 24-record evidence set')
    return compare_local_records(catalog, protected)


def pin_profile(path, value):
    text = json.dumps(value, sort_keys=True, indent=2)
    try:
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text)
    except FileExistsError:
        if path.read_text(encoding='utf-8') != text:
            raise PermissionError('Public terminology profile changed after checkpoint creation') from None


def main():
    cli = pilot_cli
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--remaining-four', action='store_true',
                        help='Run the four other pinned cases after Easy/058 completes')
    parser.add_argument('--procedure-recovery', action='store_true',
                        help='Replay Easy/058 and check local procedure grounding')
    parser.add_argument('--all-five', action='store_true',
                        help='v5: run all five pinned cases in manifest order without the Easy/058 gate')
    args = parser.parse_args()
    if args.all_five and args.remaining_four:
        parser.error('--all-five already includes the remaining four cases')
    load_research_env(cli.ROOT / '.env', os.environ)
    master, pilot, manifest, index = cli._scope()
    if args.procedure_recovery:
        if args.execute or args.remaining_four or args.all_five:
            parser.error('Procedure recovery is an offline checkpoint replay')
        store = cli.ResultArtifactStore(cli.STORE, verify_private_acl=cli._private_acl)
        return procedure_recovery(store, master, pilot, manifest, index)
    approvals = cli.STATE / 'task8_20261115'
    original = cli.FourMethodApproval.from_file(approvals / f'ours_approval_{APPROVAL_SUFFIX}.json')
    original.verify_active()
    original.verify_pilot(pilot)
    cli.verify_task8_attestation(original, cli.ROOT, pilot)
    if (original.method != 'ours' or original.variant != 'dictionary_rag'
            or original.manifest_sha256 != manifest['sha256']
            or original.index_sha256 != index.index['sha256']):
        raise PermissionError('Public recovery is outside the pinned Ours scope')
    store = cli.ResultArtifactStore(cli.STORE, verify_private_acl=cli._private_acl)
    ledgers = cli.STATE / 'ours' / original.approval_id
    approval_pin = ledgers / f'approval_{APPROVAL_SUFFIX}.sha256'
    original_scope = cli.digest(original.__dict__)
    if not store.verify_private_acl(ledgers) or approval_pin.read_text(encoding='utf-8') != original_scope:
        raise PermissionError('Original Ours approval and ledger scope do not match')
    require_benchmark_model(os.environ.get('OPENAI_MODEL'))
    if os.environ.get('SEND_RESULTS_TO_LLM', '').lower() != 'false':
        raise PermissionError('Raw result transmission must remain disabled')
    api, sql = cli._budgets(original, approvals / 'ours_api.json', approvals / 'ours_sql.json')
    config = cli.BigQueryConfig.from_env()
    if (config.project_id != original.project_id or config.location.upper() != original.location.upper()
            or set(config.allowed_datasets) != set(original.datasets)):
        raise PermissionError('BigQuery environment differs from the Ours approval')
    credit = cli._credit(SimpleNamespace(credit=approvals / f'credit_{APPROVAL_SUFFIX}.json'), original, config)
    catalog = PublicClinicalCatalog(cli.ROOT / 'data/clinsql/public_terminology')
    counts = compare_saved_linker(store, catalog, master)
    profile = {'method_profile': PROFILE, 'original_execution_scope_sha256': original_scope,
               'catalog_sha256': catalog.sha256, 'public_source_archives': ARCHIVES,
               'pinned_ours_implementation': cli.configuration('ours', original.variant, catalog.sha256),
               'public_provider_sha256': cli.sha256_file(cli.ROOT / 'src/ehrqa/clinsql/public_terminology.py'),
               'link_interface': 'question_token_ranges_with_reserved_output_id_v3',
               **({'pipeline_revision': V5_REVISION} if args.all_five else {}),
               'runner_sha256': cli.sha256_file(Path(__file__)), 'original_058_comparison': counts,
               'public_catalog_size': len(catalog.records)}
    profile_sha = cli.digest(profile)
    approved_profile = replace(original, catalog_sha256=catalog.sha256, configuration_sha256=profile_sha)
    fewshot = cli._load_frozen_fewshot(master)
    print(json.dumps({'profile_sha256': profile_sha, **profile}), flush=True)
    if not args.execute:
        return 0
    cli.verify_reader_adc()
    root = cli.STATE / ('ours/public_terminology_v5' if args.all_five else 'ours/public_terminology_anchored_v4')
    cli._protected_root(store, root)
    pin_profile(root / 'profile.json', profile)
    state = cli.ExperimentState(root / 'state.sqlite', master)
    if not (ledgers / 'api.sqlite').is_file() or not (cli.STATE / 'research_sql.sqlite').is_file():
        raise PermissionError('Existing method and shared research ledgers are required')
    api_ledger = cli.PersistentAPIBudgetLedger(ledgers / 'api.sqlite', api)
    sql_ledger = cli.PersistentSQLBudgetLedger(cli.STATE / 'research_sql.sqlite', sql,
                                               method='ours', credit=credit)
    model = PublicTerminologyModelProvider(api_ledger, public_catalog=catalog, model_id=cli.MODEL,
                                          timeout_seconds=180, reasoning_effort='medium', max_output_tokens=None)
    if args.remaining_four:
        easy = next((row for row in state.checkpoints('FOUR_METHOD_PILOT_5')
                     if row.method == 'ours' and row.case_id == EASY_058), None)
        easy_path = root / (cli.digest(['ours', EASY_058]) + '.json')
        if (not easy or easy.status != 'EXECUTED' or not easy_path.is_file()
                or cli.sha256_file(easy_path) != easy.artifact_sha256):
            raise PermissionError('Remaining runs require the completed Easy/058 checkpoint')
    for question in cli._questions(pilot, master):
        if not args.all_five and (question.query_id == EASY_058) == args.remaining_four:
            continue
        record = cli.run_case(question, state=state, approval=approved_profile, pilot=pilot,
                              schema_index=index, store=store, output_root=root, model=model,
                              clinical=catalog, few_shot=fewshot,
                              database=cli._database(original, manifest, index, question.query_id, sql_ledger, config))
        print(json.dumps({'case_id': question.query_id, 'status': record['status'],
                          'final_sql': bool(record.get('sql')), 'artifact': record.get('artifact'),
                          'usage': record['usage'], 'fallbacks': record.get('fallbacks')}), flush=True)
        if not args.all_five and question.query_id == EASY_058 and record['status'] != 'EXECUTED':
            return 2
        if record['status'] not in {'EXECUTED', 'MODEL_SQL_ERROR', 'MODEL_ABSTAINED', 'MODEL_GENERATION_FAILURE'}:
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
