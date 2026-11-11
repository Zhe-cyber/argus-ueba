# Starts the Argus demo (API 8017, UI 3013, live mirror). Safe to run again: skips what is already up.
# Usage:  powershell -ExecutionPolicy Bypass -File start_demo.ps1 [-Rehearsal]
# Read-only towards the live collection: the mirror opens the source database with mode=ro.
param([switch]$Rehearsal)
$ErrorActionPreference = 'Stop'
$wt     = $PSScriptRoot
$py     = 'C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe'
$node   = (Get-Command node).Source
$source = 'C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\connected\events.db'

function Listening($port) { [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) }

function Start-Site($root, $apiPort, $uiPort) {
    if (-not (Listening $apiPort)) {
        $env:DATABASE_URL = 'sqlite-local'
        $env:ARGUS_WORKSPACE_COPY_DB = "$root\preview.db"
        $env:ARGUS_WORKSPACE_UI_ORIGIN = "http://127.0.0.1:$uiPort"
        Start-Process -FilePath $py -WorkingDirectory $wt -WindowStyle Hidden `
            -ArgumentList @('-m','uvicorn','workspace_next.app:create_app','--factory','--host','127.0.0.1','--port',"$apiPort") `
            -RedirectStandardOutput "$root\api.stdout.log" -RedirectStandardError "$root\api.stderr.log"
        "API  $apiPort started"
    } else { "API  $apiPort already running" }
    if (-not (Listening $uiPort)) {
        Start-Process -FilePath $node -WorkingDirectory "$root\frontend" -WindowStyle Hidden `
            -ArgumentList @('node_modules/next/dist/bin/next','start','-H','127.0.0.1','-p',"$uiPort") `
            -RedirectStandardOutput "$root\ui.stdout.log" -RedirectStandardError "$root\ui.stderr.log"
        "UI   $uiPort started"
    } else { "UI   $uiPort already running" }
}

$preview = "$wt\data\live\live-v1-preview"
Start-Site $preview 8017 3013

$mirror = Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match 'workspace_next\.live_mirror' }
if (-not $mirror) {
    $env:DATABASE_URL = 'sqlite-local'
    Start-Process -FilePath $py -WorkingDirectory $wt -WindowStyle Hidden `
        -ArgumentList @('-m','workspace_next.live_mirror','--source',$source,'--dest',"$preview\preview.db",'--interval','60') `
        -RedirectStandardOutput "$preview\mirror.stdout.log" -RedirectStandardError "$preview\mirror.stderr.log"
    "Mirror started (every 60 s)"
} else { "Mirror already running" }

if ($Rehearsal) { Start-Site "$wt\data\live\live-v1-rehearsal" 8018 3014 }

"Open http://127.0.0.1:3013" + $(if ($Rehearsal) { '  and  http://127.0.0.1:3014 (simulated scenario)' })
