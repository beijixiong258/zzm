param([Parameter(Mandatory=$true)][string]$Source,[Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$app=$null;$doc=$null;$ownedPid=$null
$ext=[IO.Path]::GetExtension($Source).ToLowerInvariant()
$name=if($ext -eq '.pptx'){'POWERPNT'}else{'WINWORD'}
# Office automation can join an existing singleton: never touch a user's instance.
if(Get-Process -Name $name -ErrorAction SilentlyContinue){Write-Error "Office export refused: existing $name process; independent instance not assured.";exit 3}
Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class WindowPid { [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid); }'
try {
    $app=New-Object -ComObject $(if($ext -eq '.pptx'){'PowerPoint.Application'}else{'Word.Application'})
    $app.AutomationSecurity=3
    # Word Application does not expose HWND until a document window exists.
    # There were no pre-existing instances; require exactly one new process.
    $instances=@(Get-Process -Name $name -ErrorAction Stop)
    if($instances.Count -ne 1){throw 'Cannot unambiguously identify owned Office process'}
    [uint32]$officePid=$instances[0].Id
    $Source=[IO.Path]::GetFullPath($Source)
    $Destination=[IO.Path]::GetFullPath($Destination)
    $ownedPid=$officePid
    [IO.File]::WriteAllText($Destination+'.owned-pid.json', ('{"pid":'+$ownedPid+',"source":"Office COM export","process":"'+$name+'"}'))
    if($ext -eq '.pptx'){
        $doc=$app.Presentations.Open($Source,-1,0,0)
        $doc.SaveAs($Destination,32)
    }else{
        $app.Visible=$false
        $app.DisplayAlerts=0
        $app.Options.UpdateLinksAtOpen=$false
        $doc=$app.Documents.Open($Source,$false,$true,$false)
        $doc.ExportAsFixedFormat($Destination,17)
    }
    Write-Output "EXPORTED owned_pid=$ownedPid macro_security=3 read_only=true original_not_saved=true"
} finally {
    if($null -ne $doc){try{if($ext -eq '.pptx'){$doc.Saved=-1;$doc.Close()}else{$doc.Close(0)}}catch{Write-Warning $_};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($doc);$doc=$null}
    if($null -ne $app){try{$app.Quit()}catch{Write-Warning $_};[void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($app);$app=$null}
    [GC]::Collect();[GC]::WaitForPendingFinalizers()
    if($null -ne $ownedPid){
        $process=Get-Process -Id $ownedPid -ErrorAction SilentlyContinue
        if($process){if(-not $process.WaitForExit(8000)){if($process.ProcessName -eq $name){Stop-Process -Id $ownedPid -Force;Write-Output "CLOSED lingering owned_pid=$ownedPid"}}}
        Write-Output "OFFICE_CLEANUP_COMPLETE owned_pid=$ownedPid"
    }
}
