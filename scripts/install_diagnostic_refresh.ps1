param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference='Stop'
$configPath=(Resolve-Path -LiteralPath $Config).Path
$root=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$cfg=Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$pilot=Get-Content -LiteralPath $cfg.pilot_config -Raw | ConvertFrom-Json
$entry=Join-Path $root 'scripts/refresh_live_diagnostics.py'
& $pilot.python $entry --config $configPath --check
if ($LASTEXITCODE -ne 0) { throw 'Refresh source/config verification failed; no task installed.' }
$name='Argus-Diagnostic-Refresh'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Existing task requires review; nothing replaced.' }
$end=[DateTimeOffset]::Parse('2026-11-17T00:00:00+08:00')
$now=[DateTimeOffset]::UtcNow.ToOffset([TimeSpan]::FromHours(8))
if ($now -ge $end) { throw 'Refresh period expired.' }
$start=[DateTimeOffset]::Parse($now.ToString('yyyy-MM-dd') + 'T08:25:00+08:00')
if ($start -le $now) { $start=$start.AddDays(1) }
$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function EscapeXml([string]$value) { [Security.SecurityElement]::Escape($value) }
$exe=EscapeXml $pilot.pythonw;$working=EscapeXml $root
$arguments=EscapeXml ('"' + $entry + '" --config "' + $configPath + '"')
$startText=$start.ToString('yyyy-MM-ddTHH:mm:sszzz');$endText=$end.ToString('yyyy-MM-ddTHH:mm:sszzz')
$xml=@"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus local read-only diagnostic refresh. No provider calls or activation. Finite pilot expiry.</Description></RegistrationInfo>
<Triggers><CalendarTrigger><StartBoundary>$startText</StartBoundary><EndBoundary>$endText</EndBoundary><Enabled>true</Enabled><ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay></CalendarTrigger></Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT20M</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$exe</Command><Arguments>$arguments</Arguments><WorkingDirectory>$working</WorkingDirectory></Exec></Actions>
</Task>
"@
[IO.File]::WriteAllText((Join-Path $cfg.state_dir 'task.xml'),$xml,[Text.Encoding]::Unicode)
Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
Get-ScheduledTask -TaskName $name | Select-Object TaskName,State
