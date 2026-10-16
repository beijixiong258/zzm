$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
}
if (-not (Test-Path -LiteralPath 'config.json')) {
    & '.venv\Scripts\python.exe' -c "import json; from pathlib import Path; from backend.aicademiya.deployment_config import DEFAULTS; Path('config.json').write_text(json.dumps(DEFAULTS, ensure_ascii=False, indent=2), encoding='utf-8')"
    if ($LASTEXITCODE -ne 0) { throw 'Configuration file creation failed.' }
}
& '.venv\Scripts\python.exe' -m pip install -r 'backend\requirements.txt'
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
try {
    npm ci --include=dev --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
& '.venv\Scripts\python.exe' 'tools\launch.py' --check
if ($LASTEXITCODE -ne 0) { throw 'Startup prerequisites are not ready.' }
Write-Output 'Ready. Run start.ps1 or double-click start.cmd.'
