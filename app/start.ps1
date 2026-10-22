param(
    [ValidateSet('backend', 'frontend', 'docker')]
    [string]$Component = 'backend',
    [switch]$Check,
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if ($Check) {
    foreach ($name in @('pwsh', 'java', 'mvn', 'node', 'npm', 'docker')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        [pscustomobject]@{ Component = $name; Available = [bool]$command; Path = $command.Source }
    }
    exit 0
}
switch ($Component) {
    'backend' {
        Push-Location -LiteralPath (Join-Path $PSScriptRoot 'server')
        try { & mvn.cmd spring-boot:run } finally { Pop-Location }
    }
    'frontend' {
        Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
        try { & npm.cmd run dev } finally { Pop-Location }
    }
    'docker' { & docker compose up -d --build }
}
exit $LASTEXITCODE
