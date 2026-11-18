import hashlib
import json
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from ehrqa.clinsql.clinical_catalog import ClinicalCatalog
from ehrqa.clinsql.execution_errors import BudgetExceeded
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM
from ehrqa.clinsql.proposed import ProposedFlags, build_pipeline, ungrounded_clinical_literals, ungrounded_join_keys
from ehrqa.clinsql.proposed_runner import ProposedModelProvider, ProposedPilotApproval, run_proposed_pilot_case
from ehrqa.clinsql.benchmark_approval import BenchmarkExecutionApproval
from ehrqa.clinsql.execution_control import EXPECTED_DATASETS, EXPECTED_PROJECT, READER_PRINCIPAL
from ehrqa.clinsql.retrieval import FewShotIndex
from ehrqa.clinsql.schema_index import SchemaIndex


def test_pinned_clinical_catalog_maps_icd_versions_and_measurements(tmp_path):
    payload = {'mimic_version': '3.1', 'schema_sha256': 'schema', 'source': 'synthetic',
               'records': [
                   {'table': 'd_icd_diagnoses', 'icd_code': '0123', 'icd_version': 9,
                    'long_title': 'Sample diagnosis', 'aliases': ['example disorder']},
                   {'table': 'd_icd_diagnoses', 'icd_code': 'A123', 'icd_version': 10,
                    'long_title': 'Sample diagnosis', 'aliases': ['example disorder']},
                   {'table': 'd_items', 'itemid': 789, 'label': 'Sample measurement',
                    'abbreviation': 'SM', 'linksto': 'chartevents'},
               ]}
    data = json.dumps(payload).encode()
    path = tmp_path / 'catalog.json'
    path.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    catalog = ClinicalCatalog.load(path, expected_sha256=digest, schema_sha256='schema')
    records = catalog.search('example disorder and SM', {'tables': ['d_items']})
    assert {row['code'] for row in records} == {'0123', 'A123', 789}
    assert {row['icd_version'] for row in records if 'icd_version' in row} == {9, 10}
    assert ungrounded_clinical_literals('SELECT itemid FROM x WHERE itemid=790', 'SM', records)
    assert not ungrounded_clinical_literals('SELECT itemid FROM x WHERE itemid=789', 'SM', records)
    assert ungrounded_clinical_literals('SELECT itemid FROM labevents WHERE itemid=789', 'SM', records)
    with pytest.raises(ValueError, match='SHA-256'):
        ClinicalCatalog.load(path, expected_sha256='invalid', schema_sha256='schema')


def test_fewshot_blocks_self_near_duplicate_and_shared_answer():
    rows = [('same', 'Some earlier admission question', 'SELECT 1'),
            ('near', 'Count admissions within 30 days of the index discharge', 'SELECT 2'),
            ('answer', 'Count admissions for the synthetic group', 'SELECT 2'),
            ('ok', 'Compare mean duration across admissions', 'SELECT 3')]
    index = FewShotIndex([dict(query_id=i, question=q, sql=s, split='validation',
                               partition='development') for i, q, s in rows])
    out = index.retrieve('Count admissions within 60 days of the index discharge', query_id='same')
    assert [row['source_id'] for row in out['items']] == ['ok']
    for split, partition in [('validation', 'internal_check'), ('test', 'development')]:
        with pytest.raises(ValueError, match='development validation'):
            FewShotIndex([dict(query_id='x', question='x', sql='SELECT 1', split=split, partition=partition)])


def test_authoritative_schema_ranks_columns_and_grounds_joins():
    root = Path(__file__).resolve().parents[1] / 'data/schema'
    manifest = json.loads(next((root / 'manifests').glob('mimiciv_3_1_*.json')).read_text(encoding='utf-8'))
    index = SchemaIndex.load(root / 'indexes/schema_lexical_v1_46a816c289178f5b.json', manifest)
    records = index.schema_records()
    pipeline = build_pipeline(MockBigQuery(records), MockLLM({}), schema_index=index)
    context = pipeline.rag.schema('admissions admittime')
    assert len(records) == 31 and 'admittime' in context['columns']['admissions']
    assert pipeline.db.schema.has_edge('admissions.hadm_id', 'icustays.hadm_id')
    assert not pipeline.db.schema.has_edge('admissions.hadm_id', 'patients.subject_id')
    assert ungrounded_join_keys(
        'SELECT a.hadm_id FROM admissions a JOIN patients p ON a.hadm_id = p.subject_id',
        pipeline.db.schema)
    assert not ungrounded_join_keys(
        'SELECT a.hadm_id FROM admissions a JOIN patients p ON a.subject_id = p.subject_id',
        pipeline.db.schema)
    records[0]['ddl'] += ' '
    with pytest.raises(ValueError, match='pinned'):
        build_pipeline(MockBigQuery(records), MockLLM({}), schema_index=index)


# v5.1 flow (verify every candidate), kept as the ablation baseline.
V51 = dict(fingerprint_selection=False, parallel_branches=False)

QUESTION = 'Count admissions in the final 48 hours before discharge'
TABLE = '`demo.hosp.admissions`'
CORRECT = f'SELECT COUNT(DISTINCT hadm_id) AS n FROM {TABLE} WHERE admittime >= DATETIME_SUB(dischtime, INTERVAL 48 HOUR)'
WRONG = f'SELECT hadm_id, COUNT(*) AS n FROM {TABLE} GROUP BY hadm_id'
RECORDS = [{'table': 'admissions', 'ddl': f'CREATE TABLE {TABLE} (hadm_id INT64, admittime DATETIME, dischtime DATETIME)'}]


def model_for(sqls, checks=(), repairs=()):
    return MockLLM({
        'link': [{'requirements': [{'id': 'r1', 'span': QUESTION, 'kind': 'output',
                                   'description': 'One aggregate for the discharge window'}],
                  'links': [], 'joins': [], 'ambiguities': []}],
        'decompose': [{'steps': [{'id': 's1', 'operation': 'aggregate', 'depends_on': [],
                                 'requirement_ids': ['r1'], 'tables': ['admissions'],
                                 'description': 'Apply the discharge window and count admissions'}],
                       'output_step': 's1'}],
        'generate': [{'sql': sql} for sql in sqls], 'repair': [{'sql': sql} for sql in repairs],
        'verify': list(checks),
    })


def test_linker_coverage_feedback_uses_same_question_then_fails_open_after_two_attempts():
    missing_window = {'requirements': [
        {'id': 'r1', 'span': 'Count admissions', 'kind': 'output', 'description': 'Count admissions'}],
        'links': [], 'joins': [], 'ambiguities': []}
    model = MockLLM({'link': [missing_window, missing_window],
                     'generate': [{'sql': CORRECT}, {'sql': CORRECT}]})
    db = MockBigQuery(RECORDS)
    output = build_pipeline(db, model).run(QUESTION)
    # v5 fail-open: the linked branch is skipped, full-schema branches still answer.
    assert output['status'] == 'answered' and output['fallbacks'] == ['link_fallback']
    # v6: without a linker the two full-schema branches run (concurrently) and agree.
    assert sorted(call['stage'] for call in model.calls) == ['generate', 'generate', 'link', 'link']
    first, second = [json.loads(call['prompt'][-1]['content']) for call in model.calls[:2]]
    assert first['original_question'] == second['original_question'] == QUESTION
    assert 'Uncovered question literal: 48' in second['interface_validation_error']
    assert json.loads(second['previous_invalid_output'])['requirements'] == missing_window['requirements']


def verification(cid, supported=True):
    return {'checks': [{'requirement_id': 'r1', 'status': 'satisfied' if supported else 'contradicted',
                        'sql_evidence_ids': [f'{cid}:query'],
                        'schema_refs': ['admissions.hadm_id'] if supported else [],
                        'evidence': 'Aggregate and discharge interval' if supported else 'Grouped rows omit the discharge interval'}],
            'question_coverage': {'status': 'complete', 'uncovered_spans': [], 'extra_constraints': []},
            'verdict': 'supported' if supported else 'contradicted'}


def test_temporal_and_output_verification_repairs_then_deduplicates_candidates():
    model = model_for([WRONG, CORRECT, CORRECT],
                      [verification('c1', False), verification('c1r'), verification('c2'), verification('c3')],
                      [CORRECT])
    db = MockBigQuery(RECORDS, results={CORRECT: Execution(('n',), ((1,), (2,)), True)})
    output = build_pipeline(db, model, flags=ProposedFlags(**V51)).run(QUESTION)
    assert output['status'] == 'answered', output['reason']
    assert output['sql'] == CORRECT and output['selected']['id'] == 'c1r'
    assert any(event.get('category') == 'semantic' for event in output['trace'])
    payload = json.loads(next(c for c in model.calls if c['stage'] == 'verify')['prompt'][1]['content'])
    assert payload['static_inspection']['output_columns'] == ['hadm_id', 'COUNT(*) AS n']
    assert 'fingerprint' not in payload['execution_metadata']


@pytest.mark.parametrize('bad_sql,kind', [('SELECT ( FROM', 'syntax'),
                                        (f'SELECT missing FROM {TABLE}', 'schema')])
def test_correction_reason_distinguishes_syntax_and_schema(bad_sql, kind):
    model = model_for([bad_sql, CORRECT, CORRECT], repairs=[CORRECT])
    flags = ProposedFlags(requirement_verification=False)
    output = build_pipeline(MockBigQuery(RECORDS), model, flags=flags).run(QUESTION)
    assert output['status'] == 'answered'
    assert output['selected']['history'][0]['error_category'] == kind


@pytest.mark.parametrize('incomplete', [True, False])
def test_budget_and_incomplete_execution_never_request_correction(incomplete):
    class Database(MockBigQuery):
        def execute(self, sql):
            if not incomplete:
                raise BudgetExceeded('cap reached')
            return Execution(('n',), ((1,),), False)

    model = model_for([CORRECT])
    output = build_pipeline(Database(RECORDS), model, flags=ProposedFlags(**V51)).run(QUESTION)
    assert output['status'] == 'error' and output['selected'] is None
    assert [call['stage'] for call in model.calls] == ['link', 'decompose', 'generate']


def test_base_ablation_uses_one_prompt_and_live_scope_rejects_unapproved_case():
    flags = ProposedFlags(base_prompt_only=True, schema_rag=False, multi_layer_rag=False,
                          sql_validation=False, self_correction=False, requirement_verification=False)
    model = model_for([CORRECT])
    db = MockBigQuery(RECORDS)
    assert build_pipeline(db, model, flags=flags).run(QUESTION)['status'] == 'answered'
    assert [call['stage'] for call in model.calls] == ['generate']
    assert db.calls == [('dry_run', CORRECT), ('execute', CORRECT)]
    assert ProposedModelProvider.serialize_prompt('[{"role":"system","content":"synthetic"}]') == [
        {'role': 'system', 'content': 'synthetic'}]
    with pytest.raises(PermissionError, match='scoped validation'):
        run_proposed_pilot_case(None, approval=None, pilot_manifest=None, schema_manifest=None,
                                schema_index=None, master_manifest=None, corpus_path=None,
                                clinical_path=None, bigquery_config=None, api_budget=None,
                                sql_budget=None, output_root=None, result_store=None)


def test_proposed_approval_loads_and_rejects_other_phase(tmp_path):
    now = datetime.now(timezone.utc)
    approval = ProposedPilotApproval(
        approval_id='synthetic', approver='test', authority='test', risk_acknowledged=True,
        iam_status='READ_ONLY_LIKELY_WITH_APPROVED_RISK', valid_from_utc=now,
        valid_until_utc=now + timedelta(hours=1), principal=READER_PRINCIPAL,
        project_id=EXPECTED_PROJECT, datasets=tuple(EXPECTED_DATASETS), location='US',
        manifest_sha256='a' * 64, pilot_manifest_sha256='b' * 64,
        model_id='gpt-5-mini-2025-08-07', case_ids=tuple(map(str, range(5))),
        max_bytes_billed_per_sql=100, timeout_seconds=5, max_rows=10,
        max_result_bytes=500, api_budget_sha256='c' * 64, sql_budget_sha256='d' * 64,
        result_storage_policy_reference='synthetic', artifact_retention_days=7,
        index_sha256='e' * 64, clinical_sha256='f' * 64, run_config_sha256='1' * 64)
    path = tmp_path / 'approval.json'
    payload = {field.name: getattr(approval, field.name) for field in fields(approval)}
    path.write_text(json.dumps(payload, default=lambda value: value.isoformat()))
    assert ProposedPilotApproval.from_file(path) == approval
    common = {field.name: getattr(approval, field.name) for field in fields(BenchmarkExecutionApproval)}
    with pytest.raises(ValueError, match='phase'):
        BenchmarkExecutionApproval(**common)
