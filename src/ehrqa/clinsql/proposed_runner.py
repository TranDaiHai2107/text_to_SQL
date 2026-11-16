"""Approval-bound Ours validation pilot entry point with injected SDK clients."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from ehrqa.agentic.trace import digest
from .benchmark_approval import BenchmarkExecutionApproval
from .benchmark_backend import make_benchmark_database
from .clinical_catalog import ClinicalCatalog
from .execution_budget import PersistentSQLBudgetLedger
from .execution_modes import BenchmarkExecutionConfig
from .interfaces import Execution
from .openai_provider import OpenAIModelProvider
from .benchmark_model import BENCHMARK_LLM
from .evidence_router import guard_ours_payload
from .linking_format import LINK_FORMAT
from .pilot_api_budget import PersistentAPIBudgetLedger
from .proposed import PROPOSED_VERSION, ProposedFlags, build_pipeline
from .result_artifacts import ResultArtifactStore
from .retrieval_manifest import FROZEN_CORPUS_SHA256, load_frozen_fewshot_index
from .schema_index import verify_schema_index


MODEL = BENCHMARK_LLM


@dataclass(frozen=True, kw_only=True)
class ProposedPilotApproval(BenchmarkExecutionApproval):
    expected_phase = 'proposed_validation_pilot'
    phase: str = 'proposed_validation_pilot'
    index_sha256: str
    clinical_sha256: str
    run_config_sha256: str

    def __post_init__(self):
        super().__post_init__()
        for value in (self.index_sha256, self.clinical_sha256, self.run_config_sha256):
            if len(value) != 64 or any(char not in '0123456789abcdef' for char in value):
                raise ValueError('Ours approval requires SHA-256 pins')


class ProposedModelProvider(OpenAIModelProvider):
    @staticmethod
    def serialize_prompt(prompt):
        return [{'role': message['role'], 'content': message['content']}
                for message in json.loads(prompt)]

    def complete(self, stage, messages, tokens):
        guard_ours_payload(stage, messages)
        return super().complete(stage, json.dumps(messages, ensure_ascii=False),
                                text_format=LINK_FORMAT if stage == 'link' else None)


def run_proposed_pilot_case(question, *, approval, pilot_manifest, schema_manifest,
                            schema_index, master_manifest, corpus_path, clinical_path,
                            bigquery_config, api_budget, sql_budget, output_root,
                            result_store: ResultArtifactStore, flags=ProposedFlags(),
                            openai_client=None, bigquery_client=None):
    if type(approval) is not ProposedPilotApproval or question.split != 'validation':
        raise PermissionError('Ours requires its own scoped validation approval')
    approval.verify_active()
    approval.verify_pilot(pilot_manifest)
    pilot_payload = {key: value for key, value in pilot_manifest.items() if key != 'sha256'}
    pilot_digest = hashlib.sha256(json.dumps(
        pilot_payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if pilot_digest != approval.pilot_manifest_sha256 or master_manifest['pilot_manifest_sha256'] != pilot_digest:
        raise PermissionError('Ours pilot manifest is not pinned to the experiment')
    case = next((row for row in pilot_manifest['cases'] if row['case_id'] == question.query_id), None)
    if case is None or case['question_sha256'] != hashlib.sha256(question.text.encode()).hexdigest():
        raise PermissionError('Question differs from approved pilot inputs')
    if approval.model_id != MODEL:
        raise PermissionError('Ours pilot model differs from pinned configuration')
    verify_schema_index(schema_index.index, schema_manifest)
    if (schema_index.index['sha256'] != approval.index_sha256 or
        schema_manifest['sha256'] != approval.manifest_sha256 or
        master_manifest['schema_sha256'] != approval.manifest_sha256 or
        master_manifest['schema_index_sha256'] != approval.index_sha256):
        raise PermissionError('Ours schema and retrieval scope differ from approval')
    config = {'version': PROPOSED_VERSION, 'model': MODEL, 'flags': asdict(flags),
              'fewshot_sha256': FROZEN_CORPUS_SHA256, 'reasoning_effort': 'medium',
              'max_output_tokens': 8192, 'model_timeout_seconds': 90}
    if (digest(config) != approval.run_config_sha256 or
        digest(asdict(api_budget)) != approval.api_budget_sha256 or
        digest(asdict(sql_budget)) != approval.sql_budget_sha256):
        raise PermissionError('Ours runtime or budget differs from approval')
    clinical = ClinicalCatalog.load(clinical_path, expected_sha256=approval.clinical_sha256,
                                    schema_sha256=approval.manifest_sha256)
    few_shot = load_frozen_fewshot_index(corpus_path, master_manifest)
    if question.query_id in master_manifest['development_case_ids']:
        partition = 'development'
    elif question.query_id in master_manifest['internal_check_case_ids']:
        partition = 'internal_check'
    else:
        raise PermissionError('Question is outside the pinned validation partitions')
    if not result_store.verify_private_acl(result_store.root):
        raise PermissionError('Private result storage is required')
    output_root = Path(output_root) / approval.approval_id
    output_root.mkdir(parents=True, exist_ok=True)
    if not result_store.verify_private_acl(output_root):
        raise PermissionError('Private Ours trace and checkpoint storage is required')
    api_ledger = PersistentAPIBudgetLedger(output_root / 'api.sqlite', api_budget)
    sql_ledger = PersistentSQLBudgetLedger(output_root / 'sql.sqlite', sql_budget)
    execution = BenchmarkExecutionConfig(approval.max_bytes_billed_per_sql,
                                         approval.timeout_seconds, approval.max_rows,
                                         approval.max_result_bytes)
    database = make_benchmark_database(bigquery_config, schema_manifest, schema_index,
                                      execution, case_id=question.query_id, client=bigquery_client,
                                      ledger=sql_ledger, approval=approval)
    model = ProposedModelProvider(api_ledger, model_id=MODEL, max_output_tokens=8192,
                                  timeout_seconds=90, reasoning_effort='medium', client=openai_client)
    case_key = digest(question.query_id)
    pipeline = build_pipeline(database, model, schema_index=schema_index, few_shot_index=few_shot,
                              icd_catalog=clinical, flags=flags, log_dir=output_root / 'traces')
    with (output_root / f'{case_key}.started').open('x', encoding='utf-8') as stream:
        json.dump({'case_id': question.query_id, 'config_sha256': approval.run_config_sha256}, stream)
    output = pipeline.run(question.text, query_id=question.query_id)
    saved = {'case_id': question.query_id, 'status': output['status'], 'sql': output['sql'],
             'reason': output['reason'], 'model_calls': output['model_calls'],
             'schema_sha256': approval.manifest_sha256, 'index_sha256': approval.index_sha256,
             'clinical_sha256': approval.clinical_sha256,
             'trace_path': output['trace_path'], 'config': config,
             'evaluation_partition': partition}
    if output['selected'] is not None:
        result = output['selected']['result']
        saved['artifact'] = result_store.save('ours_' + digest([approval.approval_id, case_key]),
            Execution(tuple(result.columns), tuple(result.rows), result.complete,
                      column_types=result.column_types, job_id=result.job_id))
        saved['artifact_expires_at_utc'] = (datetime.now(timezone.utc) +
            timedelta(days=approval.artifact_retention_days)).isoformat()
        saved['events'] = [{'stage': 'result_artifact', **saved['artifact'],
                            'artifact_expires_at_utc': saved['artifact_expires_at_utc']}]
    with (output_root / f'{case_key}.json').open('x', encoding='utf-8') as stream:
        json.dump(saved, stream, ensure_ascii=False, indent=2)
    return saved
