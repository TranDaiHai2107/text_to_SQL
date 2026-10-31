"""Separate post-inference scorer; do not inspect partial replicate scores."""
import argparse
from collections import Counter
import statistics
from validation_common import ROOT, DB, load, dump, sha, checked_name, verify_protocol, activate_methods, jsonl
from run_confirmatory import preflight, dataset_directory
from statistics_tools import paired_clusters, holm


def metrics(gold, sqls, execute_sql, scorer):
    if set(gold) != set(sqls) or any(not isinstance(v, str) for v in sqls.values()):
        raise ValueError('Full string-valued prediction mapping required; no padding/dropping')
    answers = {}
    errors = 0
    for key, sql in sqls.items():
        if sql == 'null':
            answers[key] = 'null'
        else:
            try:
                answers[key] = execute_sql(sql)
            except Exception:
                answers[key] = 'error_pred'
                errors += 1
    result = scorer(gold, answers, 'official')
    ans = {k for k in gold if gold[k] != 'null'}
    nonnull = {k for k, v in sqls.items() if v != 'null'}
    correct_sql = sum(result['per_question'][k]=='correct' for k in ans)
    result.update(EX=100*correct_sql/len(ans), VSR=100*(len(nonnull)-errors)/len(gold),
                  coverage=100*len(nonnull)/len(gold),
                  answer_precision=100*correct_sql/len(nonnull) if nonnull else None,
                  correct_answerable_sql=correct_sql,
                  false_answers_on_unanswerable=sum(sqls[k]!='null' for k in set(gold)-ans),
                  execution_errors=errors)
    return result


def usage(directory):
    events = jsonl(directory/'api_events.jsonl') if (directory/'api_events.jsonl').exists() else []
    success = [e for e in events if e['kind']=='success']
    unique = {e['request_hash']:e for e in success}
    return {'unique_successful_calls':len(unique), 'failed_attempt_events':len(events)-len(success),
            'input_tokens':sum(e['usage']['prompt_tokens'] for e in unique.values()),
            'output_tokens_including_reasoning':sum(e['usage']['completion_tokens'] for e in unique.values()),
            'model_versions':dict(Counter(e['model'] for e in unique.values())),
            'system_fingerprints':dict(Counter(str(e.get('system_fingerprint')) for e in unique.values()))}


def summarize(name):
    protocol = verify_protocol()
    ready = preflight(name)
    dataset = dataset_directory(name)
    inputs = load(dataset/'inputs.json')
    expected = {r['id'] for r in inputs}
    clusters = {r['id']:r['cluster_id'] for r in inputs}
    directory = ROOT/'runs'/checked_name(name)
    activate_methods()
    from baseline_core import execute_readonly, score_answers
    from methods import ARM_NAMES
    # Require all declared replicates BEFORE opening gold or computing any score.
    by_rep = {}
    costs = {}
    family_latency = {}
    for rep in protocol['replicates']:
        source = directory/f'replicate_{rep}'
        config = load(source/'config.json')
        if config != {'dataset_manifest_sha256':sha(dataset/'manifest.json'),
                      'protocol_sha256':sha(ROOT/'protocol.json'), 'replicate':rep,
                      'historical_cache_reuse':False, 'model':protocol['model']}:
            raise ValueError('Wrong replicate configuration')
        if load(source/'status.json')['state']!='inference_complete_unscored':
            raise ValueError('All replicates must complete inference before scoring')
        by_rep[rep] = {arm:load(source/(arm+'.prediction.json')) for arm in ARM_NAMES}
        if any(set(pred)!=expected for pred in by_rep[rep].values()):
            raise ValueError('Incomplete prediction export')
        checkpoints = [load(p) for p in (source/'checkpoints').glob('*.json')]
        if len(checkpoints)!=len(inputs) or {r['id'] for r in checkpoints}!=expected:
            raise ValueError('Complete question checkpoints required')
        for row in checkpoints:
            if any(by_rep[rep][arm][row['id']]!=row['arms'][arm] for arm in ARM_NAMES):
                raise ValueError('Prediction/checkpoint mismatch')
        costs[str(rep)] = {family:usage(source/family) for family in protocol['generation_families']}
        family_latency[str(rep)] = {family:sum(r['family_wall_seconds'][family] for r in checkpoints)
                                   for family in protocol['generation_families']}
    gold = load(dataset/'gold_answers.json')
    versions = {version for families in costs.values() for record in families.values()
                for version in record['model_versions']}
    if len(versions) != 1:
        raise ValueError('Backbone version changed or is missing; do not assert a matched-model comparison')
    answer_cache = {}
    def execute_sql(sql):
        if sql not in answer_cache:
            try:
                answer_cache[sql] = (True, execute_readonly(sql, DB, 30))
            except Exception:
                answer_cache[sql] = (False, None)
        success, result = answer_cache[sql]
        if not success:
            raise ValueError('Invalid/failed SQL')
        return result
    evaluations = {str(rep):{arm:metrics(gold, sqls, execute_sql, score_answers)
                            for arm,sqls in variants.items()} for rep,variants in by_rep.items()}
    contrast_results = {}
    pairs = [protocol['primary_contrast']] + protocol['secondary_contrasts']
    for left, right in pairs:
        contrast_results[left+' - '+right] = paired_clusters(
            [evaluations[str(rep)][left]['per_question'] for rep in protocol['replicates']],
            [evaluations[str(rep)][right]['per_question'] for rep in protocol['replicates']], clusters)
    secondary = [a+' - '+b for a,b in protocol['secondary_contrasts']]
    adjusted = holm({key:contrast_results[key]['p_two_sided'] for key in secondary})
    for key, p in adjusted.items():
        contrast_results[key]['p_Holm_secondary'] = p
    primary_key = ' - '.join(protocol['primary_contrast'])
    primary = contrast_results[primary_key]
    passed = primary['delta_RS10']>0 and primary['CI95'][0]>0 and primary['p_two_sided']<.05
    summary = {arm:{'mean_RS10':statistics.mean(evaluations[str(rep)][arm]['scores']['RS10']
                           for rep in protocol['replicates']),
                   'per_replicate_RS10':[evaluations[str(rep)][arm]['scores']['RS10']
                           for rep in protocol['replicates']]} for arm in ARM_NAMES}
    report = {'state':'complete_positive_primary' if passed else 'complete_inconclusive_or_negative_primary',
              'protocol_sha256':sha(ROOT/'protocol.json'), 'dataset_manifest_sha256':sha(dataset/'manifest.json'),
              'questions':ready['questions'], 'clusters':ready['clusters'], 'summary':summary,
              'contrasts':contrast_results, 'replicate_evaluations':evaluations,
              'family_generation_usage':costs, 'family_wall_seconds':family_latency,
              'cost_note':'Shared generation reused by ablation arms; family costs must not be summed once per derived arm. Dollar cost not inferred from token counts.',
              'primary_claim_supported_under_registered_conditions':passed,
              'independence_proven_by_software':False,
              'paper_RS10_comparison_allowed':False,
              'scope':'English to SQL, pinned database; no ASR/translation/SQL-to-text/clinical safety claim'}
    dump(directory/'FINAL_CONFIRMATION.json', report)
    print(report['state'], primary)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True)
    summarize(parser.parse_args().dataset)
