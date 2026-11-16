"""Common method dispatch, durable pilot checkpoints and local evaluation staging."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import time

from ehrqa.agentic.trace import digest
from ehrqa.text2sql.logging import MeteredDatabase, MeteredModel, RunLog

from .baselines.mac_sql import MACSQL
from .baselines.sde_sql import SDESQL
from .benchmark_approval import BenchmarkExecutionApproval
from .chat_multi_provider import MAC_MODEL_PARAMETER_ADAPTATION
from .evaluator import prepare_official_sample
from .execution_errors import IncompleteResultError, SecurityRejected, classify_execution_failure
from .interfaces import Execution
from .openai_provider import AmbiguousModelRequest, ModelGenerationFailure, ModelUsageUnknown
from .benchmark_model import BENCHMARK_LLM as MODEL, ModelMismatch, require_benchmark_model
from .evidence_router import RestrictedEvidenceEgress


def build_pipeline(*args, **kwargs):
    from .proposed import build_pipeline as build
    return build(*args, **kwargs)

PHASE = 'FOUR_METHOD_PILOT_5'


VARIANTS = {
    'mac_sql': {'metadata_only': {'A', 'C', 'E'}, 'column_samples': {'A', 'C', 'D', 'E'}},
    'sde_sql': {'probe_labels_only': {'A', 'C', 'E'}, 'grouped_3x3': {'A', 'C', 'E'}},
    'ours': {'dictionary_rag': {'A', 'B', 'C', 'E'}},
    'catalog_export': {'local_dictionary': {'B'}},
    'sde_transport': {'synthetic_only': set()},
}


@dataclass(frozen=True, kw_only=True)
class FourMethodApproval(BenchmarkExecutionApproval):
    expected_phase = 'four_method_validation_pilot'
    phase: str = 'four_method_validation_pilot'
    method: str
    variant: str
    evidence: dict
    policy_reference: str
    index_sha256: str
    catalog_sha256: str | None
    configuration_sha256: str
    credit_sha256: str | None = None

    def _valid_case_scope(self):
        if self.method in {'catalog_export', 'sde_transport'}:
            return self.case_ids == (self.method,)
        return super()._valid_case_scope()

    def __post_init__(self):
        super().__post_init__()
        required = VARIANTS.get(self.method, {}).get(self.variant)
        allowed = {'A': 'question_and_schema', 'B': 'dictionary_metadata',
                   'C': 'sql_and_sanitized_errors', 'D': 'approved_column_samples',
                   'E': ('shape_and_row_counts' if self.method == 'ours' else
                         'probe_labels_and_column_names' if self.method == 'sde_sql' else
                         'row_presence_and_null')}
        if (required is None or not isinstance(self.policy_reference, str) or not self.policy_reference.strip() or
            self.evidence != {key: allowed[key] for key in required}):
            raise ValueError('Method-specific evidence authorization is missing or too broad')
        if self.model_id != MODEL or not 1 <= self.artifact_retention_days <= 7:
            raise ValueError('Pinned model and retention scope required')
        pins = [self.index_sha256, self.configuration_sha256]
        if self.method == 'ours':
            pins.append(self.catalog_sha256)
        if any(not isinstance(pin, str) or len(pin) != 64 or
               any(char not in '0123456789abcdef' for char in pin) for pin in pins):
            raise ValueError('Method configuration requires SHA-256 pins')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_case(question, approval, pilot, master, schema_index):
    approval.verify_active()
    approval.verify_pilot(pilot)
    payload = {key: value for key, value in pilot.items() if key != 'sha256'}
    actual = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if (actual != master['pilot_manifest_sha256'] or actual != approval.pilot_manifest_sha256 or
        schema_index.index['sha256'] != approval.index_sha256 or
        master['schema_index_sha256'] != approval.index_sha256 or
        schema_index.index['schema_sha256'] != approval.manifest_sha256):
        raise PermissionError('Pilot or schema scope differs from approval')
    case = next((row for row in pilot['cases'] if row['case_id'] == question.query_id), None)
    if (question.split != 'validation' or case is None or case['split'] != 'validation' or
        question.query_id not in master['development_case_ids'] or
        case['question_sha256'] != hashlib.sha256(question.text.encode()).hexdigest()):
        raise PermissionError('Question differs from pinned validation pilot')


def _failure(exc):
    if isinstance(exc, ModelMismatch):
        return 'MODEL_MISMATCH'
    if isinstance(exc, RestrictedEvidenceEgress):
        return 'RESTRICTED_EVIDENCE_EGRESS'
    if isinstance(exc, AmbiguousModelRequest):
        return 'MODEL_REQUEST_OUTCOME_UNKNOWN'
    if isinstance(exc, ModelUsageUnknown):
        return 'MODEL_USAGE_UNKNOWN'
    if isinstance(exc, ModelGenerationFailure):
        return 'MODEL_GENERATION_FAILURE'
    if isinstance(exc, PermissionError) and 'budget' in str(exc).lower():
        return 'BUDGET_EXCEEDED'
    return classify_execution_failure(exc, stage='execute')


class _StopOnSecurityViolation(MeteredDatabase):
    def probe_presence(self, sql):
        try:
            return super().probe_presence(sql)
        except SecurityRejected:
            raise PermissionError('SECURITY_REJECTED') from None

    def dry_run(self, sql, **kwargs):
        try:
            return super().dry_run(sql, **kwargs)
        except SecurityRejected:
            raise PermissionError('SECURITY_REJECTED') from None

    def _call(self, stage, sql, **kwargs):
        try:
            return super()._call(stage, sql, **kwargs)
        except SecurityRejected:
            raise PermissionError('SECURITY_REJECTED') from None


def execute_method(method, question, model, database, *, variant, schema_index=None,
                   clinical=None, few_shot=None, trace_root=None, exploration_checkpoint=None,
                   saved_probe=None, approved_sampler=None):
    if method == 'mac_sql':
        return MACSQL(model, database, value_evidence=lambda *_: '',
                      sample_approved_values=variant == 'column_samples', approved_sampler=approved_sampler).run(question.text)
    if method == 'sde_sql':
        return SDESQL(model, database, allow_probe_feedback=True, exploration_checkpoint=exploration_checkpoint,
                      saved_probe=saved_probe).run(
            question.text, schema_text='\n'.join(row['ddl'] for row in database.schema_metadata()))
    if method != 'ours' or clinical is None or few_shot is None or schema_index is None:
        raise ValueError('Ours requires a pinned schema, clinical catalog and few-shot corpus')
    output = build_pipeline(database, model, schema_index=schema_index, icd_catalog=clinical,
                            few_shot_index=few_shot, log_dir=trace_root).run(
                                question.text, query_id=question.query_id)
    result = None
    if output['selected'] is not None:
        value = output['selected']['result']
        result = Execution(tuple(value.columns), tuple(value.rows), value.complete,
                           column_types=value.column_types, job_id=value.job_id)
    return {'sql': output['sql'], 'status': output['status'], 'result': result,
            'reason': output['reason'], 'trace_path': output['trace_path']}


def _checkpoint(state, method, case_id):
    return next((row for row in state.checkpoints(PHASE)
                 if row.method == method and row.case_id == case_id), None)


def _replay(state, method, case_id, path, scope):
    row = _checkpoint(state, method, case_id)
    if row is None:
        return None
    if row.status == 'STARTED' or not path.is_file() or sha256_file(path) != row.artifact_sha256:
        raise FileExistsError('Interrupted or mismatched checkpoint requires reconciliation')
    saved = read_json(path)
    if saved['scope_sha256'] != scope:
        raise PermissionError('Saved run has a different approval or configuration')
    return saved


def _save(state, method, case_id, path, record, terminal):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
    state.finish(PHASE, method, case_id, status=terminal, artifact_sha256=sha256_file(path))
    return record


def run_case(question, *, state, approval, pilot, schema_index, store, output_root,
             model, database, clinical=None, few_shot=None, recovered_probe=None, approved_sampler=None):
    if type(approval) is not FourMethodApproval or approval.method not in {'mac_sql', 'sde_sql', 'ours'}:
        raise PermissionError('A separate four-method pilot approval is required')
    verify_case(question, approval, pilot, state.manifest, schema_index)
    require_benchmark_model(model.model_id)
    if approval.method == 'ours' and getattr(clinical, 'sha256', None) != approval.catalog_sha256:
        raise PermissionError('Clinical catalog differs from the approved snapshot')
    method = approval.method
    scope = digest(approval.__dict__)
    root = Path(output_root)
    if not store.verify_private_acl(store.root) or not store.verify_private_acl(root):
        raise PermissionError('Restricted storage ACL is required')
    path = root / (digest([method, question.query_id]) + '.json')
    previous = _replay(state, method, question.query_id, path, scope)
    if previous is not None:
        return previous
    state.claim(PHASE, method, question.query_id)
    log = RunLog(question.query_id, method)
    research = getattr(getattr(database, 'ledger', None), 'credit', None) is not None
    tracked_db = (_StopOnSecurityViolation if research else MeteredDatabase)(database, log)
    record = {'method': method, 'variant': approval.variant, 'case_id': question.query_id,
              'scope_sha256': scope, 'question_sha256': hashlib.sha256(question.text.encode()).hexdigest()}
    record.update(run_id=digest([scope, question.query_id]), model_id=model.model_id,
                  schema_sha256=approval.manifest_sha256, configuration_sha256=approval.configuration_sha256)
    record['inference_backend'] = 'openai'
    if method == 'mac_sql' and approval.variant == 'metadata_only':
        record['adaptation'] = 'MAC_SQL_RESTRICTED_ADAPTATION'
    if method == 'mac_sql':
        record['model_parameter_adaptation'] = MAC_MODEL_PARAMETER_ADAPTATION
    if method == 'sde_sql' and approval.variant == 'grouped_3x3':
        record['adaptation'] = 'SDE_GROUPED_3X3_REQUEST_ADAPTATION'
    stage = 'inference'
    started = time.monotonic()
    try:
        exploration_checkpoint = None
        saved_probe = None
        if method == 'sde_sql':
            exploration_checkpoint = root / ('exploration_' + digest([scope, question.query_id]))
            exploration_checkpoint.mkdir(exist_ok=True)
            if not store.verify_private_acl(exploration_checkpoint):
                raise PermissionError('SDE exploration checkpoint ACL failed')
            if recovered_probe is not None:
                probe_sql, job_id = recovered_probe
                evidence = database.recover_probe_presence(probe_sql, job_id)
                log.add('probe_recovered', sql=probe_sql, job_id=job_id, total_rows=evidence.total_rows,
                        has_rows=evidence.has_rows)
                saved_probe = probe_sql, evidence
        prediction = execute_method(method, question, MeteredModel(model, log), tracked_db,
                                    variant=approval.variant, schema_index=schema_index,
                                    clinical=clinical, few_shot=few_shot, trace_root=root / 'traces',
                                    exploration_checkpoint=exploration_checkpoint, saved_probe=saved_probe,
                                    approved_sampler=approved_sampler)
        sql, status, result = prediction['sql'], prediction['status'], prediction['result']
        record.update(sql=sql, inference_status=status, trace_path=prediction.get('trace_path'))
        if prediction.get('attempts') is not None:
            record['attempts'] = prediction['attempts']
        if status in {'corrected_unexecuted', 'judge_modified_unexecuted'}:
            stage = 'evaluation_execution'
            log.add(stage, sql=sql)
            if not tracked_db.dry_run(sql).valid:
                raise ValueError('Final SQL failed evaluation dry run')
            result = tracked_db.execute(sql)
        if result is None:
            reason = prediction.get('reason')
            record['status'] = (reason if reason in {'INCOMPLETE_RESULT', 'PERMISSION_DENIED',
                'BUDGET_EXCEEDED', 'RESOURCE_BUDGET_BLOCKED', 'TIMEOUT', 'INFRASTRUCTURE_ERROR', 'MODEL_REQUEST_OUTCOME_UNKNOWN',
                'MODEL_USAGE_UNKNOWN', 'MODEL_GENERATION_FAILURE', 'SECURITY_REJECTED',
                'RESTRICTED_EVIDENCE_EGRESS', 'MODEL_MISMATCH'} else
                'MODEL_SQL_ERROR' if status == 'unresolved' else
                'MODEL_ABSTAINED' if status == 'abstained' else 'MODEL_GENERATION_FAILURE')
            terminal = ('MODEL_SQL_ERROR' if record['status'] == 'MODEL_SQL_ERROR' else
                        'MODEL_GENERATION_FAILURE' if record['status'] in {
                            'MODEL_GENERATION_FAILURE', 'MODEL_ABSTAINED'} else
                        'INFRASTRUCTURE_BLOCKED')
        else:
            if not isinstance(sql, str) or not sql.strip() or not result.complete:
                raise IncompleteResultError('Missing final SQL or incomplete final result')
            stage = 'artifact_storage'
            artifact = store.save('pilot_' + digest([scope, question.query_id]), result)
            expiry = datetime.now(timezone.utc) + timedelta(days=approval.artifact_retention_days)
            log.add('result_artifact', **artifact, artifact_expires_at_utc=expiry.isoformat())
            record.update(status='EXECUTED', artifact=artifact, artifact_expires_at_utc=expiry.isoformat())
            terminal = 'EXECUTED'
    except Exception as exc:
        status = _failure(exc) if stage != 'artifact_storage' else 'ARTIFACT_STORAGE_ERROR'
        if isinstance(exc, PermissionError) and str(exc) == 'SECURITY_REJECTED':
            status = 'SECURITY_REJECTED'
        if stage == 'inference' and isinstance(exc, ValueError):
            status = 'MODEL_GENERATION_FAILURE'
        record.update(status=status, failure_stage=stage, error_type=type(exc).__name__)
        if isinstance(exc, RestrictedEvidenceEgress):
            record['egress_block'] = {'stage': exc.stage, 'category': exc.category}
        if isinstance(exc, ModelGenerationFailure):
            record['generation_failure'] = {'usage': exc.usage, 'response_id': exc.response_id,
                                            'incomplete_reason': exc.incomplete_reason}
        terminal = ('MODEL_SQL_ERROR' if status in {'SQL_EXECUTION_ERROR', 'SQL_SYNTAX_ERROR', 'SECURITY_REJECTED'}
                    and stage == 'evaluation_execution' else 'MODEL_GENERATION_FAILURE'
                    if status == 'MODEL_GENERATION_FAILURE' else 'INFRASTRUCTURE_BLOCKED')
    usage = log.summary()
    record.update(events=log.events, usage=usage, latency_seconds=time.monotonic() - started)
    return _save(state, method, question.query_id, path, record, terminal)


def reuse_cot(question, *, state, audit, store, output_root):
    if (question.split != 'validation' or audit['pilot_manifest_sha256'] != state.manifest['pilot_manifest_sha256']
        or question.query_id not in state.manifest['pilot_case_ids'] or audit['model_id'] != MODEL or
        audit['schema_sha256'] != state.manifest['schema_sha256']):
        raise PermissionError('Saved CoT run differs from the pinned pilot')
    if not store.verify_private_acl(output_root):
        raise PermissionError('Restricted checkpoint storage is required')
    entry = audit['cases'][question.query_id]
    source = read_json(entry['run_log'])
    prediction = next(e for e in source['events'] if e['stage'] == 'prediction')
    artifact = next(e for e in source['events'] if e['stage'] == 'result_artifact')
    execution = next((e for e in source['events'] if e['stage'] == 'execute'
                      and e.get('job_id') == artifact['job_id']), {})
    if (source['summary']['query_id'] != question.query_id or prediction['status'] != 'executed'
        or execution.get('sql') != prediction['sql'] or not execution.get('complete')
        or artifact['sha256'] != entry['artifact_sha256'] or artifact['job_id'] != entry['job_id']):
        raise ValueError('Saved CoT prediction differs from audited artifact')
    scope = digest(entry)
    path = Path(output_root) / (digest(['clinsql_cot', question.query_id]) + '.json')
    previous = _replay(state, 'clinsql_cot', question.query_id, path, scope)
    if previous is not None:
        return previous
    expiry = datetime.fromisoformat(artifact['artifact_expires_at_utc'])
    if datetime.now(timezone.utc) >= expiry:
        raise PermissionError('CoT result artifact retention has expired')
    result = store.load(artifact['artifact_id'], expected_sha256=artifact['sha256'])
    if result.job_id != artifact['job_id'] or len(result.rows) != entry['row_count']:
        raise ValueError('CoT stored result differs from audit')
    record = {'method': 'clinsql_cot', 'case_id': question.query_id, 'scope_sha256': scope,
              'sql': prediction['sql'], 'status': 'EXECUTED', 'source_run_log': entry['run_log'],
              'artifact': artifact, 'artifact_expires_at_utc': artifact['artifact_expires_at_utc'],
              'question_sha256': hashlib.sha256(question.text.encode()).hexdigest()}
    state.claim(PHASE, 'clinsql_cot', question.query_id)
    return _save(state, 'clinsql_cot', question.query_id, path, record, 'EXECUTED')


def stage_saved_prediction(record, question, *, store, root, benchmark_root, now=None):
    now = now or datetime.now(timezone.utc)
    if (record['case_id'] != question.query_id or record['status'] != 'EXECUTED' or
        record['question_sha256'] != hashlib.sha256(question.text.encode()).hexdigest() or
        record['method'] not in {'clinsql_cot', 'mac_sql', 'sde_sql', 'ours'}):
        raise ValueError('Staging requires an executable prediction for this question')
    if now >= datetime.fromisoformat(record['artifact_expires_at_utc']):
        raise PermissionError('Result artifact retention has expired')
    if not store.verify_private_acl(root):
        raise PermissionError('Restricted evaluation staging required')
    artifact = record['artifact']
    result = store.load(artifact['artifact_id'], expected_sha256=artifact['sha256'])
    if result.job_id != artifact['job_id']:
        raise ValueError('Final result job differs from the saved artifact')
    return prepare_official_sample(Path(root) / record['method'], benchmark_root, question,
                                   record['sql'], result)
