"""No-API ablations on OLD test. Always exploratory; never confirmation."""
from copy import deepcopy
from validation_common import ROOT, BASELINE, V3_RUN, V4_RUN, V5_RUN, load, dump, jsonl, sha, verify_protocol, activate_methods


def main():
    protocol = verify_protocol()
    activate_methods()
    from infrastructure import score_answers
    from scoring_v3 import sql_answer, api_usage
    raw = jsonl(V3_RUN / 'test/records.jsonl')
    original = {r['id']: r for r in raw}
    ids = set(original)
    gold = load(BASELINE / 'data/gold/test/answer.json')
    if ids != set(gold) or len(raw) != len(ids) or len(ids) != 1167:
        raise ValueError('Full original test required')
    bundles = {}
    for name, run, variant in [
        ('ours_direct_gef', V3_RUN, 'v3_direct'),
        ('ours_raw_three', V3_RUN, 'v3_selected'),
        ('ours_round3_no_compiler', V4_RUN, 'v4_selected'),
        ('v5_canonical_direct', V5_RUN, 'v5_direct'),
        ('v5_full', V5_RUN, 'v5_selected')]:
        bundles[name] = {'metric': load(run / 'test/evaluation.json')['variants'][variant],
                         'predictions': load(run / f'test/{variant}.prediction.json')}
    pred = {}
    sqls = {}
    for key, row in original.items():
        candidate = deepcopy(row['candidates'][0])
        if candidate.get('guard_rejected') and candidate.get('pre_guard_sql') is not None:
            candidate['sql'] = candidate['pre_guard_sql']
            candidate['execution'] = candidate['pre_guard_execution']
        sqls[key] = candidate['sql']
        pred[key] = sql_answer(candidate)
    metric = score_answers(gold, pred, 'official')
    answerable = {k for k in gold if gold[k] != 'null'}
    answered = {k for k in sqls if sqls[k] != 'null'}
    metric.update(EX=100 * sum(metric['per_question'][k] == 'correct' for k in answerable) / len(answerable),
                  VSR=100 * sum(isinstance(v, list) for v in pred.values()) / len(ids),
                  coverage=100 * len(answered) / len(ids))
    bundles['ours_direct_before_guard'] = {'metric': metric, 'predictions': sqls}
    for name, bundle in bundles.items():
        if set(bundle['predictions']) != ids or set(bundle['metric']['per_question']) != ids:
            raise ValueError(f'Incomplete arm: {name}')
    contrasts = []
    for left, right, purpose in [
        ('ours_direct_gef', 'ours_direct_before_guard', 'GEF + hard-contract guard package, same direct generation'),
        ('ours_raw_three', 'ours_direct_gef', 'Three-route selective prediction package, greater generation budget'),
        ('ours_round3_no_compiler', 'ours_raw_three', 'Round3 fingerprint + full-dictionary guards package'),
        ('v5_full', 'ours_round3_no_compiler', 'Deterministic namespace compiler, same candidates and selector'),
        ('v5_full', 'v5_canonical_direct', 'Consensus vs canonical direct; coverage/accuracy tradeoff')]:
        a, b = bundles[left]['metric'], bundles[right]['metric']
        changes = {}
        for key in ids:
            pair = b['per_question'][key] + ' -> ' + a['per_question'][key]
            changes[pair] = changes.get(pair, 0) + 1
        contrasts.append({'left': left, 'right': right, 'purpose': purpose,
                          'RS10_delta': a['scores']['RS10'] - b['scores']['RS10'], 'transitions': changes})
    metrics = {name: {k: v for k, v in b['metric'].items() if k != 'per_question'} for name, b in bundles.items()}
    result = {'status': 'exploratory_only_test_already_exposed', 'questions': 1167,
              'new_model_calls': 0, 'original_effective_generation_usage': api_usage(V3_RUN / 'test'),
              'protocol_sha256': sha(ROOT / 'protocol.json'), 'primary_metric': protocol['primary_metric'],
              'scope': 'post-generation component packages only; retrieval cannot be ablated from cached SQL',
              'arms': metrics, 'contrasts': contrasts,
              'confirmatory_claim_allowed': False, 'V5_modified': False}
    dump(ROOT / 'runs/exploratory_20261029/ablation.json', result)
    print('EXPLORATORY, no API:')
    for name, m in metrics.items():
        print(f"{name}: RS10={m['scores']['RS10']:.4f}; EX={m['EX']:.4f}; wrong={m['wrong']}")
    return result


if __name__ == '__main__':
    main()
