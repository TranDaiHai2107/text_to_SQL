"""Tuning-only experiment: add BIRD column/value descriptions to the schema DDL, 8 samples T=0.8."""
import csv, io, json, re, sys, threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1])); sys.argv = sys.argv[:1] + sys.argv[1:]
from v9_lab import context, chat, tuning_ids, load_jsonl, LAB, DEV, ROOT
from ehrqa.bird.ours_v8 import enrich_prompt, parse_sql
from ehrqa.bird.ours_v9 import V9Config

def read_csv(path):
    raw = path.read_bytes()
    for enc in ('utf-8-sig', 'cp1252', 'latin-1'):
        try: return list(csv.DictReader(io.StringIO(raw.decode(enc))))
        except UnicodeDecodeError: pass

norm = lambda s: re.sub(r'[\s`"]', '', (s or '')).lower()

def descriptions(db_id):
    out = {}
    for f in (DEV/'dev_databases'/db_id/'database_description').glob('*.csv'):
        for r in read_csv(f):
            col = (r.get('original_column_name') or '').strip()
            d = ' '.join((r.get('column_description') or '').split())
            v = ' '.join((r.get('value_description') or '').split())
            parts = []
            if d and norm(d) != norm(col): parts.append('description: ' + d)
            if v: parts.append('values: ' + v[:300])
            if parts: out[(norm(f.stem), norm(col))] = '; '.join(parts)
    return out

LINE = re.compile(r'^(\s+)(`[^`]+`|"[^"]+"|\w+)\s')
def add_descriptions(input_seq, db_id):
    desc, table, lines = descriptions(db_id), None, []
    for line in input_seq.split('\n'):
        m = re.match(r'CREATE TABLE\s+(`[^`]+`|"[^"]+"|\w+)', line)
        if m: table = norm(m.group(1))
        c = LINE.match(line)
        if table and c and not line.strip().upper().startswith(('PRIMARY', 'FOREIGN', 'CONSTRAINT')):
            d = desc.get((table, norm(c.group(2))))
            if d: line = line.rstrip() + (' -- ' if '--' not in line else ' | ') + d
        if line.startswith(');'): table = None
        lines.append(line)
    return '\n'.join(lines)

if __name__ == '__main__':
    gold, database, _ = context()
    prompts = json.loads((ROOT/'data/benchmarks/bird/omnisql_dev_bird.json').read_text(encoding='utf-8'))
    from ehrqa.bird.fewshot import TrainExamples
    from v9_lab import DATA
    examples = TrainExamples(DATA/'bird_train.json', gold)
    def prompt(i):
        text = gold[i]['question'] + ' ' + (gold[i]['evidence'] or '')
        values = database(i).catalog_search(text, [])[:V9Config().max_value_hints]
        return enrich_prompt(add_descriptions(prompts[i]['input_seq'], gold[i]['db_id']), values, examples(text)['items'])
    if sys.argv[1:2] == ['show']:
        print(prompt(int(sys.argv[2]) if len(sys.argv) > 2 else 7)[:3000]); sys.exit()
    out = LAB/'desc_samples_n8.jsonl'; done = load_jsonl(out)
    model, tracker = chat(1.5); lock = threading.Lock()
    def run(i):
        r = model.sample_text('generate_samples', [{'role': 'user', 'content': prompt(i)}], 2048, n=8, temperature=0.8)
        with lock, out.open('a', encoding='utf-8') as f:
            f.write(json.dumps({'row_index': i, 'sqls': [parse_sql(t) for t in r['contents']], 'usd': r['usd']}, ensure_ascii=False) + '\n')
    with ThreadPoolExecutor(8) as p: list(p.map(run, [i for i in tuning_ids() if i not in done]))
    print('usd', round(tracker.spent, 4))
