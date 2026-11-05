# Workspace navigation and Connections — 31 October 2026

## Delivered in the isolated preview

URL: http://127.0.0.1:3011/ (existing /workspace still opens the work queue).

- Overview prioritizes open security findings, active cases and sources needing
  review at the operational capture time. Account observations stay separate.
  Missing operational status is Unavailable, not zero healthy sources.
- Primary navigation: Overview, Work queue, Cases, Entities, Connections.
- Entities provides read-only accounts/people, native account provenance,
  approved/revoked/expired mapping evidence, and account-filtered queue pivots.
  An AWS role is not automatically classified as a machine; mappings remain
  analyst-approved. No new identity linking or person risk score was added.
- Connections separates counts in the dated database copy from sanitized
  collector/workload receipts. It shows checks, unresolved outcomes, missed
  actions and pending receipts. Stored volume never becomes a coverage percent.
- Case-to-Connections navigation preserves case ID, provider and UTC time bounds.
  Returning to the case restores these filters; case filters now live in its URL.
- All preview pages retain the isolated-data-copy label. Model scoring remains
  explicitly disabled in this preview; no dummy risk indicators were introduced.

## Operational snapshot policy

The database is the existing dated copy; it was not replaced or merged with the
live store. `workspace_next.operations.capture()` explicitly reads the existing
local sanitized receipts into `operations-snapshot.json` beside that copy. The
API reads this bounded snapshot, never provider credentials or live actor ledgers.
Refresh reloads the snapshot; it does not poll cloud APIs, retry a workload, or
update the copied native event history. Capture time and original check times
are displayed separately. States such as Recent/Stale are **at capture time**.

Only observed/configured AWS, Cloudflare and GitHub appear; the Entra parser does
not become an active connection. Latest event timestamps are compared in UTC,
with an explicit 10,000-row recent-history scan cap. Total stored counts are
database counts; coverage remains unknown.

The captured receipts at 04:47 MYT showed AWS collector/actor checks succeeding,
Cloudflare's existing unresolved outcome and two missed actions, and GitHub
workload status `stopped_review_required` with `ConnectionError`. The main
collector also retained previous failed Cloudflare/GitHub poll outcomes.
Unauthenticated HTTPS probes subsequently reached GitHub (200) and Cloudflare
(404 at its API root). This demonstrates transport reachability only, **not**
successful authenticated polling or workload recovery. No failed receipt was
cleared and no uncertain cloud action was replayed. Review the next authenticated
collector outcomes separately; these warnings must not be hidden as healthy.

## Verification

- 28 backend tests passed across operational snapshot handling, case store/API,
  UTC/timeline/finding queries and existing monitoring/escalation regressions.
- Production frontend build passed; existing build configuration still skips
  lint/type checks, so those checks are not claimed.
- Read-only browser test passed: all five navigation views, dated Connections,
  no invented Entra source, entity-to-account queue filter, case source/time
  context preservation, and mobile Connections without horizontal overflow.
- Full browser case workflow regression passed on the copy, including approved
  cross-provider timeline, stale-edit rejection and unchanged finding disposition.
- Pilot source configuration check passed. The original dashboard, backend,
  collectors, identity writer, models and frozen study artifacts were not changed.

Source: `workspace_next/operations.py`, `workspace_next/app.py`, staged frontend
pages/components and `backend/tests/test_workspace_operations.py`.
Browser check: `scripts/tests/workspace-navigation-ui.mjs`.
Private snapshots/screenshots/receipts remain in
`data/live/workspace-case-preview-20261030-v1/` and must not be committed.

## Remaining before cutover

1. Resolve/review live collection failures using authenticated receipt evidence;
   keep unknown action outcomes distinct from known failures.
2. Finalize legacy-route mapping and the deliberate writer switch, with migration
   and rollback rehearsed on a copy. The new case system is not a second live
   writable investigation store.
3. Separate presentation runtime from the actor pilot expiry. No actor extension,
   model activation, source repinning or live backend restart is implied here.
4. Review the complete workflow and deployment access controls before describing
   it as production-ready. PostgreSQL and a measured usability study remain
   outside the verified claims.
