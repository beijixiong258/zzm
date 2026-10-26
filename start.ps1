param(
    [ValidateSet('backend', 'frontend', 'docker')]
    [string]$Component = 'backend',
    [switch]$Check,
    [switch]$NoBrowser,
    [switch]$NoDemo
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
if ($Component -in @('backend', 'docker') -and (Test-Path -LiteralPath '.env')) {
    foreach ($line in Get-Content -LiteralPath '.env') {
        if ($line -match '^\s*(AICADEMIYA_AI_(?:API_KEY|BASE_URL|MODEL))\s*=(.*)$') {
            $name = $Matches[1]
            $value = $Matches[2].Trim()
            if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
                $value = $value.Substring(1, $value.Length - 2)
            }
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}
switch ($Component) {
    'backend' {
        if ($NoDemo) { $env:AICADEMIYA_DEMO_ENABLED = 'false' }
        elseif ([string]::IsNullOrWhiteSpace($env:AICADEMIYA_DEMO_ENABLED)) { $env:AICADEMIYA_DEMO_ENABLED = 'false' }
        & mvn.cmd spring-boot:run
    }
    'frontend' {
        Push-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
        try { & npm.cmd run dev } finally { Pop-Location }
    }
    'docker' {
        $configuration = Get-Content -LiteralPath 'src\main\resources\application.yaml' -Raw
        $databaseSettings = @{
            MYSQL_USER = '(?m)^ {4}username:\s*(.+)$'
            MYSQL_PASSWORD = '(?m)^ {4}password:\s*(.+)$'
            MYSQL_ROOT_PASSWORD = '(?m)^ {2}root-password:\s*(.+)$'
        }
        foreach ($entry in $databaseSettings.GetEnumerator()) {
            $match = [regex]::Match($configuration, $entry.Value)
            if (-not $match.Success) { throw "application.yaml 缺少数据库配置：$($entry.Key)" }
            $value = $match.Groups[1].Value.Trim()
            if ($value.StartsWith("'") -and $value.EndsWith("'")) {
                $value = $value.Substring(1, $value.Length - 2).Replace("''", "'")
            } elseif ($value.StartsWith('"') -and $value.EndsWith('"')) {
                $value = ConvertFrom-Json -InputObject $value
            } else {
                $value = ($value -replace '\s+#.*$', '').Trim()
            }
            if ([string]::IsNullOrWhiteSpace($value)) { throw "application.yaml 数据库配置不能为空：$($entry.Key)" }
            [Environment]::SetEnvironmentVariable($entry.Key, $value, 'Process')
        }
        & docker compose up -d --build
    }
}
exit $LASTEXITCODE
