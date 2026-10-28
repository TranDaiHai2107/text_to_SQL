param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')]
    [string]$RunName = 'vanna_qwen_20261027_v1_test'
)
$ErrorActionPreference = 'Stop'
$taskPython = (Resolve-Path (Join-Path $PSScriptRoot '../../.venv/Scripts/python.exe')).Path
$taskWorkspace = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
Push-Location $taskWorkspace
try {
    & $taskPython -X utf8 -B experiments/vanna_ehrsql/run.py --run-name $RunName --split test `
        --model qwen/qwen3.8-27b --primary-variant vanna --examples 4 --limit 0 --sql-tokens 900 --reasoning-effort none
    $taskRunExit = $LASTEXITCODE
    if ($taskRunExit -notin @(0,2)) { throw "Vanna inference exited with code $taskRunExit. Checkpoints are retained." }
    & $taskPython -X utf8 -B experiments/vanna_ehrsql/score.py --run-name $RunName
    if ($LASTEXITCODE -ne 0) { throw 'Official scoring failed; raw predictions retained.' }
    $taskReportScript = @'
import json, sys
from pathlib import Path
root=Path('experiments/vanna_ehrsql')
name=sys.argv[1]
directory=root/'runs'/name
report=json.loads((directory/'evaluation.json').read_text(encoding='utf-8'))
execution=json.loads((directory/'status.json').read_text(encoding='utf-8'))
summary={'model':'qwen/qwen3.8-27b','provider':'groq','primary_variant':'vanna',
         'train_role':'knowledge_base_only_5124_examples','dev_used':False,'test_run':name,
         'completed_test_questions':report['completed_questions'],'expected_test_questions':1167,
         'full_test_complete':report['full_benchmark_complete'],'state':execution['state'],
         'blocked_reason':execution.get('reason'),'api_usage':report.get('api_usage',{}),
         'variants':{k:{'scores':v['scores'],'answerable_ex':v['answerable_ex'],
                        'vsr_all_questions':v['vsr_all_questions']} for k,v in report.get('variants',{}).items()}}
(root/'LATEST_RESULTS.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
lines=['# Kết quả Vanna — chỉ đánh giá test','',
       'Train: 5.124 ví dụ trong knowledge base; không chấm điểm train. Không sử dụng dev.',
       'Model: `qwen/qwen3.8-27b` qua Groq. Primary cố định: `vanna`.','',
       f"Đã hoàn tất {summary['completed_test_questions']}/1.167 câu test.",'',
       'Trạng thái: '+('FULL TEST.' if summary['full_test_complete'] else '**PARTIAL — không phải kết quả cuối và chưa được so với full paper.**'),'']
for variant,metrics in summary['variants'].items():
    numbers=', '.join(f'{key}={value:.4f}' for key,value in metrics['scores'].items())
    ex='N/A' if metrics['answerable_ex'] is None else f"{metrics['answerable_ex']:.4f}"
    lines.append(f"- `{variant}`: {numbers}; EX={ex}; VSR={metrics['vsr_all_questions']:.4f}.")
lines += ['', 'RSN dùng N của số câu đã chấm; khi PARTIAL, không đối chiếu trực tiếp RSN với paper.',
          f"Chi tiết: `runs/{name}/evaluation.json`.",'']
if summary['blocked_reason']:
    lines += ['## API/quota','',str(summary['blocked_reason']),'','Checkpoint và API cache được giữ; không tự đổi model hoặc padding các câu chưa chạy thành null.','']
(root/'RESULTS.md').write_text('\n'.join(lines),encoding='utf-8')
status=json.loads((root/'STATUS.json').read_text(encoding='utf-8'))
status.update(state=execution['state'], model='qwen/qwen3.8-27b', model_selected=True,
              train_role='knowledge_base_only', active_runs={'test':name},
              completed_test_questions=report['completed_questions'], full_benchmark_run=report['full_benchmark_complete'],
              scores_available=bool(report.get('variants')), latest_results='LATEST_RESULTS.json',
              successful_test_model_calls=report.get('all_successful_api_calls',0))
(root/'STATUS.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
print('Saved test-only RESULTS.md and LATEST_RESULTS.json.')
'@
    $taskReportScript | & $taskPython -X utf8 -B - $RunName
    if ($LASTEXITCODE -ne 0) { throw 'Result summary failed.' }
    if ($taskRunExit -eq 2) { Write-Warning 'API/quota blocked inference; partial scores and checkpoints are saved.' }
} finally {
    Pop-Location
}
