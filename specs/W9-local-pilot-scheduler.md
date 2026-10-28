# W9: local laptop pilot orchestration

28 October 2026. User chose this laptop for the pilot. Read-only checks found
one verified commissioning action, no Argus scheduled task or repository cron,
an initial restricted-context reachability failure on port8012, and valid non-root simulator identity. Regular
histories are not accumulating. Address this before the next offline model test.

Implement one repeating current-user Windows task plus an owned loopback backend
service task. Poll every five minutes while logged in,
awake and online, ending after24November Malaysia time. Do not change power
settings, wake the laptop, store a Windows password or create a hosted runner.
Task actions run hidden and without elevation. Source-pinned wrapper fails closed
if runtime source changes; keep this checkout available throughout the pilot.

The wrapper must:
- Force local SQLite, live mode, unverified/no activated cloud model and the
  existing actual connected state directory. Bind backend only127.0.0.1:8013.
  Add an internal readiness route in the startup wrapper (not core backend),
  returning a hash of the actual storage path and source/runtime configuration.
  Never forward to a different demo/snapshot backend merely because it says live.
  Existing unexpected listener must not be killed or reused.
- Preserve the existing ledger/profiles/caps/15-minute due window and native
  receipts. Actors start29October and stop after24November. No commissioning
  re-run, fabricated events, backfill, retry of unknown actor attempts, writes
  to toy resources or expanded cloud permissions.
- Collect AWS with existing restricted collector (at most five batches per
  tick), then run due-only actors only when AWS collection succeeds, then audit
  receipts using the existing native DB. GitHub/Cloudflare bounded genuine feeds
  may poll at most every30minutes; keep source-specific failures separate.
- Never expose credentials in arguments/config/logs. Use existing AWS profiles,
  current-user Cloudflare DPAPI loader and gh authentication. Config contains
  only resource scope, paths, source hashes and profile names. Logs are local,
  ignored, counts/status only. Failures/timeout remain failures, not empty normal
  datasets. Tick heartbeat means orchestration ran, not full source/day coverage.
- Use non-overlap task settings plus an OS file lock. Bounded subprocess times;
  terminated uncertain requests stay protected by the existing actor ledger.
  Do not auto-retry an actor subprocess on failure. Expired jobs perform no cloud
  calls. Provide check/status modes and uninstall/disable instructions.

Before installing: synthetic tests mock subprocess/network, force
DATABASE_URL=sqlite-local, verify wrong backend/source drift/expired window or
collector failure cannot run actors, and confirm no model activation. Back up
the existing event DB consistently. Prepare concrete config and task XML with
current-user interactive token, IgnoreNew overlap policy, finite expiry and
hidden interpreter. Install only the dedicated Argus task; no other task edits.
Verify actual bounded collection, startup readiness fingerprint, ledger and
last-run evidence. Actual actor actions are not required on commissioning day;
report starts29October rather than generating extra traffic now.

This is a local controlled lab history service, not independent human users,
complete cloud telemetry, a validated live detector or an active billing alarm.
The prospective source/idle-day coverage and model-release gates still apply.

Commissioning correction: a host-context check found an older listener on8012;
the first new tick failed its identity check before provider calls. Stop only
the two new tasks, keep the pre-existing listener untouched, and use verified-
free port8013. Preserve the original config as a local repair record and update
the source pin deliberately after testing. The data/ledger/profile/budgets and
study windows do not change. Do not interpret sandbox reachability denial as
proof that a host service is offline.
