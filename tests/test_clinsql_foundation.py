"""Offline gates for benchmark leakage and bounded database access."""
import json

import pytest

from ehrqa.clinsql.dataset import load_questions, validation_partition
from ehrqa.clinsql.bigquery_adapter import BigQueryAdapter, Limits
from ehrqa.clinsql.cot import generation_prompt, refinement_prompt, extract_sql
from ehrqa.clinsql.proposed import build_pipeline
from ehrqa.clinsql.cot_runner import ClinSQLCoT
from ehrqa.clinsql.records import RunRecorder


def test_question_loader_exposes_only_input_fields_and_locks_test(tmp_path):
    path = tmp_path / 'questions.json'
    row = {'split':'validation','domain':'Labs','difficulty':'easy_level_queries',
           'problem_id':'001','query':'How many admissions?', 'sql':'SECRET GOLD SQL',
           'results_rubric':'SECRET RUBRIC'}
    path.write_text(json.dumps([row]), encoding='utf-8')
    rows, digest = load_questions(path)
    assert len(digest) == 64 and rows[0].text == row['query']
    assert 'SECRET' not in repr(rows)
    assert validation_partition(rows, seed='fixed') == validation_partition(rows, seed='fixed')
    row['split'] = 'test'
    path.write_text(json.dumps([row]), encoding='utf-8')
    with pytest.raises(PermissionError): load_questions(path)


class FakeClient:
    def __init__(self): self.executions = 0
    def dry_run(self, sql, *, timeout_seconds): return 25
    def execute(self, sql, **kwargs):
        self.executions += 1
        return {'columns':['n'], 'rows':[(1,)]}


def test_bigquery_guard_blocks_mutation_external_table_and_data_access():
    client = FakeClient()
    adapter = BigQueryAdapter(client, [], Limits(100), allowed_datasets=('physionet-data.mimiciv_3_1_hosp',))
    good = 'SELECT subject_id FROM `physionet-data.mimiciv_3_1_hosp.patients` LIMIT 1'
    assert adapter.dry_run(good).estimated_bytes == 25
    with pytest.raises(PermissionError): adapter.probe(good)
    assert client.executions == 0
    with pytest.raises(ValueError): adapter.dry_run('DELETE FROM `physionet-data.mimiciv_3_1_hosp.patients` WHERE TRUE')
    with pytest.raises(ValueError): adapter.dry_run('SELECT * FROM `other.secret.patients`')


def test_cot_prompt_shape_and_proposed_profile_are_english():
    prompt = generation_prompt('How many admissions?', 'CREATE TABLE admissions (hadm_id INT64)')
    assert 'Reasoning:' in prompt and 'BigQuery' in prompt
    assert 'BigQuery error message:' in refinement_prompt('q','schema','SELECT 1','redacted syntax error')
    assert extract_sql('Reasoning: ...\nSQL:\n```sql\nSELECT 1\n```') == 'SELECT 1'
    class Adapter:
        def schema_metadata(self): return [{'table':'admissions','ddl':'CREATE TABLE admissions (hadm_id INT64)'}]
    pipeline = build_pipeline(Adapter(), object())
    assert pipeline.config.profile == 'clinsql'


def test_cot_refines_execution_error_twice_without_gold(tmp_path):
    class Model:
        def __init__(self): self.prompts = []
        def complete(self, stage, prompt):
            self.prompts.append(prompt)
            return {'content': f'```sql\nSELECT {len(self.prompts)} FROM `physionet-data.mimiciv_3_1_hosp.patients`\n```',
                    'usage': {'prompt_tokens': 10, 'completion_tokens': 5}}
    class DB:
        def dry_run(self, sql): pass
        def execute(self, sql):
            if 'SELECT 3' not in sql: raise ValueError('redacted syntax error')
    model = Model()
    result = ClinSQLCoT(model, DB(), 'CREATE TABLE patients (subject_id INT64)').run('q1', 'question')
    assert result.status == 'executed' and len(result.attempts) == 3
    assert 'syntax error' in model.prompts[1]
    recorder = RunRecorder(tmp_path / 'records', {'model':'mock'})
    record_path = recorder.save(result)
    assert json.loads(record_path.read_text(encoding='utf-8'))['inference_usage']['calls'] == 3
    assert recorder.save(result) == record_path
    with pytest.raises(ValueError): RunRecorder(tmp_path / 'records', {'model':'other'}).save(result)
