# L10 live autoencoder v2: one real training run. Python refuses before 12 Nov 2026 MYT has closed.
#   (a) builds the account-day dataset from the pilot events DB opened read-only (?mode=ro), days <= 12 Nov MYT
#   (b) trains into a fresh folder data\live\live-ae\bundle-v2-<MYT stamp> (git-ignored)
#   (c) prints the manifest summary, model sha256 (manifest) and weights sha256
#   (d) only with -DemoDb: backfills ml_scores on that marked SQLite workspace copy (workspace-copy.json, not_live: true)
# v1 history: backend\live_ae_v1.py and bundle-20261113T003343 are kept unchanged.
param([string]$DemoDb = '')
$ErrorActionPreference = 'Stop'
$env:DATABASE_URL = 'sqlite-local'
$python = 'C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe'
$events = 'C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\connected\events.db'
$root = Split-Path -Parent $PSScriptRoot
$stamp = (Get-Date).ToUniversalTime().AddHours(8).ToString('yyyyMMddTHHmmss')
$bundle = Join-Path $root ('data\live\live-ae\bundle-v2-' + $stamp)
Push-Location $root
try {
    & $python -m backend.live_ae train --events-db $events --out $bundle
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($DemoDb) { & $python -m backend.live_ae backfill --bundle $bundle --db $DemoDb }
    exit $LASTEXITCODE
} finally { Pop-Location }
