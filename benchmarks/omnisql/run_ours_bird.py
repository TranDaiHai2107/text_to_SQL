"""Run Ours (full-agentic pipeline) on BIRD dev with the baseline's pinned GPT snapshot.

Inputs per question: the natural-language question, BIRD's external-knowledge evidence and
the database (schema text = the baseline prompt's DDL). Gold SQL is never loaded into the
pipeline. Nothing is sent to the API without --execute and an explicit --max-usd cap.

Variants (ablation-friendly; the same code with Config switches):
  v6    link -> decompose -> 3 branches (direct || independent, then decomposed), technical
        repair, local result-fingerprint vote, LLM selector only on disagreement, verifier
        only when the chosen result is empty (default)
  lite  one full-schema candidate, a second independent one only if the first fails/empty
  full  every executed candidate verified + semantic repair, LLM selector over supported
  v8    baseline reasoning prompt as generator + Ours layers (values, few-shot, repair,
        value-only vote over greedy + 8 samples, tie selector); v8_no<layer> ablates one layer
  v9    v8 + plan-prompt generator (8 more samples), set-based vote, sampled selector only when
        no result group holds a majority; v9_no<part> ablates one part
  v7    v6 + 6 sampled direct candidates from one request (T=0.8), vote only among
        candidates returning values, LLM selector only when the top result groups tie
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import random
import sys
import threading
import time

from verify_assets import DATA, HERE, ROOT, verify

sys.path.insert(0, str(ROOT / 'src'))
from ehrqa.agentic.pipeline import Config, FullAgentic  # noqa: E402
from ehrqa.agentic.prompts import BIRD_VERSION  # noqa: E402
from ehrqa.agentic.retrieval import SequentialRAG  # noqa: E402
from ehrqa.bird.database import BirdDatabase  # noqa: E402
from ehrqa.bird.fewshot import TrainExamples  # noqa: E402
from ehrqa.bird.model import BudgetExceeded, ChatModel, SpendTracker  # noqa: E402
from ehrqa.bird.ours_v8 import OursV8, V8Config  # noqa: E402
from ehrqa.bird.ours_v9 import OursV9, V9Config  # noqa: E402

V8_VARIANTS = {'v8': {}, 'v8_novalues': {'values': False}, 'v8_nofewshot': {'fewshot': False},
               'v8_norepair': {'repair': False}, 'v8_noselect': {'select': False},
               'v8_novote': {'vote': False}}
V9_VARIANTS = {'v9': {}, 'v9_noplan': {'plan_samples': 0}, 'v9_noselect': {'select': False},
               'v9_multiset': {'set_vote': False}}

DEV = DATA / 'dev_20240627'
VALUE_INDEX = DATA / 'ours_value_index'
BASELINE = ROOT / 'results' / 'omnisql'


def config(variant: str, log_dir: Path) -> Config:
    return Config(profile='bird', log_dir=log_dir, run_version=f'{BIRD_VERSION}_{variant}',
                  fingerprint_selection=variant in ('v6', 'v7'), parallel_branches=True,
                  adaptive_single=variant == 'lite', extra_samples=6 if variant == 'v7' else 0,
                  value_vote=variant == 'v7', max_model_calls=32)


def select_rows(n: int, args) -> list[int]:
    if args.ids:
        return sorted({int(x) for x in Path(args.ids).read_text().split()})
    rows = list(range(n))
    if args.sample:
        rows = sorted(random.Random(args.seed).sample(rows, args.sample))
    return rows


def score_subset(out: Path, gold: list[dict], done: dict[int, dict], model: str) -> dict:
    """Author evaluator (num_cpus 4, timeout 60) on the completed rows; paired with baselines."""
    sys.path.insert(0, str(HERE / 'official' / 'train_and_evaluate'))
    import evaluate_bird
    rows = sorted(done)
    gold_file = out / 'bird_subset_gold.json'  # author code needs 'bird' in the gold path
    pred_file = out / 'subset_pred.json'
    gold_file.write_text(json.dumps([gold[i] for i in rows], ensure_ascii=False), encoding='utf-8')
    pred_file.write_text(json.dumps([{'pred_sqls': [done[i]['sql'] or '']} for i in rows], ensure_ascii=False),
                         encoding='utf-8')
    evaluate_bird.run_eval(str(gold_file), str(pred_file), str(DEV / 'dev_databases'), 'greedy_search', False,
                           num_cpus=4, timeout=60)
    ours = [r['correctness'] for r in evaluate_bird.evaluation_results]
    result = {'questions': len(rows), 'ours_correct': sum(ours), 'ours_ex': sum(ours) / len(rows)}
    for mode in ('greedy_search', 'major_voting'):
        path = BASELINE / model / f'{mode}_score_per_question.json'
        if path.exists():
            base = json.loads(path.read_text(encoding='utf-8'))
            paired = [base[i] for i in rows]
            result[f'baseline_{mode}_correct'] = sum(paired)
            result[f'ours_only_vs_{mode}'] = sum(o and not b for o, b in zip(ours, paired))
            result[f'{mode}_only'] = sum(b and not o for o, b in zip(ours, paired))
    result['per_question'] = dict(zip(rows, ours))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', choices=('v6', 'v7', 'lite', 'full', *V8_VARIANTS, *V9_VARIANTS), default='v6')
    parser.add_argument('--model', default='gpt-4o-mini-2024-07-18')
    parser.add_argument('--sample', type=int, help='seeded random subset of dev rows')
    parser.add_argument('--seed', type=int, default=20261119)
    parser.add_argument('--ids', help='file with dev row indices')
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--max-usd', type=float, default=0.0, help='spend cap for this invocation')
    parser.add_argument('--score', action='store_true', help='score completed rows with the author evaluator')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()

    verify()
    gold = json.loads((DEV / 'dev.json').read_text(encoding='utf-8'))
    prompts = json.loads((DATA / 'omnisql_dev_bird.json').read_text(encoding='utf-8'))
    # The pipeline receives only these fields; gold SQL ('SQL') is deliberately excluded.
    questions = [{'question': g['question'], 'evidence': g['evidence'], 'db_id': g['db_id']} for g in gold]
    out = (args.output_dir or ROOT / 'results' / 'omnisql' / 'ours' / args.model / args.variant).resolve()
    out.mkdir(parents=True, exist_ok=True)
    checkpoint = out / 'predictions.jsonl'
    done = {}
    if checkpoint.exists():
        for line in checkpoint.read_text(encoding='utf-8').splitlines():
            row = json.loads(line)
            done[row['row_index']] = row  # later lines (retries) replace earlier ones
    retry = {i for i, r in done.items() if r['status'] == 'error'}
    targets = [i for i in select_rows(len(gold), args) if i not in done or i in retry]
    print(json.dumps({'variant': args.variant, 'model': args.model, 'output': str(out),
                      'completed': len(done), 'to_run': len(targets), 'execute': args.execute,
                      'max_usd': args.max_usd}, indent=2), flush=True)

    if args.execute and targets:
        if args.max_usd <= 0:
            raise SystemExit('--execute needs an explicit --max-usd cap')
        from dotenv import load_dotenv
        load_dotenv(ROOT / '.env', override=False)
        if not os.getenv('OPENAI_API_KEY'):
            raise SystemExit('OPENAI_API_KEY is missing')
        tracker = SpendTracker(args.max_usd)
        model = ChatModel(args.model, tracker)
        examples = TrainExamples(DATA / 'bird_train.json', gold)
        databases, db_lock, write_lock = {}, threading.Lock(), threading.Lock()

        def database(index: int) -> BirdDatabase:
            db_id = questions[index]['db_id']
            with db_lock:
                if db_id not in databases:
                    databases[db_id] = BirdDatabase(DEV / 'dev_databases' / db_id / f'{db_id}.sqlite',
                                                    prompts[index]['input_seq'], value_index_dir=VALUE_INDEX)
                return databases[db_id]

        stop = threading.Event()

        def run(index: int) -> None:
            if stop.is_set():
                return
            q = questions[index]
            db = database(index)
            started = time.monotonic()
            try:
                if args.variant in V9_VARIANTS:
                    pipeline = OursV9(db, model, examples=examples, config=V9Config(**V9_VARIANTS[args.variant]),
                                      log_dir=out / 'traces')
                    output = pipeline.run(q['question'], q['evidence'], prompts[index]['input_seq'],
                                          query_id=str(index))
                elif args.variant in V8_VARIANTS:
                    pipeline = OursV8(db, model, examples=examples, config=V8Config(**V8_VARIANTS[args.variant]),
                                      log_dir=out / 'traces')
                    output = pipeline.run(q['question'], q['evidence'], prompts[index]['input_seq'],
                                          query_id=str(index))
                else:
                    pipeline = FullAgentic(db, SequentialRAG(db, examples), model, config(args.variant, out / 'traces'))
                    output = pipeline.run(q['question'], evidence=q['evidence'], query_id=str(index))
            except BudgetExceeded:
                stop.set()
                return
            except Exception as error:  # API/transport failure: record a retryable error row
                output = {'status': 'error', 'sql': '', 'reason': f'{type(error).__name__}: {error}'[:300],
                          'model_calls': 0, 'fallbacks': [], 'selected': None, 'candidates': [], 'trace': [],
                          'prompt_version': args.variant, 'trace_path': None}
            responses = [e for e in output['trace'] if e['stage'] == 'model.response']
            if 'BudgetExceeded' in output['reason']:
                stop.set()
                return
            row = {'row_index': index, 'db_id': q['db_id'], 'status': output['status'], 'sql': output['sql'],
                   'reason': output['reason'], 'model_calls': output['model_calls'],
                   'fallbacks': output['fallbacks'], 'selected': (output['selected'] or {}).get('id'),
                   'candidates': [{'id': c['id'], 'status': c['status'], 'sql': c.get('sql')}
                                  for c in output['candidates']],
                   'usd': sum(e.get('usd', 0) for e in responses),
                   'prompt_tokens': sum(e['usage']['prompt_tokens'] for e in responses),
                   'completion_tokens': sum(e['usage']['completion_tokens'] for e in responses),
                   'latency_seconds': round(time.monotonic() - started, 2),
                   'prompt_version': output['prompt_version'], 'trace_path': output['trace_path']}
            with write_lock:
                with checkpoint.open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, ensure_ascii=False, default=str) + '\n')
                done[index] = row
                print(f"[{len(done)}] row {index} {row['status']} calls={row['model_calls']} "
                      f"${tracker.spent:.3f} {row['latency_seconds']}s", flush=True)

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for future in as_completed([pool.submit(run, i) for i in targets]):
                future.result()
        print(json.dumps({'spent_usd_this_run': round(tracker.spent, 4), 'stopped_by_cap': stop.is_set()}),
              flush=True)

    selected = set(select_rows(len(gold), args))
    finished = {i: r for i, r in done.items() if i in selected and r['status'] != 'error'}
    if len(finished) == len(gold):
        final = [{'row_index': i, 'pred_sqls': [finished[i]['sql'] or '']} for i in range(len(gold))]
        (out / 'greedy_search.json').write_text(json.dumps(final, ensure_ascii=False, indent=2) + '\n',
                                                 encoding='utf-8')
        print(f'Full prediction file: {out / "greedy_search.json"} (score with score_bird.py)')
    if args.score and finished:
        result = score_subset(out, gold, finished, args.model)
        rows = list(finished.values())
        result.update(usd=round(sum(r['usd'] for r in rows), 4),
                      mean_calls=round(sum(r['model_calls'] for r in rows) / len(rows), 2),
                      mean_latency_s=round(sum(r['latency_seconds'] for r in rows) / len(rows), 1),
                      statuses={s: sum(r['status'] == s for r in rows) for s in {r['status'] for r in rows}})
        (out / 'subset_score.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({k: v for k, v in result.items() if k != 'per_question'}, indent=2))


if __name__ == '__main__':
    main()
