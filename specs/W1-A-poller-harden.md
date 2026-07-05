# Spec: W1-A-poller-harden — make the CloudTrail poller demo-grade + tested

**Branch:** `w1-a-poller-harden` · **Executor:** executor (sonnet) · **Written:** 2026-07-04

## Goal
`scripts/aws_live_ingest.py` survives restarts without re-posting duplicate events, evicts
its dedup memory correctly, and has unit tests (mocked boto3 + requests — no AWS account,
no network). This is the last offline-testable step before the live demo; when the AWS
account exists (AWS_SETUP.md Tier 0), the poller should work first try.

## Non-goals
- No live AWS calls in tests. No change to the LookupEvents→/ingest data contract.
- No change to backend/main.py `/ingest` handler UNLESS acceptance forces it (see
  escalation — that's ingest-spine, planner + Codex territory, not this spec).
- Not the <60 s EventBridge path (that's W1-B).

## Files in scope
- scripts/aws_live_ingest.py
- scripts/tests/ (new) — test_aws_live_ingest.py; add scripts/tests/__init__.py if needed
  so pytest discovers it alongside backend/tests.

## Known issues to fix (planner-identified from code read)
1. **Dedup eviction is broken (line ~221):** `seen = set(list(seen)[-25_000:])` keeps an
   *arbitrary* 25k IDs, not the most-recent — a `set` has no order. Under a long run this
   can evict a just-seen ID and cause a duplicate re-post. Fix: track insertion order
   (e.g. `collections.OrderedDict` used as an ordered set, or a `deque` of IDs paired with
   the set) and evict the OLDEST. Add a test proving the newest N are retained.
2. **No restart safety:** on restart `seen` is empty and `window_start` resets to
   `now - lookback`, so every event in the lookback window is re-posted. First
   determine whether `/ingest` is idempotent for a repeated CloudTrail `eventID`:
   - SCOUT the `/ingest` handler + `event_store.py` upsert path. If a repeated eventID is
     already deduped/upserted server-side (no history inflation, no double-count), then
     restart re-posting is harmless — document that in the poller docstring and do nothing
     else for this item.
   - If it is NOT idempotent (re-posting inflates a user's event history / scores), add a
     tiny disk checkpoint: persist `{last_window_end, recent_event_ids[]}` to a JSON file
     (path via `--state-file`, default under the repo's data/ or a temp dir) and reload it
     on startup so a restart resumes instead of replaying. Keep it dependency-free.
3. **Testability:** extract the poll-once body (fetch → dedup → post) from the infinite
   `while True` loop into a function like `poll_once(ct, api, state) -> n_posted` so tests
   can call it directly. Behaviour must stay identical.

## Approach
Refactor for #3 first (pure-ish `poll_once`), then fix #1, then resolve #2 per the scout
result. Tests use `unittest.mock`: fake a boto3 paginator returning pages of
`{"Events":[{"CloudTrailEvent": "<json string>", "eventID":..., "eventTime":...}]}`, and
monkeypatch `post_event`/`requests` so nothing hits the network.

## Acceptance checks (runnable as written)
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest scripts/tests -q` → all pass
- [ ] `.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → full suite still green (no regression, no real events.db mutation — LESSONS rule 10 pattern)
- [ ] Tests cover: malformed `CloudTrailEvent` skipped; dedup across two overlapping windows posts each eventID once; eviction retains the NEWEST ids; post_event non-200 + network-error branches; (if checkpoint added) restart reloads state and does not re-post.
- [ ] `python scripts/aws_live_ingest.py --help` still works (argparse intact).
- [ ] `git diff master --stat` touches only scripts/.
- [ ] PR body notes the /ingest idempotency finding (idempotent → documented, or not → checkpoint added) and which known-issue fixes landed.

## Risk notes
- LESSONS rules 8, 9 apply: verify worktree base == current master (must include the W0
  merge) and rebase if behind; commit the moment checks pass.
- Do NOT add a real boto3/AWS integration test — mocks only; CI has no AWS creds.
- Keep the honest latency docstring (2–15 min lag) — do not overclaim.

## Escalation triggers
- Scout finds `/ingest` is NOT idempotent AND making the poller safe genuinely requires a
  server-side change (e.g. an upsert-by-eventID) → STOP, report. That edit is ingest-spine:
  planner routes it to a `heavy` agent + mandatory Codex review as its own spec.
- boto3 paginator shape differs from what fetch_events assumes → stop, report.
