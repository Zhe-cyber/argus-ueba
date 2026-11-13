# Spec: L2-live-workspace-fixes — baseline alerts, finding actions, live mirror and feed, UI audit fixes

**Branch:** `l1-live-baseline` (continue in `C:\Users\yyzhe\argus-worktrees\l1-live-baseline`; L1 work is there, uncommitted) · **Executor:** executor (sonnet) · **Written:** 2026-11-10

## Goal
The demo workspace (API 8017, UI 3013) behaves like a working product: the baseline score raises its
own alerts, an analyst can disposition findings, the copy follows the live collection within about a
minute, the Overview shows a live feed and today's riskiest accounts, and the eight UI defects from
the 10 Nov audit are fixed. Read `specs/L1-live-baseline-score.md` and
`docs/LIVE_BASELINE_SCORE_V1.md` first.

## Non-goals
- No edits under `backend/` (new test files allowed), none to `SOURCE_FILES` / `TRAINING_SOURCES`
  files. The business-hours rule fix in `backend/rarity_scorer.py` waits until after 15 Nov.
- No change to baseline weights, tiers, or the rho rule. No AE gate change.
- No writes to the live DB or the pilot checkout. No cloud calls. No change to the pilot schedule.
- No commit, push or PR.
- No demo attack scenario (separate decision).

## Files in scope
New: `workspace_next/baseline_alerts.py`, `workspace_next/live_mirror.py`,
`workspace_next/frontend/components/LiveFeed.js`, tests `backend/tests/test_baseline_alerts.py`,
`backend/tests/test_live_mirror.py`, `backend/tests/test_finding_status.py`.
Edited: `workspace_next/app.py`, `case_api.py`, `queries.py`, `operations.py`, `workload_groups.py`,
`finding_context.py` (only if needed for step 3), frontend `pages/index.js`, `pages/workspace.js`,
`pages/entities.js`, `pages/connections.js`, `pages/cases/[id].js`, `components/WorkspaceUI.js`,
`components/BaselinePanel.js`, `components/DiagnosticPanel.js`; `docs/LIVE_BASELINE_SCORE_V1.md`.

## Approach (planner-decided)

### A. Baseline alerts
1. `baseline_alerts.sync(db_path)`: for every account-day with tier Medium or High, upsert one row
   in a new table `workspace_baseline_alerts` in the copy DB (same columns as `alerts`, plus
   `account_key`, `day`; unique on `(account_key, day)`). `alert_type='baseline_risk'`,
   `severity` = tier, `title` = `Baseline risk <tier> (<score>): <account_label>`, `details` =
   JSON `{day, score, tier, signals, facts, history_days, events_today, partial}`.
   On re-sync: update score/tier/details/title; never touch `status` set by an analyst, except:
   if the day's tier falls below Medium and status is still `Open`, set `Resolved` with
   `details.auto_resolved = "score fell below Medium"`.
   Row ids must not collide with `alerts.id`: expose id as `1000000 + rowid`.
2. `queries.py`: findings list and detail read `alerts` UNION `workspace_baseline_alerts`
   (`origin = 'baseline'`). `/findings/{id}`, case links and case snapshots must work for both.
3. Triage for `origin='baseline'`: tier High → `review_first`; Medium → existing rule.
   Default queue sort stays score desc, so baseline alerts lead.

### B. Finding status actions
4. `POST /findings/{id}/status` body `{status, analyst, reason}`; status ∈ Open, Acknowledged,
   Resolved, False Positive; `analyst` and `reason` required (422 with a clear message otherwise).
   Updates the row in whichever table owns the id, sets/clears `resolved_at`, and appends to a
   new table `workspace_finding_audit(id, finding_id, old_status, new_status, analyst, reason, at_utc)`.
   Reuse an existing `backend.alert_store` function if one already does the update; do not edit it.
5. Finding dialog (`workspace.js`): buttons Acknowledge / Resolve / False positive / Reopen with
   analyst + reason inputs; show the server's error text on failure; disabled in presentation mode.

### C. Live mirror and feed
6. `python -m workspace_next.live_mirror --source <live events.db> --dest <copy db> [--interval 60] [--once]`:
   - opens source with `?mode=ro`; `INSERT OR IGNORE` new `events` rows (by primary key) and new
     `alerts` rows (by id) into the copy. Existing copy rows are never overwritten (analyst state wins).
     Do not touch `analyst_*`, `identity_*`, `workspace_*` tables.
   - **Study guard:** while now < 2026-11-16T00:00+08:00, skip any event with timestamp ≥
     2026-11-14T00:00+08:00 and any alert created at or after that instant. One constant, tested.
   - after each pass: `baseline_alerts.sync`, then write `mirror-status.json` in the preview root:
     `{last_pass_utc, events_added, alerts_added, source_latest_event_utc, guard_active}`.
   - collector status: read the pilot's
     `C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\pilot-local-v1\last_tick.json`
     (read-only) and refresh `operations-snapshot.json` in the preview root. First find the existing
     producer of that file and its schema (`workspace_next/operations.py`, `scripts/*workspace*`,
     the 3011 preview root has an example) and reuse it; if no reusable producer exists, write the
     same schema with only the fields you can fill truthfully (collector status + last check per
     source) and leave the rest null. Do not invent workload/schedule data.
   - a failed pass logs and retries next interval; it never deletes anything.
7. `GET /workspace/live-feed`: per source — `last_received_utc` (max `ingested_at`),
   `events_last_hour`, `events_today_myt`, and the 8 newest events `{time_myt, account_label,
   action, received_seconds_ago}`; plus `mirror` (the status file) and `collector` (last tick time, ok).
   No IPs, no raw payloads, emails masked as `[email hidden]`.
8. `LiveFeed.js` on the Overview: three columns (AWS / GitHub / Cloudflare), newest events on top,
   "received Ns ago", a green/amber/grey dot per source (received < 15 min / < 2 h / older), mirror
   and collector last-check lines; polls every 10 s; shows a plain "feed unavailable" on error.

### D. UI audit fixes
9. **Overview:** add "Highest baseline scores today" (top 5 accounts from the summary endpoint,
   linking to the entity). Replace "Model scoring is not enabled in this workspace preview." with
   "Baseline scoring v1 is active. The autoencoder diagnostic stays hidden until its evaluation."
   "Sources needing review" shows the number, or "0" — never "Unavailable" when the snapshot exists.
   Recent findings show account label and score chip.
10. **Queue:** a "Group similar" toggle (default on): one row per `(account, alert_type)` with
    count, latest time and highest score, expandable to its findings. `Learning` renders as
    `Learning (n of 5 days)` using `prior_observed_active_days`. Date filters are labelled and
    interpreted as MYT and converted to UTC for the API. Under each title show the specific action
    from `details.action` when present.
11. **Finding dialog:** show the account-day baseline score and facts (compact `BaselinePanel`).
    Hide the Model diagnostic box when `/workspace/diagnostic-availability` reports nothing configured.
12. **Cases:** "Include this account's activity" defaults to ticked. Missing Analyst/Reason shows an
    inline message next to the field (not only the browser tooltip). On close: a ticked-by-default
    "Also update linked findings" sets each linked Open/Acknowledged finding to False Positive when
    the resolution is "Detection false positive", otherwise Resolved, through the step-4 path.
13. **Entities:** workload group labels use the persona `label` from
    `scripts/persona_profiles_v2.json` (read-only; e.g. "Batch reporter (persona-02)").
    Account lists mask email-shaped labels unless the row is selected.
14. **Connections:** each source card shows collector status, last check, last received and events
    today from steps 6–7; "Refresh snapshot" re-reads them.
15. **Header:** `Argus · live mirror of collected data (read-only source)` while `mirror-status.json`
    is younger than 5 minutes; otherwise the current text.
16. Delete the closed case titled "Audit test case" from the copy DB (it was a UI test).

### Run
17. Rebuild the preview frontend (no npm install), restart 8017 and 3013 only, start the mirror
    loop as a hidden background process with `--interval 60`, and leave all three running.

## Acceptance checks (from the worktree)
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures
- [ ] `git diff --stat origin/six-role-commissioning -- backend/ scripts/` → empty (new tests are untracked)
- [ ] Pilot checkout `git status --porcelain` → only the two spec files
- [ ] Mirror: two passes 60 s apart; `mirror-status.json` updates; copy has 0 events ≥ 14 Nov MYT; a second pass with no new source rows adds 0
- [ ] `/findings?limit=500&status=All` contains `origin='baseline'` rows; count equals the number of Medium+High account-days in the step-12 report of L1
- [ ] Status change: POST to one rule finding and one baseline finding → list filter by the new status returns them; audit rows written; mirror pass afterwards does not revert them
- [ ] Browser check of each page (use the built-in browser or HTTP + DOM): Overview shows feed with three sources and top-5 list; queue grouped; dialog shows baseline facts and four action buttons; a case created from a finding has events in its timeline; Workloads tab shows persona role names and switching Accounts → Workloads → People does not crash; Connections shows collector status
- [ ] No 12-digit account number and no email address in any `/workspace/live-feed` response

## Risk notes
- The live DB is being written by the pilot every 5 minutes: read-only URI, short transactions,
  tolerate `database is locked` by skipping the pass.
- Tests use temp SQLite only (LESSONS 10). Never run the mirror against the live DB as `--dest`:
  refuse to start unless the dest folder has a valid `workspace-copy.json` marker with `not_live: true`.
- Never print account numbers, emails, IPs or raw events. Persona labels are fine.
- Product rule: no Anthropic API in product code.

## Escalation triggers
Stop and report if: a step needs a `backend/` or frozen-file edit; the operations-snapshot schema
cannot be determined; the UNION in step 2 breaks existing workspace tests in a way that needs a
behaviour decision; any pass would write to the source DB; the same step fails twice.
