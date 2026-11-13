param([Parameter(Mandatory=$true)][string]$Config)
$ErrorActionPreference = 'Stop'
$cfgFile = (Resolve-Path -LiteralPath $Config).Path
$cfg = Get-Content -LiteralPath $cfgFile -Raw | ConvertFrom-Json
$name = 'Argus-Pilot-AE-Shadow'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw 'Task exists; inspect before replacement.' }
$entry = Join-Path $PSScriptRoot 'cloud_ae_shadow.py'
$console = Join-Path (Split-Path $cfg.pythonw) 'python.exe'
& $console $entry tick --config $cfgFile
if ($LASTEXITCODE -ne 0) { throw 'Real shadow inference failed; no task installed.' }
$end = '2026-11-14T16:00:00Z'
if ([DateTimeOffset]::UtcNow -ge [DateTimeOffset]::Parse($end)) { throw 'Pilot expired.' }
$start = [DateTimeOffset]::UtcNow.AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
function XmlEscape([string]$value) { return [Security.SecurityElement]::Escape($value) }
$exe = XmlEscape $cfg.pythonw
$arguments = XmlEscape ('"' + $entry + '" tick --config "' + $cfgFile + '"')
$working = XmlEscape (Split-Path $PSScriptRoot)
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus read-only local AWS AE shadow inference. No provider calls or validated risk tiers.</Description></RegistrationInfo>
<Triggers><TimeTrigger><Repetition><Interval>PT30M</Interval><Duration>P28D</Duration><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>$start</StartBoundary><EndBoundary>$end</EndBoundary><Enabled>true</Enabled></TimeTrigger></Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT10M</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$exe</Command><Arguments>$arguments</Arguments><WorkingDirectory>$working</WorkingDirectory></Exec></Actions>
</Task>
"@
[IO.File]::WriteAllText((Join-Path $cfg.output_dir 'task.xml'), $xml, [Text.Encoding]::Unicode)
Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
Start-ScheduledTask -TaskName $name
Get-ScheduledTask -TaskName $name | Select-Object TaskName,State
