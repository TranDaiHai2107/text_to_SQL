"""Synthetic regressions for the pilot diagnosis; no reference data or API."""
from ehrqa.clinsql.cot import generation_prompt, _source_function
from ehrqa.clinsql.cot_runner import ClinSQLCoT
from ehrqa.clinsql.interfaces import Execution
from ehrqa.clinsql.offline import MockBigQuery, MockLLM


def test_successful_extra_projection_does_not_trigger_baseline_refinement():
    sql = 'SELECT 5 AS requested_value, 2 AS extra_count;'
    model = MockLLM({'generate': [f'```sql\n{sql}\n```']})
    db = MockBigQuery([], results={sql: Execution(
        ('requested_value', 'extra_count'), ((5, 2),), True)})
    prediction = ClinSQLCoT(model, db, 'CREATE TABLE synthetic (n INT64)').run(
        'synthetic/001', 'Return the requested value')
    assert prediction.status == 'executed' and prediction.sql == sql
    assert prediction.execution_attempts == 1
    assert [call['stage'] for call in model.calls] == ['generate']


def test_prompt_project_adaptation_changes_only_two_dataset_references():
    schema = ('CREATE TABLE `demo.mimiciv_3_1_hosp.patients` (subject_id INT64);\n'
              'CREATE TABLE `demo.mimiciv_3_1_icu.icustays` (stay_id INT64);')
    question = 'Synthetic question, no clinical data'
    native = _source_function('prompt_utils', 'build_generation_prompt')(question, schema)
    expected = native.replace('physionet-data.mimiciv_3_1_hosp',
                              'demo.mimiciv_3_1_hosp').replace(
                                  'physionet-data.mimiciv_3_1_icu',
                                  'demo.mimiciv_3_1_icu')
    assert generation_prompt(question, schema) == expected
