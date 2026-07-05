# codex_review.ps1 - Cross-vendor peer review: send a diff to Codex (OpenAI).
#
# Usage:
#   .\scripts\codex_review.ps1                    # review working-tree diff vs master
#   .\scripts\codex_review.ps1 -Branch w2-skew    # review a branch's diff vs master
#   .\scripts\codex_review.ps1 -Security          # security-focused pass (use for auth/ingest)
#
# Behaviour:
#   - If the `codex` CLI is on PATH: runs the review non-interactively and saves the
#     verdict to reviews\<name>-codex.md.
#   - If not: writes a self-contained review packet to reviews\<name>-packet.md for
#     manual pasting into the Codex app. Enable automation with:
#         npm i -g @openai/codex ; codex login

param(
    [string]$Branch = "",
    [switch]$Security
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

New-Item -ItemType Directory -Force reviews | Out-Null

if ($Branch) {
    $diff = git diff "master...$Branch"
    $name = $Branch
} else {
    $diff = git diff master
    $name = "worktree-" + (Get-Date -Format "yyyyMMdd-HHmm")
}

if (-not $diff) { Write-Host "No diff to review."; exit 0 }

$focus = if ($Security) {
    "You are doing a SECURITY review. Focus on: authentication/authorization gaps, injection (SQL/command/path), unvalidated input reaching stores or scorers, secrets handling, baseline-poisoning vectors via /ingest, tenant isolation."
} else {
    "You are doing a CORRECTNESS review. Focus on: logic bugs, train/serve consistency for ML features, API contract breaks (frontend expects existing field names), error handling, off-by-one/boundary issues."
}

$context = @"
Project: Argus - UEBA platform (FastAPI backend, Next.js frontend, PyTorch autoencoders).
Invariants that must not break:
- Feature contracts frozen: 71-dim CERT vector, 12-dim cloud vector (order matters).
- lgbm_score/wa_score fields are deprecated but kept for API back-compat.
- Tests run against SQLite (DATABASE_URL unset/non-postgres), prod uses Neon Postgres.
$focus
Report ONLY findings you are confident in, ranked by severity, each with file:line,
a one-line defect statement, and a concrete failure scenario. End with a verdict:
APPROVE or REQUEST_CHANGES.
"@

$diffFile = "reviews\$name.diff"
$diff | Out-File -Encoding utf8 $diffFile

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($codex) {
    Write-Host "Running Codex review on $name..."
    $prompt = "$context`n`nReview this diff:`n`n$diff"
    # PS 5.1: never redirect a native exe's stderr (2>&1) - progress lines on
    # stderr become ErrorRecords and abort under ErrorActionPreference=Stop.
    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = $prompt | codex exec --sandbox read-only
    $ErrorActionPreference = $prev
    $out | Out-File -Encoding utf8 "reviews\$name-codex.md"
    Write-Host "Verdict saved: reviews\$name-codex.md"
} else {
    $fence  = '```'
    $packet = "# Codex review packet: $name`n`n$context`n`n${fence}diff`n$diff`n$fence"
    $packet | Out-File -Encoding utf8 "reviews\$name-packet.md"
    Write-Host "codex CLI not on PATH - packet written to reviews\$name-packet.md"
    Write-Host "Paste it into the Codex app, save the verdict as reviews\$name-codex.md."
    Write-Host "To automate: npm i -g @openai/codex ; codex login"
}
