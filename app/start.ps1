param([switch]$NoBrowser, [switch]$Check)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run setup.ps1 before starting the application.' }
$launchArguments = @('tools\launch.py', '--config', (Join-Path $PSScriptRoot 'config.json'))
if ($NoBrowser) { $launchArguments += '--no-browser' }
if ($Check) { $launchArguments += '--check' }
& $pythonPath @launchArguments
exit $LASTEXITCODE
