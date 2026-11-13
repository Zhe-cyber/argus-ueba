# Spec: L6-ui-followups — learning-period filter, auto-refresh label, recent-findings order

**Branch:** `l1-live-baseline` (continue in `C:\Users\yyzhe\argus-worktrees\l1-live-baseline`, uncommitted) · **Executor:** executor (sonnet) · **Written:** 2026-11-11

## Goal
The queue opens on findings that matter today, the Connections page has no control that appears
to do nothing, and the Overview's recent list follows the queue's ranking.

## Non-goals
No scoring, triage-rule or data change. No `backend/` or frozen-file edits; no edits to existing
tracked files under `scripts/`. No commit/push. Pilot checkouts read-only. Rehearsal stays marked.

## Files in scope
`workspace_next/queries.py`, `case_api.py` (query parameter only), `operations.py` (recent list),
frontend `pages/workspace.js`, `pages/connections.js`, `pages/index.js`, tests in
`backend/tests/test_workspace_queries.py` / `test_workspace_operations.py` (add cases; do not
weaken existing ones).

## Approach (planner-decided)
1. **Learning-period findings.** A finding is "learning-period" when its baseline tier for the
   finding's account-day is `Learning`. Each finding carries `learning_period: true|false`.
   `GET /findings` gains `learning=exclude|only|include` (default `include`, so existing callers
   and tests are unchanged). The counts line gains "N from the learning period".
2. **Queue default.** The page requests `learning=exclude` by default and shows a toggle
   "Learning period (N)" that switches to `only`. When the default view is empty, show
   `Nothing needs review. N findings from the learning period · M on monitoring infrastructure`
   with links to those views. Group-similar, sort and other filters unchanged.
3. **Connections.** Remove the `Refresh` button. Show `Last checked <time> MYT · updates
   automatically every minute`. Keep the 60 s auto-refresh.
4. **Overview "Recent security findings".** Use the same ranking as the queue default
   (non-infrastructure first, learning-period excluded, score desc, newest first), top 5, each
   with account label and score chip. When empty: `No findings need review`.
5. Rebuild both preview frontends (no npm install); restart 8017/8018 (API changed) and
   3013/3014; keep the mirror loop running (restart it only if a module it imports changed).

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures (before: 1082 passed, 1 skipped)
- [ ] `/findings?limit=500&status=Open` (default) returns the same count as before this change; `learning=exclude` + `learning=only` counts sum to it
- [ ] Browser DOM on 3013: queue default shows no `Learning ·` row; toggle shows them; Connections has no `Refresh` button and shows the auto-update text; Overview recent list has no monitoring-infrastructure account
- [ ] Browser DOM on 3014: the first queue row is still the persona-02 High alert; `Simulated scenario` pill present
- [ ] `git diff --stat origin/six-role-commissioning -- backend/ scripts/` → only test files under `backend/tests` that already existed may show additions; nothing else

## Risk notes
Counts-only output; no account numbers, emails, IPs. Temp SQLite in tests. Guard tab-switch
renders. Do not touch ports 8013/8015/3011.

## Escalation triggers
Stop and report if an existing test must be weakened, or the same step fails twice.
