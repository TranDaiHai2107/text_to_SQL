"""Fail-closed orchestration around the locked CLINSQL scoring implementation."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time

from .official_scorer_source import SCORER_RELATIVE_PATH, load_verified_native_scorer
from .rubric_judge import ADAPTED, JudgeIncomplete, digest, parse_grade


class LeafLedger:
    def __init__(self, path, *, max_calls, retry_limit=2, grade_parser=parse_grade,
                 retry_invalid_response=False, retain_invalid_response=False):
        if max_calls < 1 or not 1 <= retry_limit <= 3:
            raise ValueError('Invalid judge call budget or retry limit')
        self.path = path
        self.max_calls = max_calls
        self.retry_limit = retry_limit
        self.grade_parser = grade_parser
        self.retain_invalid_response = retain_invalid_response
        self.retryable = {'RATE_LIMITED'}
        if retry_invalid_response:
            self.retryable.add('INVALID_JUDGE_RESPONSE')
        with self.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS attempts (
                       leaf TEXT, attempt INTEGER, status TEXT, metadata TEXT,
                       score INTEGER, explanation TEXT, PRIMARY KEY (leaf, attempt))''')

    @contextmanager
    def transaction(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('BEGIN IMMEDIATE')
            yield db

    def grade(self, key, context, prompt, judge, *, authorize):
        for _ in range(self.retry_limit):
            authorize()
            with self.transaction() as db:
                previous = db.execute('''SELECT attempt, status, score, explanation, metadata FROM attempts
                                         WHERE leaf=? ORDER BY attempt DESC LIMIT 1''', (key,)).fetchone()
                attempt = 1
                if previous:
                    attempt, status, score, explanation, old_metadata = previous
                    if status == 'COMPLETE':
                        return score, explanation
                    if status == 'INVALID_JUDGE_RESPONSE' and self.retain_invalid_response:
                        metadata = json.loads(old_metadata)
                        if recorded := metadata.get('invalid_response'):
                            try:
                                score, explanation = self.grade_parser(recorded)
                            except JudgeIncomplete:
                                pass
                            else:
                                metadata['parsed_on_resume'] = True
                                db.execute('UPDATE attempts SET status=?, metadata=?, score=?, explanation=? '
                                           'WHERE leaf=? AND attempt=?',
                                           ('COMPLETE', json.dumps(metadata), score, explanation, key, attempt))
                                return score, explanation
                    if status not in self.retryable or attempt >= self.retry_limit:
                        raise JudgeIncomplete('UNRESOLVED_OR_TERMINAL_LEAF')
                    attempt += 1
                if db.execute('SELECT count(*) FROM attempts').fetchone()[0] >= self.max_calls:
                    raise JudgeIncomplete('JUDGE_CALL_BUDGET_EXHAUSTED')
                db.execute('INSERT INTO attempts VALUES (?, ?, ?, ?, NULL, NULL)',
                           (key, attempt, 'IN_FLIGHT', json.dumps(context)))
            started = time.monotonic()
            metadata = {}
            grade = (None, None)
            raw = None
            try:
                raw, metadata = judge(prompt)
                grade = self.grade_parser(raw)
                status = 'COMPLETE'
            except JudgeIncomplete as exc:
                status = str(exc)
                if status == 'INVALID_JUDGE_RESPONSE' and self.retain_invalid_response and raw is not None:
                    metadata['invalid_response'] = raw
            except Exception as exc:
                status = 'RATE_LIMITED' if getattr(exc, 'status_code', None) == 429 else 'JUDGE_API_FAILURE'
            context = {**context, 'attempt_latency_seconds': time.monotonic() - started, **metadata}
            with self.transaction() as db:
                db.execute('UPDATE attempts SET status=?, metadata=?, score=?, explanation=? WHERE leaf=? AND attempt=?',
                           (status, json.dumps(context), *grade, key, attempt))
            if status == 'COMPLETE':
                return grade
            if status not in self.retryable or attempt >= self.retry_limit:
                raise JudgeIncomplete(status)
            time.sleep(2 ** attempt)
        raise JudgeIncomplete('JUDGE_RETRY_LIMIT')


def _sample_digest(sample, *, require_result=True):
    paths = []
    patterns = ('query_*.txt', 'sql_*.sql', 'result_*.csv', 'sql_rubric_tree.json', 'results_rubric_tree.json')
    if not require_result:
        # SQL-only sample: the prediction has SQL but no executed result. The
        # official scorer still grades its SQL tree (results score is 0).
        if list(sample.glob('result_*.csv')):
            raise JudgeIncomplete('UNEXPECTED_RESULT_FILE')
        patterns = tuple(p for p in patterns if p != 'result_*.csv')
    for pattern in patterns:
        matches = list(sample.glob(pattern))
        if len(matches) != 1 or not matches[0].is_file() or not matches[0].stat().st_size:
            raise JudgeIncomplete('MISSING_OR_AMBIGUOUS_SAMPLE_FILE')
        paths.extend(matches)
    if any((sample / name).exists() for name in ('gold_sql.sql', 'gold_results.csv')):
        raise JudgeIncomplete('UNEXPECTED_REFERENCE_FILE')
    return digest({path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})


def _validate_rubrics(sample):
    def visit(node, ids):
        node_id = node['id']
        if not isinstance(node_id, str) or node_id in ids or not isinstance(node['requirements'], str):
            raise ValueError('Invalid or duplicate rubric node')
        ids.add(node_id)
        for child in node.get('sub_tasks', []):
            visit(child, ids)

    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        visit(json.loads((sample / name).read_text(encoding='utf-8')), set())


def create_scorer(source, lock, judge, ledger, *, scope, authorize):
    native = load_verified_native_scorer(source, lock)
    module = sys.modules[native.__module__]
    source_sha = hashlib.sha256((source / SCORER_RELATIVE_PATH).read_bytes()).hexdigest()

    class CheckpointedScorer(native):
        def __init__(self):
            pass  # The explicit transport replaces native Azure construction.

        def _prepare_sample(self, sample_dir, require_result=True):
            self.sample_hash = _sample_digest(sample_dir, require_result=require_result)
            self.case = '/'.join(sample_dir.parts[-4:])
            _validate_rubrics(sample_dir)

        def score_sample(self, sample_dir):
            try:
                self._prepare_sample(sample_dir)
                return super().score_sample(sample_dir)
            except (OSError, ValueError, KeyError, TypeError):
                raise JudgeIncomplete('INVALID_SAMPLE_OR_RUBRIC') from None

        def score_sql_without_results(self, sample_dir, *, require_result=True):
            """Use the native SQL tree with a row-free judge payload."""
            try:
                self._prepare_sample(sample_dir, require_result)
                files = {
                    'query': next(sample_dir.glob('query_*.txt')).read_text(encoding='utf-8').strip(),
                    'test_sql': next(sample_dir.glob('sql_*.sql')).read_text(encoding='utf-8').strip(),
                }
                if not all(files.values()):
                    raise JudgeIncomplete('INCOMPLETE_SAMPLE')
                rubric = module.ClinicalRubricNode(json.loads(
                    (sample_dir / 'sql_rubric_tree.json').read_text(encoding='utf-8')))
                evaluations = self._evaluate_tree(rubric, files, evaluation_type='sql')
                return self._calculate_score(rubric, evaluations)
            except (OSError, ValueError, KeyError, TypeError):
                raise JudgeIncomplete('INVALID_SAMPLE_OR_RUBRIC') from None

        def _load_sample_files(self, sample_dir):
            files = super()._load_sample_files(sample_dir)
            if not files.get('query') or not files.get('test_sql') or 'test_results' not in files:
                raise JudgeIncomplete('INCOMPLETE_SAMPLE')
            return files

        def _evaluate_leaf(self, node, sample_files, evaluation_type):
            prompt = self._build_prompt(node, sample_files, evaluation_type)
            context = {'scope': scope, 'case': self.case, 'target': evaluation_type,
                       'rubric_leaf_id': node.id, 'source_sha256': source_sha,
                       'judge_config_sha256': judge.config.sha256, 'sample_sha256': self.sample_hash,
                       'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                       'requested_model': judge.config.model, 'parameters': judge.config.parameters()}
            score, explanation = ledger.grade(digest(context), context, prompt, judge, authorize=authorize)
            return module.EvaluationResult(node.id, node.requirements, float(score), explanation,
                                           node.critical, node.weight)

    return CheckpointedScorer(), module


def evaluate_split(scorer, native_module, cases, *, method, split, judge_config):
    """Cases is the explicit expected cohort, including missing predictions."""
    if split not in {'validation', 'test'} or not cases:
        raise ValueError('Expected a nonempty CLINSQL cohort')
    records = []
    outcomes = {}
    labels = ('CLINSQL_SQL_SCORE', 'CLINSQL_EXECUTION_SCORE')
    if judge_config.mode == ADAPTED:
        labels = tuple('ADAPTED_' + label for label in labels)
    for case_id, stage in cases.items():
        category, difficulty, _ = case_id.split('/')
        try:
            with stage() as path:
                value = scorer.score_sample(Path(path))
        except (JudgeIncomplete, ValueError, KeyError, PermissionError, OSError) as exc:
            reason = str(exc) if isinstance(exc, JudgeIncomplete) else 'STAGING_UNAVAILABLE'
            outcomes[case_id] = {'status': 'INCOMPLETE', 'reason': reason}
            continue
        records.append(native_module.EvaluationRecord(value, category, difficulty, split))
        outcomes[case_id] = {'status': 'GRADED', labels[0]: value.sql_score, labels[1]: value.results_score}
    complete = len(records) == len(cases)
    return {'status': 'COMPLETE' if complete else 'INCOMPLETE', 'mode': judge_config.mode,
            'score_labels': labels, 'judge_config_sha256': judge_config.sha256,
            'split': split, 'method': method, 'cases': outcomes,
            'expected': len(cases), 'graded': len(records),
            'summary': native_module._build_split_summary(method, split, records) if complete else None,
            'domains': native_module._build_scenario_breakdown(records) if complete else None}


def check_approval(approval, *, config, manifest_hash, source_hash):
    expires = datetime.fromisoformat(approval['expires_at_utc'])
    if (expires.tzinfo is None or datetime.now(timezone.utc) >= expires
            or approval.get('send_complete_result_rows') is not True
            or approval.get('manifest_sha256') != manifest_hash
            or approval.get('judge_config_sha256') != config.sha256
            or approval.get('source_sha256') != source_hash
            or type(approval.get('max_leaf_requests')) is not int
            or approval['max_leaf_requests'] < 1
            or not approval.get('approved_by') or not approval.get('policy_reference')):
        raise JudgeIncomplete('JUDGE_APPROVAL_MISSING_OR_EXPIRED')
