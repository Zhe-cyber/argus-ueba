# Collection recovery and overnight status — 31 October 2026

## Verified recovery

- Existing authenticated GitHub and Cloudflare collectors each returned exit 0
  at about 05:17 MYT. They inserted zero events; no synthetic/provider action was
  generated. Native polls remain bounded samples, not full-history guarantees.
- Triggered the existing scheduled collector while before 08:00 MYT. Its normal
  receipt recorded completed/success across AWS, actors, audit, GitHub and
  Cloudflare. Actor phase: no_due_actions, new_actions=0. Later 05:21 checks
  retained successful poll results. No poll state was manually forged or cleared.
- GitHub workload's latest check had already recovered to completed with zero
  new actions. No actor schedules, credentials, policies, workload source pins,
  live backend code or experiment/model settings were changed.

The failures were consistent with transient connectivity, but their exact root
cause is not established. Successful current checks do not rewrite prior failures.

## Cloudflare historical uncertainty

Read-only ledger review found one 30 October persona-03 claim without a saved
response ray ID or HTTP status. Queried native Access logs within five minutes
either side of that claim, restricted to its app and client identity. Zero
matching records returned, and the query was not capped.

Absence is not proof that the request never happened. With no exact response ray,
the claim remains unknown under W32. It was not replayed, marked verified, or
changed to missed. Two earlier missed Cloudflare actions also remain historical
coverage gaps. Future dates continue using the existing fixed schedule.

## Preview correction

Connections now separates:

1. Collector check outcome (overnight collection can continue).
2. Outer activity eligibility window: outside 08:00–20:00 MYT is expected idle,
   not a failed run. An open window does not claim an action is running.
3. Today's verified/pending/unresolved/missed outcomes.
4. Previous-day unresolved/missed/pending outcomes.

Workload history is read from the original ledgers using SQLite read-only mode
and stored as bounded sanitized counts in the dated operational snapshot. Native
IDs, credentials and paths are not returned by the operational API. A historical
annotation is allowed only when today's unresolved/pending/missed counts are zero
and the latest workload result specifically reports historical attention. Current
stopped/error states are never hidden by the idle or historical labels.

At the refreshed 05:21 snapshot all collectors passed; all three workload streams
had zero actions today and were outside activity hours. AWS previous-day misses
are now visible too, rather than being masked by a no-due-actions check.

The correction is deployed only to the existing isolated preview on port 3011.
Its native-event database remains a dated copy. The original collector services
and dashboard deployment were not replaced.

## Verification and evidence

- 32 isolated backend/regression tests passed, including MYT boundaries,
  read-only ledger history, historical/current failure separation, and multi-
  provider snapshot sanitization.
- Production build and read-only navigation/mobile browser checks passed.
- Internal recovery receipts: `data/live/collection-recovery-20261031/`.
- Current preview snapshot/browser receipts:
  `data/live/workspace-case-preview-20261030-v1/`.

Do not commit private copies/receipts or publish native account information.
