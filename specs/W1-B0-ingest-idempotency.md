# Spec: W1-B0-ingest-idempotency — server-side eventID dedup (gates W1-B)

**Branch:** `w1-b0-ingest-idempotency` · **Executor:** heavy (opus) — ingest spine ·
**Reviews:** planner + Codex MANDATORY (§4 rank 1) · **Written:** 2026-07-06

## Goal
POSTing the same cloud event to `/ingest` twice results in exactly one stored event and no
double-counting in the 24h window, AE history, or `total_event_count`. This unblocks W1-B:
SQS standard queues are at-least-once, so duplicates WILL arrive (UPGRADE_PLAN R10).

## Non-goals
- No SQS consumer (that's W1-B1). No feature/scoring changes. No threshold changes.
- Do NOT dedup events that lack a native event id — see the CRITICAL design rule below.

## Files in scope
- backend/event_store.py (schema + insert path)
- backend/normalizer.py (surface native event id as a top-level field)
- backend/main.py (`ingest_event` — minimal change only)
- backend/tests/ (new tests)

## Approach (planner-decided — do not deviate without escalating)
1. **Dedup key = source-native event id ONLY.**
   - aws_cloudtrail → `eventID`; azure_ad → sign-in log `id`; github_events → delivery
     `id` if present; cloudflare_access → ray/event id if present.
   - normalizer: add top-level `event_id` (string | None) to the normalised dict for
     each parser, extracted from the raw record (CloudTrail's is currently buried
     write-only in the metadata blob — surface it, keep metadata as-is).
   - **CRITICAL: events with `event_id=None` (all CERT replay sources) are ALWAYS
     inserted, exactly as today.** Do NOT hash-dedup (timestamp,user,action,...):
     CERT replay legitimately contains identical-looking rows, and dropping them would
     silently change the frozen replay AUROC. This rule preserves the CERT path
     byte-for-byte by construction — state this in the PR body for the evaluator.
2. **event_store.py:**
   - Add `event_id TEXT` column + `CREATE UNIQUE INDEX IF NOT EXISTS
     idx_events_event_id ON events(event_id)` — note SQLite unique indexes allow
     multiple NULLs, which is exactly the semantics rule 1 needs (verify with a test).
   - Migration must be idempotent and safe on EXISTING DBs: in `init_db()`, detect the
     missing column via PRAGMA table_info and `ALTER TABLE events ADD COLUMN`; then
     create the index. Existing rows get NULL event_id — fine.
   - `insert_event()` uses `INSERT OR IGNORE` (or checks `cursor.rowcount`) and returns
     whether the row was actually inserted (bool), so callers can tell a duplicate.
3. **main.py `ingest_event`:** if `insert_event` reports a duplicate, skip the
   re-scoring/alerting stages and return the normal PipelineResult shape with a
   `duplicate: true` marker — ADDITIVE field only, default false; do not rename or
   remove any existing response field (frontend back-compat).
4. **Tests** (use the conftest.py isolation fixture — note it lives on branch
   `w0-1-test-hardening`; if it is not on your base branch, rebase onto a base that
   includes it or replicate the tiny fixture locally in the new test file):
   - same CloudTrail eventID POSTed twice → 1 row, second response duplicate=true,
     total_event_count stable, live score unchanged between the two responses;
   - two CERT events with identical content and no event_id → BOTH inserted (the
     replay-semantics regression guard — this test failing means the design rule broke);
   - migration: open a pre-existing DB file created with the old DDL, init_db(), insert
     works, index exists;
   - multiple NULL event_id rows coexist (SQLite unique-index NULL semantics).

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q` → all green
- [ ] New tests cover the four cases above
- [ ] `git diff <base> --stat` touches only the four in-scope areas
- [ ] PR body: states the CERT-path-preserved-by-construction argument explicitly;
      evaluator verdict line NO-CHANGE expected (no scoring code touched)

## Risk notes
- LESSONS rules 1, 8, 9, 12 apply. Rule 9: verify base is CURRENT master in the original
  repo (the human is merging branches around now — check, don't assume).
- The user has uncommitted WIP in backend/main.py on the working tree. Your worktree sees
  committed state only; keep your `ingest_event` edit minimal (one guard clause) to keep
  the human's later merge trivial.
- data/events.db on disk must not be touched by tests (rule 10 pattern).

## Escalation triggers
- The events table turns out to be written anywhere else than insert_event → stop, report.
- Frontend code reads the PipelineResult shape in a way an additive field breaks → stop.
- Any test requires changing rarity_scorer/ae_scorer behaviour → stop (out of scope).
