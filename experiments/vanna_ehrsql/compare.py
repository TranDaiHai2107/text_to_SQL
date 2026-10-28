"""Compare THREE full test systems. Partial runs cannot become final results."""
import argparse
from benchmark import BASELINE, OUR_SYSTEM, DB, load, questions, run_path, sha, dump
from bridge import shared


def validate_report(report, expected):
    if report.get('split') != 'test' or not report.get('full_benchmark_complete'):
        raise ValueError('Only complete test reports may be compared with the full paper')
    if not report.get('official_normalization'):
        raise ValueError('The official scorer is required')
    for metrics in report['variants'].values():
        if set(metrics['per_question']) != expected:
            raise ValueError('Reports do not contain identical complete test IDs')


def compare(vanna_run, our_run, our_variant=None):
    vanna_dir = run_path(vanna_run)
    # The same conservative name validation applies to both run directories.
    our_dir = OUR_SYSTEM/'runs'/run_path(our_run).name
    vanna_report = load(vanna_dir/'evaluation.json')
    our_report = load(our_dir/'evaluation.json')
    expected = {r['id'] for r in questions('test')}
    validate_report(vanna_report, expected)
    validate_report(our_report, expected)
    vanna_config, our_config = load(vanna_dir/'config.json'), load(our_dir/'config.json')
    chosen_vanna = vanna_config['primary_variant']
    chosen_ours = our_variant or our_config['primary_variant']
    if chosen_ours != our_config['primary_variant']:
        raise ValueError('Use the predeclared primary; do not select by the test score')
    paper_path = BASELINE/'runs/audit_20261023_docker/test_gpt_probgate_425_gef/scores_official.json'
    paper = load(paper_path)
    if set(paper['per_question']) != expected or paper.get('scorer') != 'official':
        raise ValueError('Paper replay must use the same full official protocol')
    paper_prediction = paper_path.parent/'prediction.json'
    if sha(paper_prediction) != paper['prediction_sha256']:
        raise ValueError('Paper replay prediction provenance mismatch')
    manifest_path = BASELINE/'source_manifest.json'
    manifest = load(manifest_path)
    if sha(DB) != manifest['files']['upstream/src/data/mimic_iv/mimic_iv.sqlite']:
        raise ValueError('Database no longer matches the pinned benchmark')
    if vanna_config['index']['source']['database_sha256'] != sha(DB) or our_config['baseline_manifest_sha256'] != sha(manifest_path):
        raise ValueError('Systems were not configured against the pinned benchmark')
    gold = load(BASELINE/'data/gold/test/answer.json')
    answerable = [key for key in expected if gold[key] != 'null']
    paper_ex = 100*sum(paper['per_question'][key]=='correct' for key in answerable)/len(answerable)
    paper_prediction_data = load(paper_prediction)
    # This best cached branch has already applied GEF; account for any retained
    # execution error rather than interpreting non-null SQL as successful by fiat.
    paper_vsr = 100*(sum(sql!='null' for sql in paper_prediction_data.values())-len(paper['execution_errors']))/len(expected)
    ours = our_report['variants'][chosen_ours]
    vanna = vanna_report['variants'][chosen_vanna]
    same_model = (vanna_config['model'] == our_config['model'] and
                  vanna_config.get('provider', 'groq') == our_config.get('provider', 'groq') and
                  vanna_config.get('reasoning_effort') == our_config.get('reasoning_effort') and
                  vanna_config.get('sql_tokens') == our_config.get('max_sql_completion_tokens') and
                  vanna_config.get('temperature') == our_config.get('temperature'))
    result = {
        'split':'test', 'questions':len(expected), 'scorer':'official',
        'paper':{'source':'authors_cached_predictions_official_replay', 'scores':paper['scores'], 'fine_tuned':True,
                 'answerable_ex':paper_ex, 'vsr_all_questions':paper_vsr,
                 'extra_metric_note':'EX/VSR derived from released cached predictions and the common protocol; not claimed to be values reported in the paper.'},
        'ours':{'variant':chosen_ours, 'model':our_config['model'], 'scores':ours['scores'],
                'answerable_ex':ours['answerable_ex'], 'vsr_all_questions':ours['vsr_all_questions']},
        'vanna':{'variant':chosen_vanna, 'model':vanna_config['model'], 'scores':vanna['scores'],
                 'answerable_ex':vanna['answerable_ex'], 'vsr_all_questions':vanna['vsr_all_questions'], 'fine_tuned':False},
        'same_model_and_core_generation_settings_for_ours_vs_vanna':same_model,
        'interpretation':'System-level comparison against the published paper. Ours versus Vanna supports a method comparison only with matched backbone/settings; retrieval and inference resources must also be reported.',
        'paired_rs10_ours_minus_vanna':shared('evaluate').paired_delta(vanna['per_question'], ours['per_question']),
        'paired_rs10_ours_minus_paper':shared('evaluate').paired_delta(paper['per_question'], ours['per_question']),
        'source_sha256':{str(p):sha(p) for p in [vanna_dir/'evaluation.json', our_dir/'evaluation.json', paper_path]},
    }
    dump(vanna_dir/'three_system_comparison.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--vanna-run', required=True)
    parser.add_argument('--our-run', required=True)
    args = parser.parse_args()
    result = compare(args.vanna_run, args.our_run)
    print('Saved three_system_comparison.json; same model/settings:', result['same_model_and_core_generation_settings_for_ours_vs_vanna'])


if __name__ == '__main__':
    main()
