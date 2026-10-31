"""Inventory existing exposure without opening evaluation annotations."""
from collections import Counter
from validation_common import ROOT, known_inputs, normalized, dump, sha


def main():
    rows = known_inputs()
    counts = Counter(r['split'] for r in rows)
    value = {'date':'2026-10-29', 'known_question_counts':dict(counts),
             'total_existing_questions':len(rows),
             'unique_normalized_questions':len({normalized(r['question']) for r in rows}),
             'split_roles':{'train':'knowledge', 'dev':'knowledge_and_method_design',
                            'test':'exploratory_evaluation_feedback_observed'},
             'eligible_independent_holdout_from_existing_splits':False,
             'registered_new_datasets':[p.parent.name for p in (ROOT/'datasets').glob('*/manifest.json')],
             'external_candidate':{
                 'name':'EHRSQL NeurIPS 2022 MIMIC-III / eICU',
                 'author_repository':'https://github.com/glee4810/EHRSQL',
                 'paper':'https://papers.neurips.cc/paper_files/paper/2022/hash/643e347250cf9289e5a2a6c1ed5ee42e-Abstract-Datasets_and_Benchmarks.html',
                 'checked_readme':'https://raw.githubusercontent.com/glee4810/EHRSQL/main/README.md',
                 'status':'candidate_only_not_downloaded_or_scored_not_an_approved_holdout',
                 'requirements':['Pin release/commit and annotation version',
                                 'Audit overlap with EHRSQL 2024 by question and template',
                                 'Separate cross-database adapter/protocol: schema and clock differ',
                                 'Run all controls on the same new data; do not compare against old paper RS10 directly']},
             'next_required_input':'New reviewed question-SQL/null dataset compatible with pinned MIMIC-IV, OR a separately validated cross-database extension protocol.',
             'API_calls':0}
    dump(ROOT/'DATASET_INVENTORY.json', value)
    print(value)
    return value


if __name__ == '__main__':
    main()
