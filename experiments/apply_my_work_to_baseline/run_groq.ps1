param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')]
    [string]$RunName = 'groq_quota_full_v1',
    [ValidateSet('current_quota','maximum')]
    [string]$Profile = 'current_quota',
    [ValidateSet('dev','test')]
    [string]$Split = 'test',
    [ValidateRange(0,1167)]
    [int]$Limit = 0,
    [string]$PrimaryVariant = ''
)
$ErrorActionPreference = 'Stop'
if ($Split -eq 'test' -and -not $PrimaryVariant) {
    throw 'Select PrimaryVariant on dev before test. Supply -PrimaryVariant explicitly.'
}
$taskPython = (Resolve-Path (Join-Path $PSScriptRoot '../../.venv/Scripts/python.exe')).Path
Push-Location $PSScriptRoot
try {
    $taskEffort = if ($Profile -eq 'maximum') { 'high' } else { 'none' }
    $taskSqlTokens = if ($Profile -eq 'maximum') { 16384 } else { 900 }
    $taskRewriteTokens = if ($Profile -eq 'maximum') { 2048 } else { 256 }
    $taskPrimaryArgs = @()
    if ($PrimaryVariant) { $taskPrimaryArgs = @('--primary-variant', $PrimaryVariant) }
    & $taskPython -X utf8 -B run.py --run-name $RunName --split $Split --limit $Limit `
        --reasoning-effort $taskEffort --sql-tokens $taskSqlTokens --rewrite-tokens $taskRewriteTokens @taskPrimaryArgs
    $taskRunExit = $LASTEXITCODE
    & $taskPython -X utf8 -B evaluate.py --run-name $RunName
    if ($LASTEXITCODE -ne 0) { throw 'Scoring failed; inference checkpoints are retained.' }
    if ($taskRunExit -eq 2) {
        Write-Warning 'API quota/service blocked the run. Read status.json; repeat this command to resume.'
    } elseif ($taskRunExit -ne 0) {
        throw "Inference failed (exit=$taskRunExit); checkpoints retained."
    }
} finally {
    Pop-Location
}
