"""Create immutable hashes outside V5; never modify the frozen implementation."""
from validation_common import ROOT, WORKSPACE, EXPERIMENTS, BASELINE, DB, V3_RUN, V4_RUN, V5_RUN, load, sha, freeze


def build_lock():
    old = load(V5_RUN / 'protocol.json')
    for directory, entries in ((EXPERIMENTS / 'ours_improved_v5', old['source_sha256']),
                               (EXPERIMENTS / 'ours_improved_v3', old['v3_source_sha256'])):
        if any(sha(directory / name) != digest for name, digest in entries.items()):
            raise ValueError('Historical V5/V3 protocol no longer matches implementation')
    if sha(DB) != old['database_sha256'] or sha(BASELINE / 'baseline_core.py') != old['scorer_sha256']:
        raise ValueError('Historical database/scorer mismatch')
    if sha(EXPERIMENTS / 'ours_improved_v4/postprocess_v4.py') != old['v4_postprocess_sha256']:
        raise ValueError('Historical V4 dependency changed')
    files = {DB, BASELINE / 'baseline_core.py', BASELINE / 'source_manifest.json'}
    for name in ('ours_improved_v3', 'ours_improved_v4', 'ours_improved_v5', 'ours_improved_v2',
                 'apply_my_work_to_baseline', 'vanna_ehrsql'):
        files.update((EXPERIMENTS / name).glob('*.py'))
    files.update((EXPERIMENTS / 'vanna_ehrsql/.vendor/vanna/legacy').rglob('*.py'))
    files.update((BASELINE / 'upstream/src/scoring_program').glob('*.py'))
    for run in (V3_RUN, V4_RUN, V5_RUN):
        files.update(run / n for n in ('protocol.json', 'policy.json', 'test/records.jsonl', 'test/evaluation.json'))
    files.update(V5_RUN / n for n in ('FINAL_RESULTS.json', 'VALIDATION.json'))
    for split in ('train', 'dev', 'test'):
        files.add(BASELINE / f'data/inputs/{split}.json')
        files.update(BASELINE / f'data/gold/{split}/{name}.json' for name in ('label', 'answer'))
    return {'version': 'V5_final_20261029', 'selected_policy': 'strict3_canonical',
            'primary_RS10': load(V5_RUN / 'VALIDATION.json')['primary_RS10'],
            'historical_status': 'exploratory_test_informed_not_independent_holdout',
            'frozen_scope': 'algorithm, transitive local source, dataset, scorer, policy and historic outputs',
            'files': {p.relative_to(WORKSPACE).as_posix(): sha(p) for p in sorted(files)}}


if __name__ == '__main__':
    value = build_lock()
    freeze(ROOT / 'V5_LOCK.json', value)
    print(f"V5 frozen: {len(value['files'])} files; RS10={value['primary_RS10']:.4f}")
