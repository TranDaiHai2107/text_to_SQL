"""Approved real CLINSQL CoT orchestration; no network at import time."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

from ehrqa.text2sql.logging import MeteredDatabase, MeteredModel, Pricing, RunLog

from .benchmark_approval import BenchmarkExecutionApproval
from .benchmark_model import require_benchmark_model
from .cot_runner import ClinSQLCoT
from .dataset import Question
from .execution_errors import classify_execution_failure
from .openai_provider import (AmbiguousModelRequest, ModelGenerationFailure,
                              ModelUsageUnknown, OpenAIModelProvider)
from .execution_errors import IncompleteResultError
from .result_artifacts import ResultArtifactStore
from .schema_index import SchemaIndex


class _CaptureCompleteExecution:
    def __init__(self, database):
        self.database = database
        self.last_sql = None
        self.last_result = None

    def schema_metadata(self):
        return self.database.schema_metadata()

    def dry_run(self, sql):
        return self.database.dry_run(sql)

    def execute(self, sql):
        result = self.database.execute(sql)
        self.last_sql, self.last_result = sql, result
        return result


def _runtime_code_sha256() -> str:
    root = Path(__file__).resolve().parents[3]
    paths = ('src/ehrqa/clinsql/real_cot_runner.py',
             'src/ehrqa/clinsql/cot_runner.py', 'src/ehrqa/clinsql/cot.py',
             'src/ehrqa/clinsql/openai_provider.py',
             'src/ehrqa/clinsql/benchmark_backend.py',
             'src/ehrqa/clinsql/bigquery_client.py',
             'src/ehrqa/clinsql/bigquery_adapter.py',
             'src/ehrqa/clinsql/execution_budget.py',
             'src/ehrqa/clinsql/pilot_api_budget.py',
             'src/ehrqa/clinsql/schema_index.py')
    digest = hashlib.sha256()
    for relative in paths:
        data = (root / relative).read_bytes()
        digest.update(relative.encode())
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()


def run_real_cot_case(question: Question, *, pilot_manifest: dict,
                      approval: BenchmarkExecutionApproval,
                      model: OpenAIModelProvider, database,
                      schema_index: SchemaIndex, result_store: ResultArtifactStore,
                      output_root: Path, model_id: str, pricing: Pricing,
                      code_commit: str | None = None,
                      api_budget_sha256: str | None = None,
                      sql_budget_sha256: str | None = None,
                      source_aligned: bool = False) -> dict:
    """One case only; marker is claimed before API/SQL, never auto-resumed."""
    if question.split != 'validation' or not isinstance(model, OpenAIModelProvider):
        raise PermissionError('Real CoT pilot requires validation input and OpenAI transport')
    underlying = database
    while hasattr(underlying, 'database'):
        underlying = underlying.database
    if getattr(underlying, 'is_synthetic_mock', False):
        raise TypeError('Real pilot cannot use MockBigQuery')
    approval.verify_pilot(pilot_manifest)
    approval.verify_active()
    case = next((row for row in pilot_manifest['cases'] if row['case_id'] == question.query_id), None)
    if case is None or case['question_sha256'] != hashlib.sha256(question.text.encode()).hexdigest():
        raise PermissionError('Question is outside the pinned five-case pilot manifest')
    for configured_id in (model.model_id, model_id, approval.model_id):
        require_benchmark_model(configured_id)
    records = database.schema_metadata()
    if {row.get('schema_sha256') for row in records} != {schema_index.index['schema_sha256']}:
        raise ValueError('Real runner schema differs from pinned index')
    if not result_store.verify_private_acl(result_store.root):
        raise PermissionError('Restricted result storage ACL must pass before inference')
    output_root = Path(output_root)
    path = output_root / (question.query_id.replace('/', '__') + '.json')
    marker = path.with_suffix('.started')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError('Prediction already exists; replay without model call')
    context = {'case_id': question.query_id, 'pilot_manifest_sha256': pilot_manifest['sha256'],
               'approval_id': approval.approval_id,
               'schema_sha256': schema_index.index['schema_sha256'],
               'schema_index_sha256': schema_index.index['sha256'],
               'model_id': model_id, 'code_commit': code_commit,
               'api_budget_sha256': api_budget_sha256,
               'sql_budget_sha256': sql_budget_sha256,
               'reasoning_effort': model.reasoning_effort,
               'max_output_tokens': model.max_output_tokens,
               'profile': 'SOURCE_ALIGNED_NEXT_RUN' if source_aligned else 'HISTORICAL_PILOT',
               'runtime_code_sha256': _runtime_code_sha256()}
    fingerprint = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump({'fingerprint': fingerprint, 'status': 'started'}, stream)
    log = RunLog(question.query_id, 'clinsql_cot', pricing)
    log.add('run_context', **context, fingerprint=fingerprint)
    capture = _CaptureCompleteExecution(MeteredDatabase(database, log, capture_rows=False))
    tracked_model = MeteredModel(model, log)
    schema_text = '\n'.join(row['ddl'] for row in records)
    try:
        prediction = ClinSQLCoT(tracked_model, capture, schema_text,
                                refine_guard_rejections=not source_aligned).run(
            question.query_id, question.text)
        artifact = None
        if prediction.status == 'executed':
            result = capture.last_result
            if (result is None or not result.complete or
                capture.last_sql != prediction.sql):
                raise RuntimeError('Incomplete or mismatched result; official evaluation blocked')
            artifact_id = 'pilot_' + fingerprint[:24]
            artifact = result_store.save(artifact_id, result)
            expires = datetime.now(timezone.utc) + timedelta(
                days=approval.artifact_retention_days)
            log.add('result_artifact', **artifact,
                    artifact_expires_at_utc=expires.isoformat())
        log.add('prediction', sql=prediction.sql or '', status=prediction.status,
                split='validation', configured_model_id=model_id,
                model_snapshot=model.model_id)
        log.save(path)
        return {'status': prediction.status, 'sql': prediction.sql,
                'log_path': str(path), 'artifact': artifact, 'usage': log.summary()}
    except Exception as exc:
        if isinstance(exc, AmbiguousModelRequest):
            log.add('llm_transport_error', operation='generation',
                    cause_type=exc.cause_type, http_status=exc.http_status,
                    latency_seconds=exc.latency_seconds or 0,
                    usage_status='UNKNOWN_RESERVED_IN_LEDGER')
        if isinstance(exc, ModelGenerationFailure) and exc.usage:
            log.add('llm_failure', operation='generation', model=exc.model,
                    model_snapshot=exc.model, response_id=exc.response_id,
                    input_tokens=exc.usage.get('prompt_tokens', 0),
                    output_tokens=exc.usage.get('completion_tokens', 0),
                    reasoning_tokens=exc.usage.get('reasoning_tokens', 0),
                    latency_seconds=exc.latency_seconds or 0,
                    incomplete_reason=exc.incomplete_reason,
                    error_type=type(exc).__name__)
        if isinstance(exc, AmbiguousModelRequest):
            status = 'MODEL_REQUEST_OUTCOME_UNKNOWN'
        elif isinstance(exc, ModelGenerationFailure):
            status = 'MODEL_GENERATION_FAILURE'
        elif isinstance(exc, ModelUsageUnknown):
            status = 'MODEL_USAGE_UNKNOWN'
        elif isinstance(exc, IncompleteResultError):
            status = 'INCOMPLETE_RESULT'
        elif isinstance(exc, PermissionError) and 'budget' in str(exc).lower():
            status = 'BUDGET_EXCEEDED'
        else:
            status = classify_execution_failure(exc, stage='execute')
        log.add('pipeline_error', error_type=type(exc).__name__, status=status,
                error='Pilot failed; details withheld')
        log.add('prediction', sql='', status=status, split='validation',
                configured_model_id=model_id, model_snapshot=model.model_id)
        log.save(path)
        raise


def load_real_cot_checkpoint(question: Question, *, pilot_manifest: dict,
                             schema_index: SchemaIndex, output_root: Path) -> dict:
    """Read saved metadata only; an interrupted marker never triggers another API call."""
    case = next((row for row in pilot_manifest['cases'] if row['case_id'] == question.query_id), None)
    if case is None or case['question_sha256'] != hashlib.sha256(question.text.encode()).hexdigest():
        raise PermissionError('Question is outside pinned pilot')
    path = Path(output_root) / (question.query_id.replace('/', '__') + '.json')
    marker = path.with_suffix('.started')
    if not marker.exists() or not path.exists():
        raise FileNotFoundError('Interrupted or absent pilot; inspect marker and ledgers manually')
    saved = json.loads(path.read_text(encoding='utf-8'))
    context = [e for e in saved['events'] if e.get('stage') == 'run_context']
    prediction = [e for e in saved['events'] if e.get('stage') == 'prediction']
    if len(context) != 1 or len(prediction) != 1 or saved['summary']['query_id'] != question.query_id:
        raise ValueError('Invalid saved pilot log')
    expected = context[0].copy()
    expected.pop('stage')
    fingerprint = expected.pop('fingerprint', None)
    if (expected.get('pilot_manifest_sha256') != pilot_manifest['sha256'] or
        expected.get('schema_sha256') != schema_index.index['schema_sha256'] or
        expected.get('schema_index_sha256') != schema_index.index['sha256'] or
        expected.get('case_id') != question.query_id or
        fingerprint != hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest() or
        json.loads(marker.read_text(encoding='utf-8')).get('fingerprint') != fingerprint):
        raise ValueError('Saved pilot fingerprint differs from pinned inputs')
    artifacts = [e for e in saved['events'] if e.get('stage') == 'result_artifact']
    return {'status': prediction[0]['status'], 'sql': prediction[0]['sql'],
            'log_path': str(path), 'artifact': artifacts[-1] if artifacts else None,
            'usage': saved['summary']}
