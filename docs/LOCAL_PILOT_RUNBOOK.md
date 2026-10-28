# Laptop pilot collection

28 October 2026. The user selected this laptop. Two dedicated current-user
Windows tasks are installed locally: `Argus-Pilot-Backend` and
`Argus-Pilot-Collect`. This is controlled lab/genuine account telemetry
collection, not model activation, independent human users or a cloud deployment.

## Current verified state

The pilot backend binds **127.0.0.1:8013**, forcing SQLite, live mode,
`CLOUD_MODEL_PROFILE=unverified` and the existing actual `data/live/connected`
store. An internal `/pilot-health` route identifies the configured runtime,
storage-path hash and source pin. It is added by the launcher, not the core API.
An older listener on 8012 is untouched. The new pilot service binds only loopback.

At **20:46:58 Malaysia time, 28 October**, a scheduled cycle completed with exit
code 0 and verified backend identity:

| Phase | Observation |
|---|---|
| AWS | 45 native events inserted and acknowledged; zero retained/malformed |
| GitHub | 13 inserted, four duplicates; bounded repository Events API sample |
| Cloudflare | Existing Access-app query succeeded; no new login records |
| Actors | No actions executed; ordinary pilot begins 29 October |
| Receipt audit | No new receipts awaiting or gaining verification in this cycle |

These AWS events are existing native account activity, not 45 persona actions.
GitHub activity can include owner/tool-assisted operations; it is not a cohort
of independent people. Cloudflare provides authentication observations, not
in-application activity. An empty bounded query is not proof of complete logs.
The original commissioning probe/ledger is preserved and excluded from fitting.
Raw collection records are not automatically verified-normal training data.

## Schedule and guards

- The repeating task polls every five minutes while the user is logged in,
  the laptop is awake and Windows reports a network connection. Locking the
  screen is compatible with an interactive-token task; signing out/sleeping or
  network loss can miss activity. No power settings or Windows password were
  changed/stored; WakeToRun is false.
- The backend has a logon task and can be started by the collector task. Both
  run without elevation or visible console windows. Only these owned task
  names are managed; existing tasks/processes are not replaced.
- AWS collection is bounded to five batches per tick. Only successful AWS
  collection permits the due-only actor runner. Unknown actor claims block
  further automatic actors for review. No actor subprocess is retried within
  a tick. Existing ledger claims, read-only fixture permissions, caps of 48/run,
  128/day and 1792/pilot, and the 15-minute grace remain unchanged.
  Those SDK limits apply to the actor runner; bounded collector polls are
  separate operations and are not described as part of that actor budget.
- Actor activity starts 29 October. Missed slots are not backfilled, timestamps
  are not rewritten, and commissioning is not rerun. Source receipts still
  require matching native CloudTrail records via the existing audit path.
- Genuine GitHub/Cloudflare queries occur at most every 30 minutes. Failed
  attempts are persisted and remain visible between polls, not converted to
  empty normal observations. Credentials stay in existing AWS profiles,
  GitHub authentication and current-user Cloudflare DPAPI storage.
  Between polls, counts are nested under `previous_outcome` with their original
  attempt time; they must not be summed as new inserts on the current tick.
- Task overlap policy is IgnoreNew; OS file locks also protect manual overlap.
  Subprocesses have bounded times. Timeout/termination may leave unknown
  attempts, which the existing ledger preserves without automatic retries.
- The pilot ends after 24 November Malaysia time. No later cloud calls are
  authorized by this job. The service has an expiry timer as well as task
  boundaries. Competition-day service configuration will be prepared separately
  after evaluation; this finite, unverified pilot launcher is not a final release.

The actual runtime checkout must remain available. A hash pin covers backend
runtime files, the collector/actor helpers, fixture definitions and frozen
profiles. Source drift fails closed. New isolated model-analysis scripts do not
alter that pin; changing serving/collector code requires stopping owned tasks,
reviewing the change and deliberately refreshing the private config/version.
Never refresh hashes blindly to silence a failure.

## Local state and inspection

Private state is a sibling of `connected` and `persona-history-v1`, named
`pilot-local-v1`. `config.json` contains paths/scope/profile names and hashes,
**no keys or tokens**. Existing event/ledger databases have consistent initial
SQLite backups there. The runner continues to use the original ledger.
Status, per-day count-only tick logs, genuine-source poll outcomes and a private
backend log are kept locally and ignored by Git. Do not publish raw provider data.

```powershell
python scripts/local_pilot.py check --config CONFIG_PATH
python scripts/local_pilot.py status --config CONFIG_PATH
Get-ScheduledTaskInfo -TaskName Argus-Pilot-Collect
```

Use the configured existing Python environment, not an unrelated interpreter.
Status checks include backend identity and prefer a newer failure over stale
successful tick output. An operational tick is not full source/day coverage or
proof of a usable baseline. Reconcile plans, attempts and native observations;
keep no-activity, missed/unresolved and insufficient-history states distinct.
The prospective protocol and idle-day/model gates remain in force. The planned
November resource-change scenario executor is still separate pending work.

To pause only this pilot:

```powershell
Disable-ScheduledTask -TaskName Argus-Pilot-Collect
Stop-ScheduledTask -TaskName Argus-Pilot-Collect
Stop-ScheduledTask -TaskName Argus-Pilot-Backend
Disable-ScheduledTask -TaskName Argus-Pilot-Backend
```

To remove scheduling after stopping it, unregister only those two exact names.
Keep all data, ledger and evidence files; uninstalling tasks must not reset
claims or budgets. The installer refuses existing task names rather than
silently replacing them.

## Commissioning corrections and validation

The first reachability check ran in a restricted tool context and incorrectly
suggested that 8012 was offline. The first new tick correctly rejected the older
listener's missing identity endpoint before provider collection. It was not
killed or reused. The private config was preserved before a tested 8013 repair;
data, ledger, source scopes and study windows stayed unchanged.

Hidden `pythonw.exe` also has no console streams; Uvicorn formatter setup failed
with ValueError caused by an `isatty` lookup on None. A local file stream fixes
that issue, and a synthetic regression reproduces construction under hidden
streams. Only the newly owned tasks were stopped/restarted during repairs;
private config snapshots preserve the engineering history.

A later automatic cycle also completed successfully. Its status initially
repeated the previous genuine-feed poll counts alongside a not-due marker.
Those counts are now explicitly nested as the previous outcome, with a
regression test; stored events were never duplicated by this display issue.

Final full regression: **374 passed, one optional PostgreSQL skip**, with
DATABASE_URL=sqlite-local, including all 13 scheduler tests.
CI is recorded in the PR. PowerShell AST parsing
reported zero errors; actual registration, startup fingerprint and scheduled
bounded collection were also verified. No new IAM permissions, model, toy
resource writes or production/HF deployment. Billing-alarm activation is not
claimed. Independent review is not claimed; the user prefers manual transfer.
