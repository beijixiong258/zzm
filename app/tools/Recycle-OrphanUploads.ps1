param(
    [switch]$Apply,
    [ValidateRange(1, 3650)][int]$MinimumAgeDays = 7,
    [string]$Server = '127.0.0.1',
    [ValidateRange(1, 65535)][int]$Port = 3306,
    [string]$Database = 'aicademiya'
)
$ErrorActionPreference = 'Stop'
if (-not $env:MYSQL_USER -or -not $env:MYSQL_PASSWORD) {
    throw '请在当前 PowerShell 会话设置 MYSQL_USER 和 MYSQL_PASSWORD。'
}
$uploadRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\data-local\uploads'))
if ($env:AICADEMIYA_UPLOAD_DIR) { $uploadRoot = [IO.Path]::GetFullPath($env:AICADEMIYA_UPLOAD_DIR) }
if (-not (Test-Path -LiteralPath $uploadRoot -PathType Container)) { throw '上传目录不存在。' }
$uploadRoot = (Resolve-Path -LiteralPath $uploadRoot).Path.TrimEnd('\')
$uploadPrefix = $uploadRoot + '\'
$trashRoot = Join-Path $env:USERPROFILE 'Desktop\智能体回收站\垃圾桶\AIcademiya\orphan-uploads'
$connectionBuilder = [System.Data.Odbc.OdbcConnectionStringBuilder]::new()
$connectionBuilder.Driver = 'MySQL ODBC 8.0 Unicode Driver'
$connectionBuilder['Server'] = $Server
$connectionBuilder['Port'] = $Port
$connectionBuilder['Database'] = $Database
$connectionBuilder['Uid'] = $env:MYSQL_USER
$connectionBuilder['Pwd'] = $env:MYSQL_PASSWORD
$connectionBuilder['CHARSET'] = 'utf8mb4'
$connection = [System.Data.Odbc.OdbcConnection]::new($connectionBuilder.ConnectionString)
$cutoff = [DateTime]::UtcNow.AddDays(-$MinimumAgeDays)
try {
    $connection.Open()
    $references = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
    $query = $connection.CreateCommand()
    $query.CommandText = 'SELECT storage_path FROM course_material'
    $reader = $query.ExecuteReader()
    while ($reader.Read()) { [void]$references.Add([IO.Path]::GetFullPath($reader.GetString(0))) }
    $reader.Dispose()
    $query.Dispose()
    foreach ($file in Get-ChildItem -LiteralPath $uploadRoot -File) {
        $source = [IO.Path]::GetFullPath($file.FullName)
        if (-not $source.StartsWith($uploadPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw '文件路径超出上传目录。' }
        if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
        if ($file.LastWriteTimeUtc -ge $cutoff -or $references.Contains($source)) { continue }
        $action = '候选，尚未移动'
        if ($Apply) {
            $check = $connection.CreateCommand()
            $check.CommandText = 'SELECT COUNT(*) FROM course_material WHERE storage_path=?'
            [void]$check.Parameters.AddWithValue('path', $source)
            $referenced = [long]$check.ExecuteScalar()
            $check.Dispose()
            if ($referenced -gt 0) { continue }
            $destination = [IO.Path]::GetFullPath((Join-Path $trashRoot ($file.BaseName + '-' + [guid]::NewGuid().ToString('N') + $file.Extension)))
            if (-not $destination.StartsWith(([IO.Path]::GetFullPath($trashRoot).TrimEnd('\') + '\'), [StringComparison]::OrdinalIgnoreCase)) {
                throw '目标路径超出指定垃圾桶。'
            }
            New-Item -ItemType Directory -Path $trashRoot -Force | Out-Null
            Move-Item -LiteralPath $source -Destination $destination
            $action = '已移入垃圾桶'
        }
        [pscustomobject]@{ File = $source; Bytes = $file.Length; Result = $action }
    }
} finally {
    $connection.Dispose()
}