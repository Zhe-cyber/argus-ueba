# Collection after the pilot (L9 Part A)

The laptop pilot stops collecting at 17 Nov 2026 00:00 MYT (its backend on 8013 exits by itself).
AWS keeps queued events for 3 days; the GitHub and Cloudflare fetchers look back 24 hours, so the
operational collector must be running by about 17 Nov 20:00 MYT to avoid a gap.

## What runs

- `scripts/ops_collect.py tick` - the existing fetchers from `scripts/collect_live.py`, unchanged:
  `collect_aws` (SQS; non-root `argus-collector` profile, us-east-1 queue of the expected account,
  verified dead-letter queue, delete only after a durable ingest receipt), `collect_github` (repository
  Events via `gh`, owner/admin check, same `github-event-revisions` archive), `collect_cloudflare`
  (Access request log, filtered to each configured app id). Each provider is isolated; outcome per
  provider in `ops-status.json` (counts, error kind, last success, minutes since last success,
  `possibly_truncated`, and the persona summary). No collection before `collect_start_local`.
- `scripts/ops_personas.py tick` - from 16 Nov: AWS personas through `run_persona_history.plan_today /
  execute / audit` (profiles v2, same caps, 15-minute grace, claim before I/O, no retry) on a new marked
  ledger with its own lifetime budget; Cloudflare personas (one request per persona per day in the
  machine pilot's windows, DPAPI loader, own ledger, 6/day, 90/ledger). A 401/403 stops Cloudflare
  persona actions (`token_expired_or_invalid`) until the owner sets `reviewed_through_utc`.
  **GitHub is collection only**: the machine pilot's write function is bound to its dated plan and ledger.
- `scripts/ops_collect.py serve` - the ingest backend (`backend.main`, live mode, SQLite in
  `live_state_dir`). `/` and `/ingest` stay a loopback machine interface; workspace sign-in does not apply.

## Limits

GitHub and Cloudflare fetches are bounded samples: the last 24 h, at most 100 records per fetch
(Cloudflare's 100 are account-wide, before the app filter). `possibly_truncated: true` means a fetch
returned a full page and older records may have been missed. `minutes_since_last_ok` shows downtime.

## Owner steps (in order)

1. Copy `config/ops.json` to `data/live/ops/ops.json`; fill account/queue/app ids, repos, `gh_path`,
   `supervisor.python`. Set `live_state_dir` to the event store the workspace mirror reads (recommended:
   the existing pilot `data/live/connected` folder, used in place after the pilot backend has exited, so
   evidence is never split). Include the machine-lab Access app id in `providers.cloudflare.app_ids`;
   set `personas.enabled`, `personas.cloudflare.state_dir` and `tokens_valid_until_utc` (renewed tokens).
2. `python scripts/ops_collect.py check --config data/live/ops/ops.json` - must print
   `machine_lab_app_collected: true` if Cloudflare personas are on.
3. **Retire.** After 17 Nov 00:00 MYT: `scripts/retire_pilot_tasks.ps1` (dry run), then `-Apply`.
4. **Wait for drain.** Disabling lets a running pilot tick finish. Do not continue until `Argus-Pilot-Collect` is
   Disabled (not Running) and no process runs `local_pilot.py ... tick` or `collect_live` (the dry run of step 6
   prints the current state; `scripts/ops_cutover_check.py` decides).
5. **Final snapshot / init.** Only now take the final copy of the pilot store: only if `live_state_dir` is a new
   folder, `python scripts/ops_collect.py init --config ... --from <pilot events.db>` and point the workspace mirror
   at the new store. (A snapshot taken before the drain can miss the last tick's events.)
6. **Install.** `scripts/install_ops_tasks.ps1 -Config data/live/ops/ops.json` (dry run), then `-Apply`;
   `Start-ScheduledTask -TaskName Argus-Ops-Backend`. `-Apply` re-checks the drain itself, waits up to 10 minutes
   (every 15 s) and refuses if the old collection is still alive: two collectors would split the SQS queue.
7. Before the first evaluation check: `python -m backend.readiness --db <live_state_dir>/events.db` must print READY
   (exit 0). It reports the method binding, the comparator manifest actually loaded, account-days without a score
   (repair: `python -m backend.baseline_scorer --repair-missing --db <db>`, `python -m backend.live_ae repair-missing
   --bundle <pinned bundle> --db <db>`), schema columns and events from 13 Nov.
8. After a few ticks read `data/live/ops/ops-status.json`.

These tasks are the interim scheduler; `install_supervisor_task.ps1` removes them when the supervisor
takes over (one scheduler only).

## Supervisor (Part C) and notifications (Part D)

`scripts/argus_supervisor.py --config <ops.json>` is the single scheduler once installed
(`scripts/install_supervisor_task.ps1`, dry run then `-Apply`; it removes the interim Argus-Ops-* tasks).
It runs ingest API, collector loop, persona loop (independent), mirror, workspace API (sign-in files from
`auth`), notifier and web UI (built with `NEXT_PUBLIC_API_URL` = workspace API). Restart back-off 2-60 s;
five exits in ten minutes = failed. `health.json` every 30 s; Connections shows one row per component.
Ports in the template: ingest 8020, workspace API 8021, UI 3016.

`python -m backend.notify loop` (run by the supervisor): one message per account-day baseline finding at
High, state in `notify.db` (no resend after restart; Highs present at first start are skipped). Default
sender `outbox` (JSONL file). For Telegram/email set `notify.sender` and create the credential file
(JSON: `bot_token`, or `username`/`password`) at `notify.credential_file`; it is never logged.

Workspace users: `python -m backend.auth add-user <name> --role analyst --users-file data/live/ops/auth/users.json`.
