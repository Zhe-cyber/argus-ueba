param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$configPath = (Resolve-Path -LiteralPath $Config).Path
$check = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$pilot = Get-Content -LiteralPath $check.pilot_config -Raw | ConvertFrom-Json
$taskName = 'Argus-Pilot-Daily-Check'
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'Task already exists; inspect before replacement.'
}
$end = [DateTimeOffset]::Parse('2026-11-17T00:00:00+08:00')
if ([DateTimeOffset]::UtcNow -ge $end) { throw 'Pilot expired.' }
$entry = Join-Path $pilot.source_root 'scripts/daily_pilot_check.py'
& $pilot.python $entry --config $configPath
if ($LASTEXITCODE -ne 0) { throw 'First read-only check failed; no task installed.' }
$myNow = [DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
$daily = [DateTimeOffset]::Parse($myNow.ToString('yyyy-MM-dd') + 'T08:15:00+08:00')
if ($daily -le $myNow) { $daily = $daily.AddDays(1) }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function XmlEscape([string]$value) { return [Security.SecurityElement]::Escape($value) }
$startText = $daily.ToString('yyyy-MM-ddTHH:mm:sszzz')
$logonStart = $myNow.ToString('yyyy-MM-ddTHH:mm:sszzz')
$endText = $end.ToString('yyyy-MM-ddTHH:mm:sszzz')
$exe = XmlEscape $pilot.pythonw
$working = XmlEscape $pilot.source_root
$arguments = XmlEscape ('"' + $entry + '" --config "' + $configPath + '"')
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus read-only daily pilot coverage. No provider calls or scoring. Expires 17 November MY.</Description></RegistrationInfo>
<Triggers>
<CalendarTrigger><StartBoundary>$startText</StartBoundary><EndBoundary>$endText</EndBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger>
<LogonTrigger><StartBoundary>$logonStart</StartBoundary><EndBoundary>$endText</EndBoundary><Enabled>true</Enabled><UserId>$sid</UserId></LogonTrigger>
</Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT5M</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$exe</Command><Arguments>$arguments</Arguments><WorkingDirectory>$working</WorkingDirectory></Exec></Actions>
</Task>
"@
$xmlPath = Join-Path $check.output_dir 'task.xml'
[IO.File]::WriteAllText($xmlPath, $xml, [Text.Encoding]::Unicode)
Register-ScheduledTask -TaskName $taskName -Xml $xml | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
