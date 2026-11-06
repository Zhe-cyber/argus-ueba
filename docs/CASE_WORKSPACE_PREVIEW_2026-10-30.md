# Analyst workflow preview — isolated copy

## Review

Open http://127.0.0.1:3011/workspace. API: loopback port 8015.

This is a working preview backed by a **dated private copy** of the connected
store, not continuously updated live monitoring. Existing dashboard port 3000,
API 8013, collectors, model configuration and legacy investigation writers are
unchanged. The preview shows its isolated-copy label on every workspace page.

1. Review a security finding or switch to account observations.
2. Open its evidence drawer. Read actual recorded rule facts, or inspect the
   legacy-evidence limitation when no exact triggering event is retained.
3. Create a case with an explicit reason, optionally including the finding's
   account as related activity; alternatively add it to an existing open case.
4. Add related accounts or a person with approved mappings. The case timeline
   combines available source activity and linked finding markers.
5. Inspect normalized event evidence, retain selected events, record analyst
   notes and close with an explicitly selected resolution and reason.

## Implemented in this increment

- Server-side category/status/provider/account/time filters and cursor pages,
  including findings older than the previous 100-row UI limit. Query scans are
  bounded at 10,000 candidate rows and explicitly expose caps; counts describe
  matches within that scan, not guaranteed complete source coverage.
- UTC timestamp parsing before comparison/order, exclusive end times, invalid
  timestamp counts, timeline paging and source filtering. UI displays MYT and
  explicitly labels UTC filter inputs.
- Transactional create-from-finding with optional related-account scope. Missing
  references roll back the entire creation; exact retries return original results.
- Approved identity mapping snapshots; current revocation/expiry is surfaced
  without erasing historical case scope. AWS related-account context does not
  establish AWS personal ownership. No inferred person score or auto-linking.
- A case timeline distinguishes linked evidence from related account activity.
  Native IDs/namespaces/digests appear in the evidence inspector. Original provider
  payload is not claimed to exist when its retained artifact has not been resolved.
- Explicit closing reason, version conflicts, audited priority override reason,
  and unchanged linked finding disposition. No automated cloud response.
- Browser command retry keys survive refresh in sessionStorage. Drawer keyboard
  handling includes Escape, focus containment and restoration; no public hosting.

Source: `workspace_next/queries.py`, `case_api.py`, `case_store.py`, `app.py`, and
`workspace_next/frontend/`. The preview frontend is assembled by
`scripts/prepare_workspace_preview.py`; these pages are **not mounted into the
original application**. API startup requires an explicitly marked SQLite copy.

## Verification

- Production Next.js build passed. Existing build configuration skips lint/type
  validation; those checks are not claimed.
- 22 backend tests passed across case workspace, queries and existing monitoring/
  escalation regression coverage.
- Browser journey passed: finding → drawer → new case → normalized event
  inspection → approved GitHub/Cloudflare cross-provider timeline → notes →
  closure. A second browser page's stale edit was rejected and original notes
  retained. Finding disposition stayed unchanged. Zero unexpected browser origins
  and zero page errors; five write requests went only to the marked preview copy.
- Pilot source configuration check passed after implementation.

Private screenshots, browser receipt, database and service logs are under
`data/live/workspace-case-preview-20261030-v1/`. Hidden preview service PIDs are in
its `processes.json`. Browser verification created clearly named test cases only
in that copy; these are not real incident adjudications. Do not publish screenshots
with native account identifiers or emails without redaction.

## Before live cutover

Complete the migration routing/writer switch, Connections and final navigation,
review operational deployment and perform a full cutover rehearsal. PostgreSQL
remains unverified. Existing API actor labels are analyst-supplied text, not
authenticated user identity. The local preview does not prove a production
multi-analyst authorization model or improve the detector's validation status.
Study freeze/evaluation dates and the separate competition runtime plan remain
unchanged.
