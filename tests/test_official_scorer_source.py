"""Native scorer source parity without network, clinical data or paid judge."""
import json
from pathlib import Path

from ehrqa.clinsql.evaluator import OfficialClinSQLEvaluator
from ehrqa.clinsql.official_scorer_source import (
    count_judge_leaf_calls, load_verified_native_scorer)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'external/clinsql_official'
LOCK = ROOT / 'PAPER_SOURCE_LOCK.json'


def test_native_scorer_injection_uses_source_logic_without_api(tmp_path):
    scorer_type = load_verified_native_scorer(SOURCE, LOCK)
    sample = tmp_path / 'validation/Example/easy_level_queries/001'
    sample.mkdir(parents=True)
    (sample / 'query_001.txt').write_text('Synthetic question', encoding='utf-8')
    (sample / 'sql_001.sql').write_text('SELECT 1', encoding='utf-8')
    (sample / 'result_001.csv').write_text('value\n1\n', encoding='utf-8')
    rubric = {'id': 'root', 'requirements': 'Synthetic requirement', 'weight': 1}
    for name in ('sql_rubric_tree.json', 'results_rubric_tree.json'):
        (sample / name).write_text(json.dumps(rubric), encoding='utf-8')
    prompts = []

    def factory():
        # The system test Python has no OpenAI SDK; native scoring logic below
        # only needs an injected local transport, not the Azure constructor.
        scorer = object.__new__(scorer_type)

        def fake_azure(prompt):
            prompts.append(prompt)
            return 'Score: 1\nExplanation: synthetic'

        scorer._call_azure = fake_azure
        return scorer

    evaluator = OfficialClinSQLEvaluator(SOURCE, source_commit='locked-test',
                                         judge_config_hash='synthetic-test',
                                         scorer_factory=factory)
    result = evaluator.evaluate_saved_predictions(tmp_path, split='validation')
    assert result['sql_score'] == result['execution_score'] == 1.0
    assert len(prompts) == 2
    assert all('Synthetic question' in prompt and 'Model results rows' in prompt
               for prompt in prompts)


def test_native_judge_leaf_count_for_saved_pilot():
    report = count_judge_leaf_calls(SOURCE, [
        'Diagnostic_Procedures/easy_level_queries/058',
        'Vital_Signs_Monitoring/easy_level_queries/044',
        'Laboratory_Results_Analysis/medium_level_queries/079',
        'Medication_Management/medium_level_queries/012',
        'Patient_Demographics_and_Admissions/hard_level_queries/058',
    ])
    assert report['sql_leaf_calls'] == 58
    assert report['results_leaf_calls'] == 52
