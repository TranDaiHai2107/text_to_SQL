"""No paid calls by default. Complete all registered questions, arms and replicates."""
import argparse
from pathlib import Path
import os
import time
from validation_common import ROOT, VANNA, DB, load, dump, sha, freeze, checked_name, verify_protocol, activate_methods


def dataset_directory(name):
    return ROOT / 'datasets' / checked_name(name)


def preflight(name=None):
    protocol = verify_protocol()
    if name is None:
        return {'state':'awaiting_new_eligible_dataset', 'API_calls':0,
                'reason':'All local EHRSQL 2024 splits were used for knowledge or test-informed development.',
                'registered_datasets':[p.parent.name for p in (ROOT/'datasets').glob('*/manifest.json')],
                'protocol':protocol['id'], 'V5_frozen':True}
    directory = dataset_directory(name)
    manifest = load(directory / 'manifest.json')
    if manifest['protocol_sha256'] != sha(ROOT/'protocol.json') or manifest['database_sha256'] != sha(DB):
        raise ValueError('Dataset/protocol/database mismatch')
    for filename, digest in manifest['files'].items():
        if sha(directory/filename) != digest:
            raise ValueError('Sealed dataset changed: '+filename)
    return {'state':'ready_for_registered_inference', 'API_calls':0, 'dataset':name,
            'questions':manifest['questions'], 'clusters':manifest['clusters'],
            'replicates':protocol['replicates'],
            'initial_calls_all_replicates':manifest['questions']*9*len(protocol['replicates']),
            'maximum_successful_calls_with_repairs':manifest['questions']*18*len(protocol['replicates']),
            'budget_note':protocol['budget_comparison']}


def inference(name, replicate):
    protocol = verify_protocol()
    preflight(name)
    if replicate not in protocol['replicates']:
        raise ValueError('Replicate not in the registered protocol')
    dataset = dataset_directory(name)
    # ONLY sanitized questions/cluster IDs are loaded. Gold is read later by the separate scorer.
    inputs = load(dataset/'inputs.json')
    directory = ROOT/'runs'/checked_name(name)/f'replicate_{replicate}'
    directory.mkdir(parents=True, exist_ok=True)
    freeze(directory/'config.json', {'dataset_manifest_sha256':sha(dataset/'manifest.json'),
           'protocol_sha256':sha(ROOT/'protocol.json'), 'replicate':replicate,
           'historical_cache_reuse':False, 'model':protocol['model']})
    activate_methods()
    from client_v3 import V3Client
    from retrieval_v3 import StructuredRAG
    from pipeline_v3 import run_question
    from postprocess_v5 import load_metadata
    from methods import DenseExampleControl, vanna_candidates, derive_arms, ARM_NAMES
    from infrastructure import api_balance, RunBlocked
    import sys
    sys.path.insert(1, str(VANNA))
    from vanna_adapter import make_vanna, assert_index, training_documents
    from benchmark import corpus, schema
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    balance = api_balance()
    if balance.get('is_available') is False:
        raise RunBlocked('No balance; no scoring/null padding')
    if not (directory/'starting_balance.json').exists():
        dump(directory/'starting_balance.json', balance)
    rag = StructuredRAG()
    dense = DenseExampleControl(rag)
    vn = make_vanna(VANNA/'indexes/chroma_train_dev')
    index = assert_index(vn, VANNA/'indexes/chroma_train_dev', ('train','dev'))
    for kind, documents in training_documents(corpus(('train','dev')), schema()).items():
        stored = getattr(vn, kind+'_collection').get(include=['documents'])
        if dict(zip(stored['ids'], stored['documents'])) != documents:
            raise ValueError('Vanna knowledge content differs from the pinned train/dev corpus')
    freeze(directory/'knowledge.json', {'ours':rag.manifest, 'vanna':index})
    metadata = load_metadata()
    clients = {}
    for family in protocol['generation_families']:
        normal = V3Client(directory/family, thinking=False)
        reasoning = V3Client(directory/family, thinking=True)
        reasoning._event_lock, reasoning._keys_lock, reasoning._key_locks = normal._event_lock, normal._keys_lock, normal._key_locks
        clients[family] = {'normal':normal, 'reasoning':reasoning}
    expected = {r['id']:r['question'] for r in inputs}
    completed = {p.stem:load(p) for p in (directory/'checkpoints').glob('*.json')}
    if any(k not in expected or r['question']!=expected[k] or set(r['arms'])!=set(ARM_NAMES)
           for k,r in completed.items()):
        raise ValueError('Unexpected/incomplete question checkpoint')
    started = time.monotonic()
    try:
        for item in inputs:
            if item['id'] in completed:
                continue
            families = {}
            for family in protocol['generation_families']:
                checkpoint = directory/family/'checkpoints'/(item['id']+'.json')
                if checkpoint.exists():
                    result = load(checkpoint)
                    if result['question'] != item['question'] or len(result['candidates'])!=3:
                        raise ValueError('Invalid family checkpoint')
                else:
                    begin = time.monotonic()
                    if family=='control_vanna':
                        result = vanna_candidates(vn, item, clients[family])
                    else:
                        result = run_question(item, rag if family=='ours_structured' else dense, clients[family])
                    result['wall_seconds'] = time.monotonic()-begin
                    dump(checkpoint, result)
                families[family] = result
            chosen = derive_arms(families, metadata)
            row = {'id':item['id'], 'question':item['question'],
                   'arms':{arm:record['sql'] for arm,record in chosen.items()},
                   'family_wall_seconds':{key:r['wall_seconds'] for key,r in families.items()}}
            dump(directory/'checkpoints'/(item['id']+'.json'), row)
            completed[item['id']] = row
            dump(directory/'status.json', {'state':'running', 'completed':len(completed), 'expected':len(inputs)})
            print(f'replicate {replicate}: {len(completed)}/{len(inputs)}', flush=True)
    except Exception as error:
        # Exception text from the provider is redacted by the existing client.
        dump(directory/'status.json', {'state':'incomplete_no_score', 'completed':len(completed),
             'expected':len(inputs), 'error_type':type(error).__name__, 'wall_seconds_this_session':time.monotonic()-started})
        raise
    for arm in ARM_NAMES:
        freeze(directory/(arm+'.prediction.json'), {r['id']:completed[r['id']]['arms'][arm] for r in inputs})
    dump(directory/'status.json', {'state':'inference_complete_unscored', 'completed':len(inputs),
         'expected':len(inputs), 'wall_seconds_this_session':time.monotonic()-started})
    verify_protocol()
    print('All arms complete. Run score_confirmatory.py after all registered replicates.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset')
    parser.add_argument('--replicate', type=int, choices=(1,2,3), default=1)
    parser.add_argument('--execute', action='store_true', help='Actually call the API on a registered eligible dataset')
    args = parser.parse_args()
    if args.execute:
        if not args.dataset:
            parser.error('--execute requires an independently registered dataset')
        inference(args.dataset, args.replicate)
    else:
        value = preflight(args.dataset)
        dump(ROOT/'READINESS.json', value)
        print(__import__('json').dumps(value, indent=2))
