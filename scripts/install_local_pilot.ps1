param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$cfgFile = (Resolve-Path -LiteralPath $Config).Path
$cfg = Get-Content -LiteralPath $cfgFile -Raw | ConvertFrom-Json
$root = [IO.Path]::GetFullPath($cfg.source_root)
$entry = Join-Path $root 'scripts/local_pilot.py'
& $cfg.python $entry check --config $cfgFile
if ($LASTEXITCODE -ne 0) { throw 'Pilot config check failed; no tasks created.' }
$taskNames = @('Argus-Pilot-Backend', 'Argus-Pilot-Collect')
foreach ($name in $taskNames) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
        throw 'An owned-name task already exists; inspect it before replacement.'
    }
}
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$start = [DateTimeOffset]::UtcNow.AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$end = '2026-11-24T16:00:00Z'
if ([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($end)) { throw 'Pilot period has expired.' }
function XmlEscape([string]$value) { return [Security.SecurityElement]::Escape($value) }
foreach ($mode in @('serve', 'tick')) {
    $name = if ($mode -eq 'serve') { 'Argus-Pilot-Backend' } else { 'Argus-Pilot-Collect' }
    $trigger = if ($mode -eq 'serve') {
        "<LogonTrigger><StartBoundary>$start</StartBoundary><EndBoundary>$end</EndBoundary><Enabled>true</Enabled><UserId>$sid</UserId></LogonTrigger>"
    } else {
        "<TimeTrigger><Repetition><Interval>PT5M</Interval><Duration>P28D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>$start</StartBoundary><EndBoundary>$end</EndBoundary><Enabled>true</Enabled></TimeTrigger>"
    }
    $limit = if ($mode -eq 'serve') { 'P28D' } else { 'PT15M' }
    $network = if ($mode -eq 'serve') { 'false' } else { 'true' }
    $arguments = XmlEscape ('"' + $entry + '" ' + $mode + ' --config "' + $cfgFile + '"')
    $exe = XmlEscape $cfg.pythonw
    $working = XmlEscape $root
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus controlled local pilot. Source-pinned, finite, no model activation. Runtime state is local; no Windows password stored.</Description></RegistrationInfo>
<Triggers>$trigger</Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>$network</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>$limit</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$exe</Command><Arguments>$arguments</Arguments><WorkingDirectory>$working</WorkingDirectory></Exec></Actions>
</Task>
"@
    $xmlPath = Join-Path $cfg.state_dir ($name + '.xml')
    [IO.File]::WriteAllText($xmlPath, $xml, [Text.Encoding]::Unicode)
    Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
}
Start-ScheduledTask -TaskName 'Argus-Pilot-Backend'
Start-ScheduledTask -TaskName 'Argus-Pilot-Collect'
Get-ScheduledTask -TaskName $taskNames | Select-Object TaskName,State
