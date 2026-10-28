param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$cfgFile = (Resolve-Path -LiteralPath $Config).Path
$cfg = Get-Content -LiteralPath $cfgFile -Raw | ConvertFrom-Json
$entry = Join-Path $cfg.source_root 'scripts/local_pilot.py'
& $cfg.python $entry check --config $cfgFile
if ($LASTEXITCODE -ne 0) { throw 'Config validation failed.' }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$updates = @()
foreach ($mode in @('serve', 'tick')) {
    $name = if ($mode -eq 'serve') { 'Argus-Pilot-Backend' } else { 'Argus-Pilot-Collect' }
    $task = Get-ScheduledTask -TaskName $name
    $taskSid = if ($task.Principal.UserId -match '^S-1-') { $task.Principal.UserId } else { ([Security.Principal.NTAccount]::new($task.Principal.UserId)).Translate([Security.Principal.SecurityIdentifier]).Value }
    $expected = '"' + $entry + '" ' + $mode + ' --config "' + $cfgFile + '"'
    if ($task.State -ne 'Disabled' -or $task.Actions.Count -ne 1 -or
        $task.Actions[0].Execute -ne $cfg.pythonw -or $task.Actions[0].Arguments -ne $expected -or
        $task.Actions[0].WorkingDirectory -ne $cfg.source_root -or
        $taskSid -ne $sid -or $task.Principal.LogonType -ne 'Interactive' -or
        $task.Principal.RunLevel -ne 'Limited') { throw 'Owned task identity/state mismatch; nothing replaced.' }
    $original = Export-ScheduledTask -TaskName $name
    $backup = Join-Path $cfg.state_dir ($name + '-before-v2.xml')
    if (-not (Test-Path -LiteralPath $backup)) { [IO.File]::WriteAllText($backup, $original, [Text.Encoding]::Unicode) }
    [xml]$xml = $original
    foreach ($trigger in $xml.Task.Triggers.ChildNodes) {
        if (-not $trigger.EndBoundary) { throw 'Missing finite task expiry.' }
        $trigger.EndBoundary = '2026-11-14T16:00:00Z'
    }
    $updates += @{Name=$name; Xml=$xml.OuterXml}
}
# Both identities were checked before either mutation. Keep disabled until health checks.
foreach ($update in $updates) {
    Register-ScheduledTask -TaskName $update.Name -Xml $update.Xml -Force | Out-Null
    Disable-ScheduledTask -TaskName $update.Name | Out-Null
}
Get-ScheduledTask -TaskName 'Argus-Pilot-Backend','Argus-Pilot-Collect' | Select-Object TaskName,State
