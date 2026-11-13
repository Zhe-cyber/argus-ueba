# Spec: L9 — collection continuity, login and analyst identity, run as a service, notifications

**Branch:** `l9-platform` off `l1-live-baseline` (after Live v1 is committed) · worktree `C:\Users\yyzhe\argus-worktrees\l9-platform` · **Executor:** heavy (opus) for login; executor (sonnet) otherwise · **Written:** 2026-11-12

Read first: the hardening plan sections WP1, WP3, WP4, WP5 (summarised below), `specs/L1`–`L6`,
`specs/L8-sprint-build.md` (built in parallel on another branch: do not touch scoring files —
`backend/baseline_scorer.py`, `backend/rarity_scorer.py`, `backend/main.py::_process_ingest`,
`workspace_next/baseline_*`), LESSONS.md.

## Non-goals
No scoring change. No edits to the running pilot checkouts (read-only). No commit/push. Never
create, read or print real passwords, tokens or keys; never install scheduled tasks — write the
install scripts for the owner to run. No cloud calls except where a step says "owner runs".

## A. Collection continuity (WP1) — first, it is time-critical
1. `scripts/ops_collect.py`: one tick that runs the three existing provider fetchers
   (AWS SQS, GitHub events, Cloudflare Access — import them from `scripts/collect_live.py` /
   their modules; do not modify those files) against a configured backend, with no study dates,
   persona actors or reserved logic. Each provider is independent: one failing does not stop the
   others. Writes `ops-status.json` (per provider: last run, ok, received, inserted, error kind).
2. `scripts/ops_personas.py`: runs the ordinary persona workloads after 15 Nov using the same
   plan generator and profiles (import `persona_history_plan.make_plan`, profiles v2) for any date,
   the same AWS execution mechanics (import from `run_persona_history.py`), its own new ledger
   file, the same caps, and the same no-retry rule. Cloudflare persona requests likewise through
   the existing loader. GitHub persona pushes: reuse the GitHub machine pilot's action function if
   it can be imported without date limits; otherwise leave GitHub to collection only and say so.
3. `config/ops.json` (tracked template, no secrets): backend URL, database path, intervals,
   provider toggles, ledger path, persona on/off.
4. `scripts/install_ops_tasks.ps1` for the owner: one task every 5 minutes for `ops_collect`
   + `ops_personas`; and `scripts/retire_pilot_tasks.ps1` that disables the old Argus-Pilot-*
   collector/actor tasks (not the backend) — both print what they will do and need `-Apply`.
5. Tests with mocked providers: provider isolation, status file, persona plan for 16–30 Nov,
   caps, no retry, refuses to write into the pilot's ledger.

## B. Login and analyst identity (WP4)
6. `backend/auth.py`: users file (outside git, path in config), scrypt hashes with per-user salt
   (`hashlib.scrypt`), roles `analyst` / `viewer`; `python -m backend.auth add-user <name> --role analyst`
   prompts for the password twice (no password on the command line, no default user).
7. Session: signed HTTP-only, SameSite=Strict cookie; secret from a file outside git created on
   first run; 8 h idle expiry; logout. Five failures lock that user for 5 minutes; failures logged
   without the password.
8. Enforcement on the workspace service: every route needs a session except `/auth/login`,
   `/auth/logout`, `/health`; changing routes need role `analyst` and header `X-Argus-Request: 1`.
   Case/finding changes take the analyst name from the session; remove the free-text Analyst
   fields from the UI and API bodies (keep accepting and ignoring them for one release, logged).
   Old audit rows keep their text and are shown as "recorded before sign-in".
9. UI: login page, signed-in name + logout in the header, redirect to login on 401, viewer sees
   no change buttons.
10. Tests: no session → 401 on every protected route (parametrised over the route list); wrong
    password; lockout; expired session; tampered cookie; viewer blocked; missing header blocked;
    audit row carries the session user. Existing tests sign in through a fixture user.
11. Write `reviews/L9-auth-security-review.md`: threat list and how each is handled, for the
    project's security review step.

## C. Run as a service (WP3)
12. `scripts/argus_supervisor.py`: starts and watches ingest API, ops collector loop, mirror,
    workspace API, web UI from `config/ops.json`; restart with back-off; five failures in ten
    minutes → failed; writes `health.json` every 30 s. `/health` on the workspace; Connections shows
    one row per component.
13. `scripts/install_supervisor_task.ps1` (owner runs): logon task for the supervisor; prints and
    needs `-Apply`. Remove hard-coded user paths from tracked code (use config).
14. Tests: child crash → restart; repeated crash → failed; health file content.

## D. Notifications (WP5)
15. `backend/notify.py`: sender chosen in config (`telegram` | `email` | `outbox`); default
    `outbox` (writes to a local file). One message per baseline finding that first reaches High,
    recorded in a table so restarts never resend; masked account numbers and emails; send failures
    retried later and never block ingest. Telegram via HTTPS bot API, email via `smtplib`; the
    credential is read from a file the owner creates (path in config); never logged.
16. Tests with the outbox and mocked senders: one message per High; no resend after restart;
    masking; failure isolation.

## Order and acceptance
Order: A (by end of 15 Nov) → B → C → D. Each part ends with the full test suite green:
`$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures.
Browser check (DOM) after B: login works with a fixture user in a temp users file; every page
redirects to login without a session. Report per part what was built, test totals, what the owner
must run, and anything not verified.

## Escalation triggers
Stop and report if: a provider fetcher cannot be imported without modifying its file; the persona
runner cannot be reused without the study's date guards; auth needs changes to scoring files owned
by L8; the same step fails twice.
