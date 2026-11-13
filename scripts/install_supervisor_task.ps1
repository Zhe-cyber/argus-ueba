# Registers the Argus supervisor as a logon task (owner runs). Dry-run by default; -Apply to act.
# One scheduler only: with -Apply this UNREGISTERS the interim Argus-Ops-Collect, Argus-Ops-Personas and
# Argus-Ops-Backend tasks (the supervisor runs those components itself). Refuses while the old pilot
# collector (Argus-Pilot-Collect) is enabled. Paths come from the config, not from this script.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install_supervisor_task.ps1 -Config data\live\ops\ops.json [-Apply]
param([Parameter(Mandatory=$true)][string]$Config, [switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cfgFile = (Resolve-Path -LiteralPath $Config).Path
$cfg = Get-Content -LiteralPath $cfgFile -Raw | ConvertFrom-Json
$Python = $cfg.supervisor.python
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) { throw 'Set supervisor.python in the config (path to python.exe).' }
$pythonw = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'

$old = Get-ScheduledTask -TaskName 'Argus-Pilot-Collect' -ErrorAction SilentlyContinue
if ($old -and $old.State -ne 'Disabled') {
    "REFUSED: Argus-Pilot-Collect is still enabled. Run scripts\retire_pilot_tasks.ps1 -Apply first."
    exit 1
}
& $Python (Join-Path $root 'scripts\ops_collect.py') check --config $cfgFile
if ($LASTEXITCODE -ne 0) { throw 'Config check failed; nothing changed.' }
if ($cfg.supervisor.frontend_dir) { "web UI: $($cfg.supervisor.frontend_dir) must be built with NEXT_PUBLIC_API_URL=http://127.0.0.1:$($cfg.supervisor.workspace_api_port)" }

$name = 'Argus-Supervisor'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw "Task $name already exists; inspect it before replacing." }
$interim = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { @('Argus-Ops-Collect', 'Argus-Ops-Personas', 'Argus-Ops-Backend') -contains $_.TaskName })
foreach ($t in $interim) {
    "remove interim task: $($t.TaskName) (state $($t.State))"
    if ($Apply) {
        Stop-ScheduledTask -TaskName $t.TaskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $t.TaskName -Confirm:$false
        '  removed'
    }
}
function X([string]$v) { return [Security.SecurityElement]::Escape($v) }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$start = [DateTimeOffset]::UtcNow.AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$arguments = '"' + (Join-Path $root 'scripts\argus_supervisor.py') + '" --config "' + $cfgFile + '"'
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus supervisor: single scheduler for ingest, collection, personas, mirror, workspace API and UI.</Description></RegistrationInfo>
<Triggers><LogonTrigger><StartBoundary>$start</StartBoundary><Enabled>true</Enabled><UserId>$sid</UserId></LogonTrigger></Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT0S</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$(X $pythonw)</Command><Arguments>$(X $arguments)</Arguments><WorkingDirectory>$(X $root)</WorkingDirectory></Exec></Actions>
</Task>
"@
"Task $name (at logon)"
"  run: $pythonw $arguments"
if ($Apply) {
    Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
    '  registered. Start now with:  Start-ScheduledTask -TaskName Argus-Supervisor'
} else { 'Dry run: nothing changed. Re-run with -Apply.' }
