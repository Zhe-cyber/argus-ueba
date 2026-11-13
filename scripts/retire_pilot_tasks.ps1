# Disables the old pilot collector/actor tasks (owner runs). Never touches Argus-Pilot-Backend.
# Run this BEFORE install_ops_tasks.ps1 (which refuses while Argus-Pilot-Collect is enabled): only one
# process may drain the SQS queue.
# Dry-run by default; -Apply to disable. Disabling lets a running tick finish (no Stop, so no
# half-done claims). Tasks are not unregistered; data and ledgers are untouched.
# Usage: powershell -ExecutionPolicy Bypass -File scripts\retire_pilot_tasks.ps1 [-Apply]
param([switch]$Apply)
$ErrorActionPreference = 'Stop'
$keep = @('Argus-Pilot-Backend')
$exact = @('Argus-Pilot-Collect', 'Argus-GitHub-Machine-Pilot')
$all = @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object { $_.TaskName -like 'Argus-*' })
$targets = @($all | Where-Object {
    ($exact -contains $_.TaskName -or $_.TaskName -like '*Machine-Pilot*' -or $_.TaskName -like '*Cloudflare*') -and ($keep -notcontains $_.TaskName)
})
foreach ($name in $exact) {
    if (-not ($all | Where-Object { $_.TaskName -eq $name })) { "not installed: $name" }
}
foreach ($task in $targets) {
    "retire: $($task.TaskName) (state $($task.State))"
    if ($Apply -and $task.State -ne 'Disabled') {
        Disable-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath | Out-Null
        "  disabled"
    }
}
foreach ($task in ($all | Where-Object { $targets -notcontains $_ })) { "left alone: $($task.TaskName) (state $($task.State))" }
if (-not $Apply) { 'Dry run: nothing changed. Re-run with -Apply.' }
