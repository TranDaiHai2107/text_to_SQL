"""Paired evaluation of the update_baseline rungs / v10 variants on Ours v9's stored candidates.

Every variant reuses v9's generated SQL (g, s1..s8, p1..p8) instead of sampling again, so all rungs
share one candidate pool and differ only by the change under test (no run-to-run sampling noise).
API calls are made only for what v9 never produced:
  repair         when the feedback differs from v9's (an unstored literal is reported); otherwise v9's
                 stored repair is replayed (same prompt, temperature 0)
  select         v9's stored selector votes are replayed when the options are the same groups;
                 otherwise a new sampled call
  select_pair / merge / generate_dc_samples   always new calls
Gold SQL never enters a prompt.

  python v10_replay.py check                       # ub5_select must reproduce v9 exactly, with no API call
  python v10_replay.py run NAME [NAME ...] --max-usd 5
  NAME: an update_baseline rung (ub0_baseline .. ub7_pairwise) or a v10 variant (v10_merge, v10_early, v10_dc)
Output: results/omnisql/ours/gpt-4o-mini-2024-07-18/replay/<NAME>/predictions.jsonl (+ greedy_search.json)
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import sys
import threading

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ehrqa.bird.database import BirdDatabase  # noqa: E402
from ehrqa.bird.fewshot import TrainExamples  # noqa: E402
from ehrqa.bird.model import BudgetExceeded, ChatModel, SpendTracker  # noqa: E402
from ehrqa.bird.ours_v10 import OursV10, V10Config  # noqa: E402
from ehrqa.bird.update_baseline import NAMES as RUNGS, ladder_config  # noqa: E402

DATA = ROOT / 'data/benchmarks/bird'
DEV = DATA / 'dev_20240627'
RUNS = ROOT / 'results/omnisql/ours/gpt-4o-mini-2024-07-18'
OUT = RUNS / 'replay'
V10_VARIANTS = {'v10_merge': {'resolve': 'merge'}, 'v10_early': {'early_stop_share': 0.9},
                'v10_dc': {'plan_samples': 4, 'dc_samples': 4}}


def config(name: str) -> V10Config:
    return ladder_config(name) if name in RUNGS else V10Config(**V10_VARIANTS[name])


def fence(sql: str) -> str:
    return '```sql\n' + (sql or '') + '\n```'


class NoAPI:
    def complete_text(self, *a, **k):
        raise RuntimeError('API call during check')

    sample_text = complete_text


class ReplayModel:
    """Serves v9's stored generations; anything else goes to the real model."""

    def __init__(self, stored: dict, real, events: dict):
        self.stored, self.real, self.events, self.api_calls = stored, real, events, 0

    def complete_text(self, stage, messages, tokens):
        if stage == 'generate':
            return {'content': fence(self.stored.get('g', '')), 'usage': {}, 'usd': 0.0, 'replayed': True}
        if stage == 'repair' and self.events.get('replay_repair'):
            return {'content': fence(self.stored.get('gr') or self.stored.get('g', '')), 'usage': {}, 'usd': 0.0,
                    'replayed': True}
        self.api_calls += 1
        return self.real.complete_text(stage, messages, tokens)

    def sample_text(self, stage, messages, tokens, *, n, temperature):
        prefix = {'generate_samples': 's', 'generate_plan_samples': 'p'}.get(stage)
        if prefix:
            texts = [fence(self.stored.get(f'{prefix}{k}', '')) for k in range(1, n + 1)]
            return {'contents': texts, 'usage': {}, 'usd': 0.0, 'replayed': True}
        self.api_calls += 1
        return self.real.sample_text(stage, messages, tokens, n=n, temperature=temperature)


class ReplayV10(OursV10):
    def __init__(self, *a, v9_select=None, replay_model=None, **k):
        super().__init__(*a, **k)
        self.v9_select, self.replay_model = v9_select, replay_model

    def _complete(self, trace, stage, prompt, *, n=1, temperature=0.0):
        if stage == 'repair':  # v9 asked the same thing iff no unstored literal is reported
            self.replay_model.events['replay_repair'] = 'is not stored in that column' not in prompt
        return super()._complete(trace, stage, prompt, n=n, temperature=temperature)

    def _listwise(self, trace, prompt, groups, total, candidates):
        reps = [g[0] for g in groups[:self.config.select_groups]]
        stored = self.v9_select
        if stored and stored['options'] == [c['id'] for c in reps] and stored.get('choice'):
            trace.emit('ours.select', resolver='listwise', options=stored['options'], votes=stored['votes'],
                       choice=stored['choice'], replayed=True)
            return reps[int(stored['choice']) - 1], f'_selected_{len(reps)}', 0
        if stored and stored['options'] == [c['id'] for c in reps]:
            return reps[0], '_select_fallback', 0
        return super()._listwise(trace, prompt, groups, total, candidates)


def v9_state():
    rows = {}
    for line in (RUNS / 'v9/predictions.jsonl').read_text(encoding='utf-8').splitlines():
        r = json.loads(line)
        rows[r['row_index']] = r
    out = {}
    for i, r in rows.items():
        stored = {c['id']: c['sql'] or '' for c in r['candidates']}
        select = None
        for line in open(r['trace_path'], encoding='utf-8'):
            e = json.loads(line)
            if e['stage'] == 'ours.select':
                select = {'options': e['options'], 'votes': e['votes'], 'choice': e['choice']}
        out[i] = (stored, select, r['sql'])
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('cmd', choices=('check', 'run'))
    parser.add_argument('names', nargs='*')
    parser.add_argument('--max-usd', type=float, default=0.0)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--rows', type=int, help='only the first N questions (smoke test; no greedy_search.json)')
    args = parser.parse_args()
    if not sys.flags.utf8_mode:
        raise SystemExit('set PYTHONUTF8=1')
    names = ['ub5_select'] if args.cmd == 'check' else args.names
    for name in names:
        config(name)  # fail fast on unknown names
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
    state = v9_state()
    examples = TrainExamples(DATA / 'bird_train.json', gold)
    databases, lock = {}, threading.Lock()

    def database(i):
        db_id = gold[i]['db_id']
        with lock:
            if db_id not in databases:
                databases[db_id] = BirdDatabase(DEV / 'dev_databases' / db_id / f'{db_id}.sqlite',
                                                prompts[i]['input_seq'], value_index_dir=DATA / 'ours_value_index')
            return databases[db_id]

    if args.cmd == 'run':
        if args.max_usd <= 0:
            raise SystemExit('run needs an explicit --max-usd cap')
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
        if not os.getenv('OPENAI_API_KEY'):
            raise SystemExit('OPENAI_API_KEY is missing')
        tracker = SpendTracker(args.max_usd)
        real = ChatModel('gpt-4o-mini-2024-07-18', tracker)
    else:
        tracker, real = None, NoAPI()

    for name in names:
        cfg = config(name)
        out = OUT / name
        out.mkdir(parents=True, exist_ok=True)
        checkpoint = out / 'predictions.jsonl'
        done = {}
        if checkpoint.exists() and args.cmd == 'run':
            for line in checkpoint.read_text(encoding='utf-8').splitlines():
                r = json.loads(line)
                done[r['row_index']] = r
        todo = [i for i in range(args.rows or len(gold)) if i not in done or done[i]['status'] == 'error']
        write = threading.Lock()
        stop = threading.Event()

        def one(i):
            if stop.is_set():
                return
            stored, select, v9_sql = state[i]
            rm = ReplayModel(stored, real, {})
            pipe = ReplayV10(database(i), rm, examples=examples, config=cfg, log_dir=None,
                             v9_select=select, replay_model=rm)
            try:
                o = pipe.run(gold[i]['question'], gold[i]['evidence'], prompts[i]['input_seq'], query_id=str(i))
            except BudgetExceeded:
                stop.set()
                return
            except Exception as error:
                if args.cmd == 'check':
                    raise
                o = {'status': 'error', 'sql': '', 'reason': f'{type(error).__name__}: {error}'[:300],
                     'model_calls': 0, 'candidates': [], 'trace': []}
            if 'BudgetExceeded' in o['reason']:
                stop.set()
                return
            responses = [e for e in o['trace'] if e['stage'] == 'model.response' and not e.get('replayed')]
            row = {'row_index': i, 'status': o['status'], 'sql': o['sql'], 'reason': o['reason'],
                   'api_calls': rm.api_calls, 'usd': sum(e.get('usd', 0) for e in responses),
                   'same_as_v9': o['sql'] == v9_sql,
                   'candidates': [{'id': c['id'], 'status': c['status'], 'sql': c.get('sql')}
                                  for c in o['candidates']],
                   'events': [{k: v for k, v in e.items() if k not in ('run_id', 'utc', 'elapsed_s', 'output')}
                              for e in o['trace'] if e['stage'] in ('ours.repair', 'ours.select', 'ours.merge',
                                                                     'ours.early_stop', 'ours.vote')]}
            with write:
                with checkpoint.open('a', encoding='utf-8') as f:
                    f.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
                done[i] = row

        if args.cmd == 'check' and checkpoint.exists():
            checkpoint.unlink()
        with ThreadPoolExecutor(args.workers) as pool:
            for future in as_completed([pool.submit(one, i) for i in todo]):
                future.result()
        rows = [done[i] for i in sorted(done)]
        summary = {'name': name, 'rows': len(rows), 'errors': sum(r['status'] == 'error' for r in rows),
                   'api_calls': sum(r['api_calls'] for r in rows), 'usd': round(sum(r['usd'] for r in rows), 4),
                   'same_as_v9': sum(r['same_as_v9'] for r in rows), 'stopped_by_cap': stop.is_set()}
        if len(rows) == len(gold) and not summary['errors']:
            (out / 'greedy_search.json').write_text(json.dumps(
                [{'row_index': i, 'pred_sqls': [done[i]['sql'] or '']} for i in range(len(gold))]), encoding='utf-8')
        (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
        print(json.dumps(summary), flush=True)
        if args.cmd == 'check' and (summary['same_as_v9'] != len(rows) or summary['api_calls']):
            raise SystemExit('check failed: replay does not reproduce v9')
        if stop.is_set():
            raise SystemExit('stopped by the spend cap')


if __name__ == '__main__':
    main()
