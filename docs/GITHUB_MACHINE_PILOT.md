# GitHub controlled machine pilot

Installed 30 October 2026, after W34's real commissioning activity reached Argus.
This is live-system work; Claude's W33 artifacts and offline model work are not
changed by it.

## What runs

`Argus-GitHub-Machine-Pilot` runs hidden Python every 15 minutes and at logon.
It writes only to the existing private `Zhe-cyber/argus-activity-lab` repository
with the existing restricted App. No new account, permission grant, public
service or project-repository edit was created. Existing DPAPI credentials stay
local; short-lived installation credentials remain in memory. No LLM calls.

Actions run 31 October–13 November MYT. The deterministic plan activates 2–6
profile templates/day, each writing at most one labelled JSON file. Six templates
are still **one native Bot account**, not six human accounts. The activity API
and exact commit/actor checks provide native evidence. Files and commits are
explicitly controlled machine workload. One repository gives little resource
diversity; this pilot does not establish AE eligibility or human behaviour.

At most six write attempts/day and 84 for the pilot, excluding commissioning.
The task is reconciliation-only on 14 November and expires 15 November 00:00 MYT.
The laptop must be awake, online and the user logged in for this interactive,
current-user task. Missed slots/days are recorded without generating catch-up
actions. Global power, update and billing settings were not changed.

## Evidence and operation

Private state under `data/live/github-app-lab-v1/` (ignored):

- `pilot-config.json`: source/scope pins and immutable commissioning binding.
- `machine-ledger.db`: original write claims, native commit IDs, activity receipts.
- `last-pilot-status.json`: latest sanitized result.
- `pilot-attempts.jsonl`: append-only results, including failures.
- `native-activity/`: exact content-addressed provider payloads; keep private.

First real pre-start tick passed with zero writes and no newly ingested events.
No full workload day or scheduled-write result is claimed at installation time.
The old commissioning watcher remains disabled. Task action/working-directory
readback matched the intended hidden Python and source.

An unknown write outcome or pending Bot identity blocks further writes. Known
commits can continue read-only reconciliation; missed/unknown actions are not
silently replayed. Provider verification requires the exact native activity and
Argus receipt. A 30-row activity cap is explicit telemetry, not full coverage.

The live source card refreshes from Argus; provider activity can arrive later
than the write. No extra account or priority is fabricated while waiting.

PowerShell to inspect or stop this task only:

~~~powershell
Get-ScheduledTask -TaskName 'Argus-GitHub-Machine-Pilot'
Get-ScheduledTaskInfo -TaskName 'Argus-GitHub-Machine-Pilot'
Get-Content 'C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba\data\live\github-app-lab-v1\last-pilot-status.json'
Disable-ScheduledTask -TaskName 'Argus-GitHub-Machine-Pilot'
~~~

Disabling the task does not delete state or change the AWS study. Inspect
unknown claims rather than clearing the ledger. Source edits require reviewed
configuration repinning before future ticks; do not blindly regenerate pins.

Implementation: `scripts/github_machine_pilot.py`; setup helper:
`scripts/install_github_machine_pilot.ps1`; fixed plan: W35. Synthetic tests cover
planning, expiry, claim-before-write, no-repeat/unknown blocking, caps, exact
activity receipts, missing evidence, source/scope rejection and failure history.
