# Case workspace foundation — staged, not deployed

## Implemented

- Standalone case IDs; multiple cases per account and multiple account/finding/
  event associations per case. References snapshot source evidence at link time.
- New / In progress / Closed lifecycle, separate resolution and mandatory closing
  reason. Case priority is an explicit workflow field, not a model risk score.
- Compare-and-swap version checks, transactional writes, append-only application
  audit and command retry receipts. Reusing a request key with different content
  conflicts. Closed cases cannot be silently edited or reopened.
- Normalized evidence inspector includes native ID, source namespace, digest,
  row reference and timestamp. Original provider payload status is unresolved;
  no reconstructed JSON is advertised as original evidence.
- Explicit finding associations do not prove which events triggered a historical
  alert. Linking or closing a case does not modify finding disposition, identity
  mappings, event evidence, models or benchmark labels.
- Atomic retry-safe legacy import preserves the complete original record,
  including old status/timestamps/history/notes/owner/suggestion. Imported cases
  start New/unreviewed in the new workflow; their original status stays in the
  legacy provenance rather than becoming a new confirmed-incident decision.

## Files and API

Inactive package: `workspace_next/case_store.py`, `workspace_next/case_api.py`.
It is outside the pilot's pinned backend tree and is not registered by main.py.
The schema is additive in the event database when explicitly initialized.

| Route | Contract |
|---|---|
| POST /cases | title, owner, actor, request_key; optional priority/notes |
| GET /cases | limit 1–100; next cursor uses before_time and before_id together |
| GET /cases/{id} | fields, links, legacy provenance, audit history |
| PATCH /cases/{id} | expected_version, actor, request_key, allowed changes |
| POST /cases/{id}/links | expected_version, actor, request_key, kind/target/reason |
| GET /events/{id} | normalized source evidence only |

Conflict is HTTP 409, missing record 404, invalid input 422. Request keys must
remain stable across retries. A retried write returns its original response;
fetch the case afterwards if the latest state is needed.

## Verification

16 tests passed: eleven new foundation/API/copy-rollback tests plus five existing
monitoring/escalation regression tests. Checks cover racing writers, lost-response
retries, mismatched request-key reuse, missing evidence rollback, closure guards,
multi-source associations, stable keyset pagination and exact legacy preservation.

The command `scripts/rehearse_case_migration.py` opens its source SQLite database
read-only, creates a fresh backup and working copy, imports the legacy snapshot,
verifies existing table hashes, retries the import and restores the copy.
Real-store copy rehearsal passed: **one legacy record imported; existing table
content unchanged; restored copy matched backup**. Private artifacts and receipt:
`data/live/case-migration-rehearsal-20261030-v2/`. These contain private evidence
and must not be committed or used on public posters.

Pilot configuration check passed after staging. The most recent completed tick
was successful; no current source-pin failure was found. No live restart, writer
switch, stored-record migration or model change was performed.

## Remaining before cutover

Build the queue/drawer and case timeline, attach approved identity provenance,
add the final legacy-route mapping and writer switch, and rehearse the complete
workflow. Priority overrides already require an audited change_reason.
Validate PostgreSQL separately before claiming support. The current rehearsal
does not prove an online migration while legacy writers remain active.
