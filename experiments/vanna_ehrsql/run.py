"""Explicit inference entry point; uses real Vanna, no proposed-system RAG."""
import argparse
import copy
import hashlib
import json
import time
from benchmark import ROOT, BASELINE, OUR_SYSTEM, load, dump, questions, run_path, sha


def add_gef(row):
    record = copy.deepcopy(row['variants']['vanna'])
    execution = record['execution']
    record['gef_filtered'] = (not execution['valid'] or execution['empty']) and not execution['abstained']
    if record['gef_filtered']:
        record['sql'] = 'null'
    row['variants']['vanna_gef'] = record
    return row


def definition(args, index):
    return {
        'system':'Vanna AI', 'pipeline':'legacy_rag_sql_in_vanna_2.0.2',
        'provider':'groq', 'model':args.model, 'split':args.split,
        'modes':['vanna', 'vanna_gef'], 'primary_variant':args.primary_variant or 'vanna',
        'primary_metric':'RS10', 'temperature':0, 'seed':42,
        'reasoning_effort':args.reasoning_effort,
        'sql_tokens':args.sql_tokens, 'limit':args.limit, 'retrieved_examples':args.examples,
        'retrieved_ddl':17, 'retrieved_documentation':1,
        'allow_llm_to_see_data':False, 'fine_tuning':False, 'auto_training':False,
        'schema_validation_used_for_feedback':False, 'index':index,
        'scorer':'official', 'gold_test_access_during_inference':False,
        'evaluation_scope':'in_sample_train_with_self_retrieval' if args.split=='train' else 'held_out_'+args.split,
        'selection_protocol':'fixed_before_test_no_dev_tuning',
        'code_sha256':{p.name:sha(p) for p in ROOT.glob('*.py')},
        'shared_code_sha256':{p:sha(OUR_SYSTEM/p) for p in ['model_client.py', 'settings.py', 'sql_runtime.py', 'evaluate.py']},
        'vanna_source_sha256':{p:sha(ROOT/'.vendor/vanna'/p) for p in ['legacy/base/base.py', 'legacy/chromadb/chromadb_vector.py']},
    }


class RunState:
    """One split's immutable config and durable, resumable inference records."""
    def __init__(self, args, index):
        self.args = args
        self.directory = run_path(args.run_name)
        self.config = definition(args, index)
        self.directory.mkdir(parents=True, exist_ok=True)
        config_path = self.directory/'config.json'
        if config_path.exists():
            if load(config_path) != self.config:
                raise ValueError('Code/config changed: choose a new run name')
        else:
            dump(config_path, self.config)
        self.selected = sorted(questions(args.split), key=lambda r:hashlib.sha256(('apply_work_v1:'+r['id']).encode()).hexdigest())
        if args.limit:
            self.selected = self.selected[:args.limit]
        self.path = self.directory/'records.jsonl'
        records = [json.loads(line) for line in self.path.read_text(encoding='utf-8').splitlines()] if self.path.exists() else []
        if len(records) != len({r['id'] for r in records}):
            raise ValueError('Duplicate completed ID')
        self.done = {r['id']:r for r in records}
        expected = {r['id']:r['question'] for r in self.selected}
        if any(key not in expected or expected[key] != row['question'] for key,row in self.done.items()):
            raise ValueError('Unexpected completed ID/question')

    def pending(self):
        return (item for item in self.selected if item['id'] not in self.done)

    def status(self, state, **details):
        dump(self.directory/'status.json', {'state':state, 'split':self.args.split,
             'completed_questions':len(self.done), 'requested_questions':len(self.selected),
             'updated_at_unix':time.time(), **details})

    def append(self, row):
        if row['id'] in self.done:
            raise ValueError('Refusing duplicate prediction')
        with self.path.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(row, ensure_ascii=False)+'\n')
            handle.flush()
        self.done[row['id']] = row
        self.status('running')
        print(f"Vanna {self.args.split} completed {len(self.done)}/{len(self.selected)}: {row['id']}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-name', required=True)
    parser.add_argument('--split', choices=['train', 'dev', 'test'], default='dev')
    parser.add_argument('--model', required=True, help='Actual Groq model ID; never a Vanna model name')
    parser.add_argument('--primary-variant', choices=['vanna', 'vanna_gef'])
    parser.add_argument('--examples', type=int, default=4)
    parser.add_argument('--limit', type=int, default=0)
    parser.add_argument('--sql-tokens', type=int, default=900)
    parser.add_argument('--reasoning-effort', choices=['none', 'low', 'medium', 'high'], default='none')
    args = parser.parse_args()
    if args.limit < 0 or not 1 <= args.examples <= 20 or not 64 <= args.sql_tokens <= 16384:
        parser.error('Invalid question/example/token limit')
    if args.split == 'test' and args.primary_variant is None:
        parser.error('Fix --primary-variant before test; dev tuning is optional')
    from vanna_adapter import make_vanna, assert_index, generate
    vn = make_vanna(ROOT/'indexes/chroma', examples=args.examples)
    index = assert_index(vn, ROOT/'indexes/chroma')
    state = RunState(args, index)
    from bridge import shared
    transport = shared('model_client')
    vn.transport = transport.ModelClient(state.directory, args.model, args.reasoning_effort, args.sql_tokens, 256)
    state.status('running')
    try:
        for item in state.pending():
            state.append(add_gef(generate(vn, item)))
    except transport.RunBlocked as error:
        state.status('blocked_by_api', reason=str(error))
        return 2
    # generate_sql, unlike ask(auto_train=True), never writes eval Q/SQL to RAG.
    assert_index(vn, ROOT/'indexes/chroma')
    state.status('complete')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
