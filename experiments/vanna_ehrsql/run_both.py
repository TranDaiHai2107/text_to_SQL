"""Round-robin train/test inference; score only AFTER model calls have stopped."""
import argparse
from argparse import Namespace
import itertools
from benchmark import ROOT, load, dump, run_path
from bridge import shared
from run import RunState, add_gef


def finish_reports(states, model, blocked):
    from score import score
    reports = {state.args.split:score(state.directory) for state in states}
    summary = {'model':model, 'provider':'groq', 'primary_variant':'vanna',
               'dev_used':False, 'blocked_reason':blocked,
               'scope':'Train is in-sample with self retrieval; only full test can be compared with the paper.',
               'splits':{split:{'run':state.args.run_name, 'completed':reports[split]['completed_questions'],
                   'expected':len(state.selected), 'full':reports[split]['full_benchmark_complete'],
                   'scope':reports[split]['evaluation_scope'],
                   'variants':{name:{'scores':m['scores'], 'answerable_ex':m['answerable_ex'],
                                     'vsr_all_questions':m['vsr_all_questions']}
                               for name,m in reports[split].get('variants', {}).items()},
                   'api_usage':reports[split].get('api_usage', {})}
                   for state in states for split in [state.args.split]}}
    dump(ROOT/'LATEST_RESULTS.json', summary)
    lines = ['# Kết quả Vanna trên train và test', '', f'Model: `{model}` qua Groq. Primary: `vanna`. Không dùng dev.', '',
             '**Chỉ điểm full test mới được đối chiếu với paper. Điểm train có self-retrieval, không phải đánh giá độc lập.**', '']
    for split, info in summary['splits'].items():
        lines += [f'## {split}: {info["completed"]}/{info["expected"]} câu', '',
                  'Trạng thái: '+('đủ toàn bộ tập.' if info['full'] else '**PARTIAL — chưa phải kết quả cuối cùng.**'), '']
        for name,m in info['variants'].items():
            scores = ', '.join(f'{key}={value:.4f}' for key,value in m['scores'].items())
            ex = 'N/A' if m['answerable_ex'] is None else f'{m["answerable_ex"]:.4f}'
            lines.append(f'- `{name}`: {scores}; EX={ex}; VSR={m["vsr_all_questions"]:.4f}.')
        if not info['variants']:
            lines.append('Chưa có prediction hoàn tất để chấm.')
        lines += ['', f'Chi tiết: `runs/{info["run"]}/evaluation.json`.', '']
    if blocked:
        lines += ['## Hạn mức/dịch vụ', '', blocked, '', 'Checkpoint và API cache được giữ. Không tự đổi model hoặc tính câu chưa chạy thành null.', '']
    (ROOT/'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    status = load(ROOT/'STATUS.json')
    status.update(state='blocked_by_api' if blocked else 'completed_train_and_test', model_selected=True,
                  model=model, scores_available=any(info['completed'] for info in summary['splits'].values()),
                  full_benchmark_run=all(info['full'] for info in summary['splits'].values()),
                  inference_started=True, latest_results='LATEST_RESULTS.json')
    # Includes cached/earlier successes in the same run, not fake test transports.
    status['model_api_calls'] = sum(report.get('all_successful_api_calls',0) for report in reports.values())
    dump(ROOT/'STATUS.json', status)
    return summary


def infer_interleaved(states, clients, vn, generate, blocked_type):
    headers = {}
    try:
        for pair in itertools.zip_longest(*(state.pending() for state in states)):
            for state,item in zip(states, pair):
                if item is None:
                    continue
                vn.transport = clients[state.args.split]
                vn.transport.headers = headers
                row = add_gef(generate(vn, item))
                headers = vn.transport.headers
                state.append(row)
    except blocked_type as error:
        print(str(error), flush=True)
        return str(error)
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-prefix', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--sql-tokens', type=int, default=900)
    args = parser.parse_args()
    if not 64 <= args.sql_tokens <= 16384:
        parser.error('Invalid SQL output token budget')
    run_path(args.run_prefix+'_train')
    run_path(args.run_prefix+'_test')
    from vanna_adapter import make_vanna, assert_index, generate
    vn = make_vanna(ROOT/'indexes/chroma')
    index = assert_index(vn, ROOT/'indexes/chroma')
    states = [RunState(Namespace(run_name=args.run_prefix+'_'+split, split=split, model=args.model,
                    primary_variant='vanna', examples=4, limit=0, sql_tokens=args.sql_tokens, reasoning_effort='none'), index)
              for split in ['test', 'train']]
    transport = shared('model_client')
    clients = {state.args.split:transport.ModelClient(state.directory, args.model, 'none', args.sql_tokens, 256) for state in states}
    for state in states:
        state.status('running')
    top = load(ROOT/'STATUS.json')
    top.update(state='running_train_and_test', model_selected=True, model=args.model, inference_started=True,
               active_runs={state.args.split:state.args.run_name for state in states})
    dump(ROOT/'STATUS.json', top)
    # Share pacing headers across both transports; there is one account/quota.
    blocked = infer_interleaved(states, clients, vn, generate, transport.RunBlocked)
    # No additional model calls occur after loading gold for scoring.
    for state in states:
        state.status('blocked_by_api' if blocked else 'complete', reason=blocked)
    assert_index(vn, ROOT/'indexes/chroma')
    finish_reports(states, args.model, blocked)
    return 2 if blocked else 0


if __name__ == '__main__':
    raise SystemExit(main())
