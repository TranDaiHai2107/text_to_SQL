"""Official scorer file layout and injectable judge, separate from inference."""
from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
import re
import shutil
from datetime import datetime, timezone

from .dataset import Question
from ehrqa.text2sql.interfaces import Execution


def prepare_official_sample(root: Path, benchmark_root: Path, question: Question,
                            sql: str, result: Execution | None, *, allow_test=False) -> Path:
    """Stage an already saved prediction for official scoring, never inference."""
    if result is not None and not result.complete:
        raise ValueError('Truncated execution result cannot be staged for official scoring')
    if question.split == 'test' and not allow_test:
        raise PermissionError('Test evaluation requires a frozen protocol')
    if question.split not in {'validation', 'test'}:
        raise ValueError('Unknown CLINSQL split')
    if len(question.query_id.split('/')) != 3:
        raise ValueError('Invalid question ID')
    domain, difficulty, problem_id = question.query_id.split('/')
    if any(not re.fullmatch(r'[A-Za-z0-9_]+', part)
           for part in (domain, difficulty, problem_id)):
        raise ValueError('Unsafe question ID')
    source = Path(benchmark_root) / 'data' / 'splits' / question.split / domain / difficulty / problem_id
    target = Path(root) / question.split / domain / difficulty / problem_id
    if not source.is_dir():
        raise FileNotFoundError(source)
    target.mkdir(parents=True, exist_ok=True)
    (target / f'query_{problem_id}.txt').write_text(question.text, encoding='utf-8')
    (target / f'sql_{problem_id}.sql').write_text(sql, encoding='utf-8')
    csv_path = target / f'result_{problem_id}.csv'
    # Match the native CLINSQL pandas CSV path and its empty-result placeholder.
    import pandas as pd
    if result is None or not result.rows or not result.columns:
        pd.DataFrame({'result': [None]}).to_csv(csv_path, index=False)
    else:
        pd.DataFrame(result.rows, columns=result.columns).to_csv(csv_path, index=False)
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        shutil.copyfile(source / name, target / name)
    return target


def prepare_saved_run_sample(log_path: Path, root: Path, benchmark_root: Path,
                             question: Question, *, result_store=None,
                             artifact_id: str | None = None,
                             artifact_sha256: str | None = None) -> Path:
    """Render a persisted mock prediction for re-scoring without model calls."""
    saved = json.loads(Path(log_path).read_text(encoding='utf-8'))
    if saved['summary']['query_id'] != question.query_id:
        raise ValueError('Run record belongs to a different question')
    predictions = [e for e in saved['events'] if e['stage'] == 'prediction']
    if len(predictions) != 1 or predictions[0]['split'] != question.split:
        raise ValueError('Run record has no unique matching prediction')
    sql = predictions[0]['sql'] or ''
    executions = [e for e in saved['events'] if e['stage'] == 'execute'
                  and e.get('sql') == sql and e.get('error') is None]
    result = None
    if result_store is not None:
        if not artifact_id or not artifact_sha256:
            raise ValueError('Restricted result artifact ID and SHA-256 required')
        references = [event for event in saved['events'] if event['stage'] == 'result_artifact'
                      and event.get('artifact_id') == artifact_id and event.get('sha256') == artifact_sha256]
        if len(references) != 1:
            raise ValueError('Missing unique result artifact reference')
        expires = datetime.fromisoformat(references[0]['artifact_expires_at_utc'])
        if expires.tzinfo is None or datetime.now(timezone.utc) >= expires:
            raise PermissionError('Result artifact retention has expired')
        result = result_store.load(artifact_id, expected_sha256=artifact_sha256)
        matching = [event for event in executions if result.job_id and
                    event.get('job_id') == result.job_id]
        if len(matching) != 1:
            raise ValueError('Restricted artifact requires one matching successful SQL job')
        event = matching[0]
        if (not result.job_id or
            len(result.rows) != event.get('row_count') or not event.get('complete')
            or references[0].get('job_id') != result.job_id):
            raise ValueError('Restricted artifact does not match saved execution metadata')
    elif executions:
        event = executions[-1]
        if event.get('rows') is None:
            raise ValueError('Saved execution rows unavailable for official result scoring')
        result = Execution(tuple(event['columns']),
                           tuple(tuple(row) for row in event['rows']),
                           bool(event['complete']), event.get('bytes_billed'))
    return prepare_official_sample(root, benchmark_root, question, sql, result)


class OfficialClinSQLEvaluator:
    def __init__(self, source_root: Path, *, source_commit: str,
                 judge_config_hash: str, scorer_factory=None, allow_test=False):
        self.source_root = Path(source_root)
        self.source_commit = source_commit
        self.judge_config_hash = judge_config_hash
        self.scorer_factory = scorer_factory
        self.allow_test = allow_test

    def evaluate_saved_predictions(self, prediction_dir: str, *, split: str) -> dict:
        if split not in {'validation', 'test'}:
            raise ValueError('Unknown split')
        if split == 'test' and not self.allow_test:
            raise PermissionError('Test evaluation requires a frozen protocol')
        if not self.source_commit or not self.judge_config_hash:
            raise ValueError('Official scorer and judge configuration must be pinned')
        if not (self.source_root / 'evaluation' / 'clinical_rubric_scorer.py').is_file():
            raise FileNotFoundError('Official CLINSQL scorer is not installed')
        if self.scorer_factory is None:
            raise RuntimeError('Explicit official scorer factory required; this call may use a paid judge')
        split_dir = Path(prediction_dir) / split
        if not split_dir.is_dir():
            raise FileNotFoundError(split_dir)
        samples = sorted(split_dir.glob('*/*/*/sql_rubric_tree.json'))
        if not samples:
            raise ValueError('No prepared CLINSQL samples')
        scorer = self.scorer_factory()
        scores = []
        for rubric in samples:
            sample = rubric.parent
            value = scorer.score_sample(sample)
            scores.append({'query_id': '/'.join(sample.parts[-3:]),
                           'sql_score': float(value.sql_score),
                           'execution_score': float(value.results_score)})
        return {'split': split, 'samples': scores,
                'sql_score': sum(x['sql_score'] for x in scores) / len(scores),
                'execution_score': sum(x['execution_score'] for x in scores) / len(scores),
                'judge_config_hash': self.judge_config_hash,
                'source_commit': self.source_commit}
