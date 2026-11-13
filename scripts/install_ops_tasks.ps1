# INTERIM scheduler for post-pilot collection (owner runs). Dry-run by default; -Apply to register.
# The supervisor (install_supervisor_task.ps1) is the single scheduler once installed; it removes these tasks.
#   Argus-Ops-Collect   every 5 minutes: ops_collect.py tick (per-provider intervals inside)
#   Argus-Ops-Personas  every 5 minutes: ops_personas.py tick (independent of fetches, so a slow fetch cannot
#                       make a persona miss its window)
#   Argus-Ops-Backend   at logon: ops_collect.py serve (ingest API on the configured loopback port)
# -Apply refuses until the old pilot collection has drained (task disabled and idle, no pilot tick/collect_live
# process; waits up to 10 minutes): run retire_pilot_tasks.ps1 -Apply first. Nothing is started here. Refuses to replace existing task names.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\install_ops_tasks.ps1 -Config data\live\ops\ops.json [-Apply]
param([Parameter(Mandatory=$true)][string]$Config, [string]$Python, [switch]$Apply)
$ErrorActionPreference = 'Stop'
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cfgFile = (Resolve-Path -LiteralPath $Config).Path
$cfg = Get-Content -LiteralPath $cfgFile -Raw | ConvertFrom-Json
if (-not $Python) { $Python = $cfg.supervisor.python }
if (-not $Python -or -not (Test-Path -LiteralPath $Python)) { throw 'Give -Python or set supervisor.python in the config (path to python.exe).' }
$pythonw = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw 'pythonw.exe not found next to python.exe.' }

# 1. One SQS consumer: the old pilot collection must be retired AND drained (scripts\ops_cutover_check.py decides):
#    Argus-Pilot-Collect disabled and not Running, and no process running local_pilot.py ... tick or collect_live.
#    -Apply waits up to 10 minutes (poll every 15 s), then refuses. Order: retire -> drain -> final snapshot/init -> install.
function Get-CutoverState {
    $t = Get-ScheduledTask -TaskName 'Argus-Pilot-Collect' -ErrorAction SilentlyContinue
    $procs = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine } |
        ForEach-Object { @{ pid = $_.ProcessId; command_line = $_.CommandLine } })
    $task = if ($t) { @{ state = [string]$t.State; enabled = [bool]$t.Settings.Enabled } } else { $null }
    return (ConvertTo-Json -InputObject @{ task = $task; processes = $procs } -Depth 4 -Compress)
}
function Test-Drained {
    $out = Get-CutoverState | & $Python (Join-Path $root 'scripts\ops_cutover_check.py')
    return @{ ok = ($LASTEXITCODE -eq 0); text = ($out -join '; ') }
}
'cutover check: Argus-Pilot-Collect disabled and not Running; no process running local_pilot.py tick or collect_live'
$check = Test-Drained
if ($Apply) {
    $deadline = (Get-Date).AddMinutes(10)
    while (-not $check.ok -and (Get-Date) -lt $deadline) {
        "waiting for drain: $($check.text)"
        Start-Sleep -Seconds 15
        $check = Test-Drained
    }
    if (-not $check.ok) {
        "REFUSED: the old pilot collection has not drained after 10 minutes: $($check.text)"
        'Two collectors would split the SQS queue. Run scripts\retire_pilot_tasks.ps1 -Apply, let the running tick finish, then retry.'
        exit 1
    }
}
"cutover check now: $($check.text)$(if (-not $Apply) { ' (dry run: -Apply waits up to 10 minutes for this, then refuses)' })"

# 2. Config check (prints whether the Cloudflare machine-lab app is among the collected apps).
& $Python (Join-Path $root 'scripts\ops_collect.py') check --config $cfgFile
if ($LASTEXITCODE -ne 0) { throw 'Config check failed; nothing registered.' }

# 3. GitHub CLI sign-in under this (the tasks') identity. Output is not shown: it can name the account.
$gh = if ($cfg.providers.github.gh_path) { $cfg.providers.github.gh_path } else { (Get-Command gh -ErrorAction SilentlyContinue).Source }
if ($cfg.providers.github.enabled) {
    if (-not $gh) { 'gh auth status: gh not found (GitHub collection will fail)' }
    else {
        & $gh auth status --hostname github.com *> $null
        "gh auth status: $(if ($LASTEXITCODE -eq 0) { 'signed in' } else { 'NOT signed in (exit ' + $LASTEXITCODE + '); run gh auth login' })"
    }
}

$store = [IO.Path]::GetFullPath((Join-Path $root $cfg.live_state_dir))
if ([IO.Path]::IsPathRooted($cfg.live_state_dir)) { $store = [IO.Path]::GetFullPath($cfg.live_state_dir) }
"event store written by the ops backend: $store\events.db  (the workspace mirror must read this same file)"

$names = @('Argus-Ops-Collect', 'Argus-Ops-Personas', 'Argus-Ops-Backend')
foreach ($name in $names) {
    if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) { throw "Task $name already exists; inspect it before replacing." }
}
function X([string]$v) { return [Security.SecurityElement]::Escape($v) }
$sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$start = [DateTimeOffset]::UtcNow.AddMinutes(1).ToString("yyyy-MM-ddTHH:mm:ss'Z'")
$cfgArg = ' --config "' + $cfgFile + '"'
$every5 = "<TimeTrigger><Repetition><Interval>PT5M</Interval><StopAtDurationEnd>false</StopAtDurationEnd></Repetition><StartBoundary>$start</StartBoundary><Enabled>true</Enabled></TimeTrigger>"
$tasks = @{
    'Argus-Ops-Collect'  = @{ Trigger = $every5; Action = ('"' + (Join-Path $root 'scripts\ops_collect.py') + '" tick' + $cfgArg); Limit = 'PT15M'; Network = 'true' }
    'Argus-Ops-Personas' = @{ Trigger = $every5; Action = ('"' + (Join-Path $root 'scripts\ops_personas.py') + '" tick' + $cfgArg); Limit = 'PT15M'; Network = 'true' }
    'Argus-Ops-Backend'  = @{ Trigger = "<LogonTrigger><StartBoundary>$start</StartBoundary><Enabled>true</Enabled><UserId>$sid</UserId></LogonTrigger>"
                              Action = ('"' + (Join-Path $root 'scripts\ops_collect.py') + '" serve' + $cfgArg); Limit = 'PT0S'; Network = 'false' }
}
foreach ($name in $names) {
    $t = $tasks[$name]
    $xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
<RegistrationInfo><Description>Argus operational collection (post-pilot, interim until the supervisor). No credentials stored in the task.</Description></RegistrationInfo>
<Triggers>$($t.Trigger)</Triggers>
<Principals><Principal id="Owner"><UserId>$sid</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
<Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>$($t.Network)</RunOnlyIfNetworkAvailable><Enabled>true</Enabled><Hidden>true</Hidden><WakeToRun>false</WakeToRun><ExecutionTimeLimit>$($t.Limit)</ExecutionTimeLimit></Settings>
<Actions Context="Owner"><Exec><Command>$(X $pythonw)</Command><Arguments>$(X $t.Action)</Arguments><WorkingDirectory>$(X $root)</WorkingDirectory></Exec></Actions>
</Task>
"@
    "Task $name"
    "  run: $pythonw $($t.Action)"
    if ($Apply) {
        Register-ScheduledTask -TaskName $name -Xml $xml | Out-Null
        '  registered (not started)'
    }
}
if (-not $Apply) { 'Dry run: nothing registered. Re-run with -Apply.' }
else { 'Start the backend after init:  Start-ScheduledTask -TaskName Argus-Ops-Backend' }
