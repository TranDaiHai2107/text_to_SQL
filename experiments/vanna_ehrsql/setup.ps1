$ErrorActionPreference = 'Stop'
$taskPython = (Resolve-Path (Join-Path $PSScriptRoot '../../.venv/Scripts/python.exe')).Path
$taskVendor = Join-Path $PSScriptRoot '.vendor'
& $taskPython -m pip install --no-deps --require-hashes --target $taskVendor -r (Join-Path $PSScriptRoot 'requirements-vendor.txt')
if ($LASTEXITCODE -ne 0) { throw 'Vanna installation failed.' }
& $taskPython -m pip install --no-deps --target $taskVendor -r (Join-Path $PSScriptRoot 'requirements-support.txt')
if ($LASTEXITCODE -ne 0) { throw 'Vanna support dependency installation failed.' }
Write-Output 'Installed isolated Vanna runtime. No model API was called.'
