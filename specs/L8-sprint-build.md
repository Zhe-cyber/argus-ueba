# Spec: L8 — sprint build: one scoring path in the backend, sensitive list, four scenarios, Malaysia-time rule

**Branch:** `l8-sprint` off `l1-live-baseline` (after Live v1 is committed) · worktree `C:\Users\yyzhe\argus-worktrees\l8-sprint` · **Executor:** heavy (opus) — scoring path · **Written:** 2026-11-12

Read first: `specs/L7-live-evaluation-rules.md` (the contract this build must not break),
`specs/L1`–`L6`, `docs/LIVE_BASELINE_SCORE_V1.md`, `backend/rarity_scorer.py` notes, LESSONS.md.

## Goal
One scoring path. The backend ingest service computes the baseline risk score and raises baseline
findings as events arrive, and stores them in its own database. The workspace reads them from
there instead of computing them on a mirror copy. The Malaysia-time business-hours rule, a
deployment sensitive-resource list and four attack scenarios are part of the same build.

## Non-goals
- Do not change the score's behaviour (L7 §1: algorithm identity). No weight, tier, novelty or
  usual-hours change.
- Do not touch the running pilot checkout (`C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba`)
  or `C:\Users\yyzhe\.codex\worktrees\argus-cloud-live` — read-only. Do not edit files listed in
  `scripts/train_clue_v2.py::TRAINING_SOURCES` (the CLUE benchmark still runs). The V3 study
  files (`scripts/reserved_study.py::SOURCE_FILES`) are closed: leave them untouched.
- The autoencoder frozen feature contracts (CERT 71, cloud 12) and the AE's own off-hours feature
  are not changed.
- No commit, push or PR. No cloud calls; never run any scenario live.

## Approach (planner-decided)

### A. Reference vectors first (guards algorithm identity)
1. Before moving anything, generate `backend/tests/data/baseline_reference_v1_1.json`: at least
   40 synthetic account-day cases covering every signal, Learning, unavailable resource signal,
   novelty discount, usual-hours widening at both edges and midnight wrap, MYT day boundary, and
   the sensitive list. Store inputs and the current outputs (score, tier, signals, facts).
2. `backend/tests/test_baseline_reference.py` asserts the scorer reproduces every case exactly.
   It must pass on the current code before step 3 starts, and after every later step.

### B. Move the scorer into the backend
3. Move the pure scoring logic to `backend/baseline_scorer.py` (functions take an account's event
   rows and a day; no database access inside). `workspace_next/baseline_score.py` becomes a thin
   import of it, so existing workspace code and tests keep working.
4. Backend storage (`backend/event_store.py` schema, created on init for SQLite and PostgreSQL):
   table `baseline_scores(account_key, day, score, tier, signals_json, facts_json, history_days,
   events_today, partial, computed_at)` unique on `(account_key, day)`. Baseline findings go into the
   existing `alerts` table with `alert_type='baseline_risk'`, `severity` = tier, and a unique
   `(alert_type, user_id, day)` guard (add a `day` column or encode it in `details`; choose the one
   that works on both SQLite and PostgreSQL and test both).
5. Ingest path (`backend/main.py::_process_ingest`): after an event with an `account_key` is
   accepted, recompute that account's score for that event's MYT day and upsert it; raise or update
   the baseline finding when the tier is Medium or High; apply the L2 auto-resolve/never-override-
   analyst rules. Recompute is per affected account-day only, never the whole table.
6. Backfill command: `python -m backend.baseline_scorer --backfill` recomputes every stored
   account-day (used once on the operational database and in tests).
7. Workspace: read scores and baseline findings from the backend tables (through the copy it is
   given). Remove `workspace_next/baseline_alerts.py` and the mirror's call to it; the mirror keeps
   copying events and alerts only. Workspace endpoints and the UI keep the same response shapes.
8. Legacy live tiers: `_live_risk_tier` and the user list currently use the AE score. Make the
   user/account risk shown by the backend API the baseline tier; keep the AE value as a separate
   diagnostic field. Update the tests that pin the old behaviour and say which.

### C. Malaysia-time business-hours rule (WP2)
9. Read the notes in `backend/rarity_scorer.py`. Business hours become settings
   (`ARGUS_BUSINESS_TZ=Asia/Kuala_Lumpur`, `ARGUS_BUSINESS_DAYS=Mon-Fri`, `ARGUS_BUSINESS_HOURS=08:00-18:00`)
   used by the rule-based off-hours flag and the "outside business hours" finding. The AE feature
   window stays as it is; add a comment next to both explaining the two windows.
   Tests: 10:00 MYT weekday inside; 02:00 MYT outside; Saturday outside; midnight wrap.

### D. Sensitive resources (WP6)
10. `config/sensitive_resources.json` (tracked): `{"version": 1, "providers": {"aws_cloudtrail":
    ["*-confidential", "*confidential*"], "github_events": [], "cloudflare_access": []}}` with simple
    `*` wildcards, combined with the built-in patterns. The scorer reads it once at start; a missing
    or malformed file falls back to the built-in patterns and logs a warning. The Method and limits
    page lists the active patterns (read through an existing or new workspace endpoint).
11. Record in `docs/LIVE_BASELINE_SCORE_V1.md`: date, reason (rehearsal showed the lab's
    `confidential` bucket was not covered), and that it was fixed before any evaluation attack.
    Recompute and report the 1–11 Nov tier counts (counts only) on the demo copy; if any persona
    account-day rises above Low, stop and report.

### E. Four scenarios (WP9)
12. Extend `scripts/demo_scenario_live.py` and `scripts/demo_scenario_sim.py` to S1–S4 exactly as in
    L7 §2 (`--scenario S1|S2|S3|S4`). Keep every existing guard (dry-run default, explicit
    `--confirm <persona>`, date guard ≥ 2026-11-16 MYT, call caps sized per scenario, read-only
    permissions, ledger with no secrets). S3 and S4 must refuse to run outside 10:00–17:00 MYT;
    S1 and S2 must refuse outside 21:00–22:00 MYT. Cloudflare is used by S1 only.
13. Rehearse S1–S4 in the simulated copy (each on its own simulated day after the latest real day)
    and print, per scenario: score, tier, signals. Record the numbers; do not adjust anything.

### F. Run
14. Rebuild and restart the demo (API 8017, UI 3013) and rehearsal (8018/3014) so they run this
    build; keep the mirror loop running. Leave the ingest backend of the pilot (8013) alone.

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures
- [ ] `test_baseline_reference.py` passes before step 3 and at the end (same file, unchanged)
- [ ] PostgreSQL path: the existing isolated PostgreSQL test pattern covers the new table and unique guard (if no local PostgreSQL, say so; CI runs it)
- [ ] Ingesting a synthetic event stream through `/ingest` produces the same scores/tiers/findings as the backfill command
- [ ] Workspace pages render with the same content on 3013 (browser DOM, no "Application error"); queue and entity scores match the backend table
- [ ] Rehearsal numbers for S1–S4 printed; dry-run of each scenario exits 0; live mode before 16 Nov refuses
- [ ] `git diff --stat l1-live-baseline -- $(TRAINING_SOURCES)` empty; V3 SOURCE_FILES untouched
- [ ] No 12-digit number, email or IP in any output

## Escalation triggers
Stop and report if: a reference vector changes; the PostgreSQL unique guard cannot be expressed
portably; a persona account-day in 1–11 Nov rises above Low after the sensitive list; a step needs
a TRAINING_SOURCES change; the same step fails twice.
