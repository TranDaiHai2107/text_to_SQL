"""One-question validation runner with injected transports and persistent logs."""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import os

from ehrqa.text2sql.logging import MeteredDatabase, MeteredModel, Pricing, RunLog
from .baselines.mac_sql import MACSQL
from .baselines.sde_sql import SDESQL
from .config import ExperimentConfig
from .cot_runner import ClinSQLCoT
from .dataset import Question
from .offline import MockBigQuery, MockLLM
from .proposed import build_pipeline


METHODS = frozenset({'proposed', 'clinsql_cot', 'sde_sql'})
HISTORICAL_OFFLINE_METHODS = frozenset({'mac_sql'})


def run_validation_one(method: str, question: Question, *, model, database,
                       output_root: Path, config: ExperimentConfig,
                       pricing: Pricing | None = None, few_shot_index=None,
                       icd_catalog=None, value_evidence=None, sde_judge=None,
                       schema_index=None, historical=False) -> dict:
    if method not in METHODS and not (historical and method in HISTORICAL_OFFLINE_METHODS):
        raise ValueError(f'Unknown method: {method}')
    if not isinstance(model, MockLLM) or not isinstance(database, MockBigQuery):
        raise TypeError('Offline runner requires MockLLM and MockBigQuery; no paid services')
    if question.split != 'validation':
        raise PermissionError('Offline runner only accepts validation questions')
    path = Path(output_root) / method / (question.query_id.replace('/', '__') + '.json')
    if path.exists():
        raise FileExistsError('Prediction already saved; do not call the model again')
    marker = path.with_suffix('.started')
    marker.parent.mkdir(parents=True, exist_ok=True)
    fingerprint = hashlib.sha256(json.dumps({
        'method': method, 'query_id': question.query_id, 'question': question.text,
        'model_id': config.model_id, 'model_snapshot': config.model_snapshot,
        'schema_sha256': schema_index.index['schema_sha256'] if schema_index else None,
    }, sort_keys=True).encode('utf-8')).hexdigest()
    descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        json.dump({'fingerprint': fingerprint, 'status': 'started'}, stream)
    log = RunLog(question.query_id, method, pricing)
    tracked_model = MeteredModel(model, log)
    tracked_db = MeteredDatabase(database, log, capture_rows=True)  # synthetic mock rows only
    schema_text = '\n'.join(row['ddl'] for row in tracked_db.schema_metadata())
    try:
        if method == 'proposed':
            output = build_pipeline(tracked_db, tracked_model, few_shot_index=few_shot_index,
                                    icd_catalog=icd_catalog, schema_index=schema_index).run(
                                        question.text, query_id=question.query_id)
            status, sql = output['status'], output['sql']
        elif method == 'clinsql_cot':
            output = ClinSQLCoT(tracked_model, tracked_db, schema_text).run(question.query_id, question.text)
            status, sql = output.status, output.sql
        elif method == 'mac_sql':
            output = MACSQL(tracked_model, tracked_db, value_evidence=value_evidence).run(question.text)
            status, sql = output['status'], output['sql']
        else:
            output = SDESQL(tracked_model, tracked_db, judge=sde_judge).run(question.text,
                                                                             schema_text=schema_text)
            status, sql = output['status'], output['sql']
    except Exception as exc:
        log.add('pipeline_error', error_type=type(exc).__name__,
                error='Pipeline failed; details withheld')
        log.add('prediction', sql='', status='error', split=question.split,
                configured_model_id=config.model_id, model_snapshot=config.model_snapshot)
        log.save(path)
        raise
    log.add('prediction', sql=sql, status=status, split=question.split,
            configured_model_id=config.model_id, model_snapshot=config.model_snapshot)
    log.save(path)
    return {'status': status, 'sql': sql, 'log_path': str(path), 'usage': log.summary()}


def load_validation_checkpoint(method: str, question: Question, *, output_root: Path,
                               config: ExperimentConfig, schema_index=None) -> dict:
    """Read a completed prediction without model calls; fail closed on interrupted runs."""
    if method not in METHODS | HISTORICAL_OFFLINE_METHODS or question.split != 'validation':
        raise ValueError('Only known validation methods can be resumed')
    path = Path(output_root) / method / (question.query_id.replace('/', '__') + '.json')
    marker = path.with_suffix('.started')
    if not marker.exists() or not path.exists():
        raise FileNotFoundError('Incomplete run; inspect marker before any retry')
    expected = hashlib.sha256(json.dumps({
        'method': method, 'query_id': question.query_id, 'question': question.text,
        'model_id': config.model_id, 'model_snapshot': config.model_snapshot,
        'schema_sha256': schema_index.index['schema_sha256'] if schema_index else None,
    }, sort_keys=True).encode('utf-8')).hexdigest()
    if json.loads(marker.read_text(encoding='utf-8')).get('fingerprint') != expected:
        raise ValueError('Checkpoint inputs differ from pinned run configuration')
    saved = json.loads(path.read_text(encoding='utf-8'))
    events = [row for row in saved['events'] if row.get('stage') == 'prediction']
    if len(events) != 1 or saved['summary']['query_id'] != question.query_id:
        raise ValueError('Invalid saved prediction')
    return {'status': events[0]['status'], 'sql': events[0]['sql'],
            'log_path': str(path), 'usage': saved['summary']}
