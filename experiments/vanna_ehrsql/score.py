"""Score completed Vanna records with the exact shared official scorer."""
import argparse
import json
from benchmark import ROOT, BASELINE, load, questions, run_path, sha, dump
from bridge import shared


def score(directory):
    directory = directory.resolve()
    config = load(directory/'config.json')
    expected = {r['id'] for r in questions(config['split'])}
    records = [json.loads(line) for line in (directory/'records.jsonl').read_text(encoding='utf-8').splitlines()] if (directory/'records.jsonl').exists() else []
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)) or not set(ids) <= expected:
        raise ValueError('Duplicate or foreign question IDs')
    report = shared('evaluate').evaluate(directory)
    report['system'] = 'Vanna AI legacy SQL/RAG'
    report['model'] = config['model']
    report['prediction_source'] = 'new_model_inference_not_author_cache'
    report['evaluation_scope'] = ('in_sample_train_with_self_retrieval' if config['split']=='train'
                                  else 'held_out_'+config['split'])
    report['comparable_to_published_test'] = config['split']=='test' and set(ids)==expected
    report['full_benchmark_complete'] = set(ids) == expected
    report['wrapper_code_sha256'] = {p.name:sha(p) for p in ROOT.glob('*.py')}
    dump(directory/'evaluation.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', required=True)
    args = parser.parse_args()
    report = score(run_path(args.run_name))
    print(json.dumps({'completed_questions':report['completed_questions'],
                     'full_benchmark_complete':report['full_benchmark_complete'],
                     'variants':{name:m['scores'] for name,m in report.get('variants', {}).items()}}, indent=2))


if __name__ == '__main__':
    main()
