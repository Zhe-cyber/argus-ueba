# Spec: L3-infrastructure-context — rank monitoring infrastructure below workloads; collapse feed repeats

**Branch:** `l1-live-baseline` (continue in `C:\Users\yyzhe\argus-worktrees\l1-live-baseline`, uncommitted) · **Executor:** executor (sonnet) · **Written:** 2026-11-11

## Goal
The first rows of the queue, the Overview top-5 and the live feed show workload/user accounts, not
the system watching itself. Scores are unchanged and stay visible.

## Non-goals
No change to baseline scoring, weights, tiers or alert creation. No `backend/` or frozen-file edits.
No commit/push. Pilot checkouts read-only. Nothing is hidden permanently: every list has a way to
show infrastructure accounts.

## Files in scope
`workspace_next/finding_context.py`, `queries.py`, `baseline_score.py` (summary flag only),
`app.py`, new `workspace_next/system_accounts.py`, frontend `pages/index.js`, `pages/workspace.js`,
`pages/entities.js`, `components/LiveFeed.js`, new `backend/tests/test_system_accounts.py`,
`docs/LIVE_BASELINE_SCORE_V1.md` (one paragraph).

## Approach (planner-decided)
1. `system_accounts.is_infrastructure(account_label, account_kind, source)` is true when any holds:
   - `account_kind == 'service'` (provider service principals, e.g. labels ending `.amazonaws.com`);
   - AWS service-linked role: label starts with `AWSServiceRole`;
   - the label is listed in `system-accounts.json` in the preview root:
     `{"basis": "declared: Argus collector and lab runner identities", "labels": [...]}`.
     Create that file with the collector's read-only identity and the lab actor runner — identify
     them from the data (the account that issues the 5-minute `GetCallerIdentity` preflight; the
     account whose label ends `-runner`). If either cannot be identified unambiguously, leave it out
     and report. Missing file → only the first two rules apply.
2. Every finding, summary row, group member and feed event carries `infrastructure: true|false`.
3. Triage: an infrastructure account never gets `review_first`; it gets a new label
   `Context: monitoring infrastructure` (add to `TRIAGE_LABELS`, counts line and the Triage filter).
   Precedence: infrastructure → this label; else existing rules (baseline High → review first).
4. Queue default sort: `(infrastructure asc, score desc, created desc)`. A toggle
   "Show infrastructure first: off" is not needed — the Triage filter already isolates them.
5. Overview "Highest baseline scores today": non-infrastructure accounts only, with a line
   `N infrastructure accounts not shown · view` linking to `/workspace?triage=infrastructure_context`.
6. Live feed: collapse consecutive events with the same `(account_label, action)` within a source
   into one line `… × N · latest received Ns ago`. Infrastructure events render in muted text.
   The per-source counters keep counting everything.
7. Entities → Accounts: an "Infrastructure" chip beside those accounts; no reordering.
8. Tests: the three rules; file missing; triage precedence (infrastructure + High → infrastructure
   label, not review first); sort order; feed collapse (3 identical in a row → one line × 3;
   A, B, A stays three lines).
9. Rebuild the preview frontend (no npm install), restart 8017 and 3013 only; keep the mirror loop
   running (restart it if the code it imports changed).

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures (before: 1063 passed, 1 skipped)
- [ ] `git diff --stat origin/six-role-commissioning -- backend/ scripts/` → empty
- [ ] `/findings?limit=500&status=Open`: first non-infrastructure row precedes every infrastructure row; `triage_counts` has the new key and the counts sum to the total
- [ ] Overview in the browser: top-5 has no infrastructure account; AWS feed shows the heartbeat as one collapsed line
- [ ] Copy still has 0 events ≥ 14 Nov MYT; pilot checkout status unchanged except spec files

## Risk notes
Same as L2: pilot read-only, counts-only output (no 12-digit numbers, emails, IPs), temp SQLite in
tests, guard field access on tab switches in `entities.js`.

## Escalation triggers
Stop and report if a rule would classify any `argus-ueba-actors-persona-0N` role or any Cloudflare
service token as infrastructure; if a step needs a `backend/` edit; if the same step fails twice.
