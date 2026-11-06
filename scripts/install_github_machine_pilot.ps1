$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskName = 'Argus-GitHub-Machine-Pilot'
$taskConfigPath = 'C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\pilot-local-v1\config.json'
$taskConfig = Get-Content -Raw -LiteralPath $taskConfigPath | ConvertFrom-Json
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) { throw 'Task already exists; inspect instead of overwriting.' }
$taskPython = $taskConfig.python
$taskHiddenPython = $taskConfig.pythonw
if (!(Test-Path -LiteralPath $taskHiddenPython) -or [IO.Path]::GetFileName($taskHiddenPython) -ne 'pythonw.exe') { throw 'Verified hidden Python required.' }
& $taskPython -c "import json; from pathlib import Path; from scripts import github_machine_pilot as p; p.validate(json.loads((p.state()/'pilot-config.json').read_bytes())); print('GitHub pilot source/scope pins verified')"
if ($LASTEXITCODE -ne 0) { throw 'Pilot validation failed.' }
$taskScript = Join-Path $PSScriptRoot 'github_machine_pilot.py'
$taskAction = New-ScheduledTaskAction -Execute $taskHiddenPython -Argument ('"' + $taskScript + '" tick') -WorkingDirectory $taskRoot
$taskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskEnd = [DateTimeOffset]::Parse('2026-11-15T00:00:00+08:00')
if ([DateTimeOffset]::Now -ge $taskEnd) { throw 'Pilot has expired.' }
$taskStart = (Get-Date).AddMinutes(1)
$taskDuration = $taskEnd.LocalDateTime - $taskStart
$taskRepeat = New-ScheduledTaskTrigger -Once -At $taskStart -RepetitionInterval (New-TimeSpan -Minutes 15) -RepetitionDuration $taskDuration
$taskLogin = New-ScheduledTaskTrigger -AtLogOn -User $taskUser
$taskRepeat.EndBoundary = '2026-11-15T00:00:00+08:00'
$taskLogin.EndBoundary = '2026-11-15T00:00:00+08:00'
$taskSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$taskPrincipal = New-ScheduledTaskPrincipal -UserId $taskUser -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger @($taskRepeat,$taskLogin) -Settings $taskSettings -Principal $taskPrincipal -Description 'Finite Argus one-bot controlled GitHub lab; writes 31 Oct-13 Nov only, reconciliation 14 Nov; no model activation.' | Out-Null
$taskReadback = Get-ScheduledTask -TaskName $taskName
if ($taskReadback.Actions.Count -ne 1 -or $taskReadback.Actions[0].Execute -ne $taskHiddenPython -or $taskReadback.Actions[0].Arguments -ne $taskAction.Arguments -or $taskReadback.Actions[0].WorkingDirectory -ne $taskRoot) { throw 'Task action readback differs; inspect before running.' }
Write-Output 'Installed Argus-GitHub-Machine-Pilot: every 15 minutes and at logon; finite expiry 15 Nov 00:00 MYT.'
