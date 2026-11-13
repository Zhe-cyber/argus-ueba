# Manual pilot commit — target 5 November

The user commits/pushes manually. Current local work includes W18–W33, backend
identity/normalisation changes, frontend work, collector fixes and offline
results; no automatic commit. Verify the current branch rather than assuming it.
Review all staged files; do not push/merge or switch branches as part of this
checklist. This is a staging checklist, not a claim that this entire batch has
received one final independent review.

PowerShell:

~~~powershell
Set-Location 'C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba'
git -c core.bare=false config --worktree core.autocrlf false
git -c core.bare=false branch --show-current
git -c core.bare=false status --short
git -c core.bare=false add -- backend frontend scripts docs specs infra
git -c core.bare=false diff --cached --check
git -c core.bare=false diff --cached --stat
~~~

Inspect these directories for unrelated changes before proceeding. The earlier
command omitted backend implementation, frontend and infrastructure files needed
by the newer work. Private pilot data, keys and models must remain ignored and
unstaged; inspect `git diff --cached --name-only`. If any check fails, stop rather
than committing an unknown state. W33's new access module is not imported by the
running pilot, and does not require a runtime repin.

Stage only the aggregate offline result artifacts separately after reviewing
them. CSV files are globally ignored, so adding the result directory alone will
not include its metrics CSV:

~~~powershell
git -c core.bare=false add -- results/shared-core-reserved-v1/report.md results/shared-core-reserved-v1/roc-comparison.png results/shared-core-reserved-v1/provenance.json
git -c core.bare=false add -f -- results/shared-core-reserved-v1/metrics.csv
git -c core.bare=false diff --cached --check
git -c core.bare=false diff --cached --stat
~~~

Do not force-add any raw logs, account-level data, model files or credentials.
Review/handover files under `reviews/` are deliberately not staged by these
commands. Their presence may leave untracked files after the code commit.

update.md is a local handover and is deliberately excluded from staging. A worktree-local exclude rule keeps it out of normal status without altering the repository .gitignore. The batch DOES include the deferred W19 webhook receiver as tested inactive code; it creates no deployment, listener, task or webhook on import. If you want to omit that code from this commit, unstage those W19 paths explicitly and expect them to remain uncommitted; do not claim an entirely clean worktree.

After reviewing:

~~~powershell
git -c core.bare=false commit -m "Add guarded cloud pilot, identity review, benchmark results and W33 protocol"
git -c core.bare=false status --short
git -c core.bare=false log -1 --oneline
$pilotPython = 'C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe'
$pilotConfig = 'C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\pilot-local-v1\config.json'
& $pilotPython scripts/local_pilot.py check --config $pilotConfig
& $pilotPython scripts/local_pilot.py status --config $pilotConfig
~~~

Pilot verification requires configuration_valid=true and backend_ready=true.
Inspect every remaining status entry; do not claim a clean worktree while
deliberately excluded handovers or other changes remain. A commit ordinarily
does not change working bytes. If pins fail, preserve evidence and investigate;
do NOT automatically repin or run checkout/renormalize. Future runtime edits need
the usual controlled release and must meet the pre-calibration deadline.

This is not a claim that the worktree is clean today. It becomes complete after user commit and checks. Send the commit hash/status back for verification. Git uses the user's configured author identity.
