param(
    [ValidateSet('author', 'official')]
    [string]$Scorer = 'official',
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')]
    [string]$RunName = ('replay_' + (Get-Date -Format 'yyyyMMdd_HHmmss')),
    [ValidateRange(1, 3600)]
    [int]$SqlTimeout = 30
)

# Explicit future execution only. Never invoked by container startup/build.
$ErrorActionPreference = 'Stop'
$taskRepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$experiments = @(
    'test_gpt_ft',
    'test_gpt_probgate_450',
    'test_gpt_probgate_450_gef',
    'test_gpt_probgate_425_gef'
)

Push-Location $taskRepoRoot
try {
    $taskRunsRoot = Join-Path $PSScriptRoot 'runs'
    $taskRunDirectory = Join-Path $taskRunsRoot $RunName
    if (Test-Path -LiteralPath $taskRunDirectory) {
        throw "Run directory exists; choose a new -RunName: $taskRunDirectory"
    }
    New-Item -ItemType Directory -Path $taskRunsRoot -Force | Out-Null
    & docker compose --profile baseline up -d --build --wait --wait-timeout 120 probgate-baseline
    if ($LASTEXITCODE -ne 0) { throw 'Baseline container is not ready.' }
    & docker compose exec -T probgate-baseline python reproduce.py preflight `
        --split test --sql-timeout $SqlTimeout --output "runs/$RunName/preflight.json"
    if ($LASTEXITCODE -ne 0) { throw 'Gold SQL preflight failed. Check preflight.json before scoring.' }
    foreach ($experiment in $experiments) {
        $resultDirectory = "runs/$RunName/$experiment"
        Write-Host "Replay: $experiment ($Scorer)"
        & docker compose exec -T probgate-baseline python reproduce.py postprocess `
            --experiment $experiment `
            --raw upstream/src/log_probability_final_test.json `
            --sql-timeout $SqlTimeout `
            --output "$resultDirectory/prediction.json"
        if ($LASTEXITCODE -ne 0) { throw "Postprocessing failed: $experiment" }
        & docker compose exec -T probgate-baseline python reproduce.py score `
            --split test --scorer $Scorer `
            --sql-timeout $SqlTimeout `
            --predictions "$resultDirectory/prediction.json" `
            --output "$resultDirectory/scores.json"
        if ($LASTEXITCODE -ne 0) { throw "Scoring failed: $experiment" }
    }
    & docker compose exec -T probgate-baseline python reproduce.py summarize `
        --run-dir "runs/$RunName" --scorer $Scorer
    if ($LASTEXITCODE -ne 0) { throw 'Comparison summary failed.' }
    Write-Host "Saved: baselines/probgate_ehrsql_2024/runs/$RunName"
}
finally {
    Pop-Location
}
