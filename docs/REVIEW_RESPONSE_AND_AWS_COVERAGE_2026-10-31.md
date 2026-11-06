# Review response and AWS coverage audit — 31 October 2026

## Critical result: the current all-six-role AWS release gate cannot pass

Read the frozen V2 protocol, method annex and existing read-only readiness
implementation. Verified each action against the native receipt checks, not just
its ledger label. Counts as audited before today's activity window:

| 30 October role | Planned | Native verified | Missed | Coverage | Day eligibility |
|---|---:|---:|---:|---:|---|
| persona-01 | 3 | 1 | 2 | 33.3% | Incomplete |
| persona-02 | 2 | 2 | 0 | 100% | Usable |
| persona-03 | 4 | 2 | 2 | 50% | Incomplete |
| persona-04 | 2 | 2 | 0 | 100% | Usable |
| persona-05 | 4 | 3 | 1 | 75% | Incomplete |
| persona-06 | 4 | 1 | 3 | 25% | Incomplete |

The 15 recorded misses comprise **7 warm-up misses on 29 October and 8 fitting
misses on 30 October**, as the reviewer suspected. No unresolved fitting claims
were found for that day. The eight missed slots were 11:28, 11:53, 11:57, 12:17,
12:31, 12:51, 15:10 and 15:22 MYT. They have no attempted_at/request receipt.

Windows Kernel-Power event descriptions record Modern Standby starting around
11:25 MYT, additional brief transitions around 12:57 and exit at 15:49 with reason
Lid. These overlap the missed slots and support an availability explanation.
They do not establish the exact cause of every miss; a Wi-Fi failure alone is
not the only supported explanation. No power settings were changed.

The annex requires every role to have at least five usable fitting dates spanning
seven calendar dates. Fitting is 30 October–5 November. For the four incomplete
roles, the earliest possible usable date is now 31 October, so even perfect future
delivery gives a maximum six-calendar-day span. Therefore the **existing all-six
release gate is unattainable**, not merely pending. Late reconciliation cannot
repair a missed action for which no call was attempted. Do not backfill, change
the day boundary, lower 90%, or reinterpret the span to obtain a passing release.

This is a no-go for the specified AWS reserved-study release under unchanged
rules. It does not invalidate the ingestion pipeline or the separate W33 offline
experiment, and does not require stopping ordinary collection. Any replacement
study requires an explicit prospective protocol decision; none was made here.
No release/model training or reserved evaluation was attempted.

Internal read-only audit artifacts:
`data/live/reviewer-audit-20261031/aws-readiness.json` and
`missed-fitting-actions.json`. Frozen protocol/annex/runner/ledger were untouched.

## Dashboard corrections

1. **Timezone:** confirmed rarity uses Mon–Fri 07:00–19:00 UTC, while the older
   AE feature window is deliberately distinct. Display title now says outside
   the UTC rule window; the drawer states its exact window and available native
   event time in UTC. Created timestamps remain labelled MYT. Original alert
   title and severity stay unchanged; no detector window was modified.
2. **Noise/context:** added server-side Service/workload versus Other/unclassified
   filtering, account kind and limited-observed-history cues. Service-linked AWS
   roles and the controlled role names require native issuer-ARN evidence; names
   alone do not establish machine identity. First-five-observed-day cue is a
   display heuristic, not a model eligibility rule or suppression policy. No
   machine account is automatically cleared or downgraded. The column now says
   Recorded severity rather than suggesting it is a newly computed priority.
3. **Names/presentation:** queue and cases prefer readable account labels while
   preserving internal keys for links. Presentation mode visually masks email,
   12-digit account IDs, full acct keys and IPv4 addresses and blocks API writes
   from the preview client. It is deliberately read-only. Native API responses,
   browser URLs, underlying data and exports are **not anonymized**. Review every
   public capture; this is visual assistance, not an access-control boundary.
4. **Resources:** bounded JSON/literal parsing presents structured resource values
   using proper JSON. Original stored resource strings and native payload digests
   remain unchanged. Arbitrary expressions are not evaluated.
5. **Status age:** checks include age before the operational snapshot. A snapshot
   is not presented as continually fresh “two minutes ago”. Idle, previous
   unresolved outcomes and present collector review states remain distinct.

These changes are deployed only to the isolated preview on port 3011. Live
collector code and its runtime pins were not changed.

## Verification

- 36 isolated backend tests passed.
- Production frontend build passed (existing lint/type skip configuration remains).
- New read-only browser check passed for UTC wording, service/workload filters,
  readable context and visual masking with expanded case details. Recorded alert
  IDs, original titles, severities and statuses were unchanged.
- Existing full case workflow browser regression passed, including approved
  cross-provider timeline, stale-edit rejection and closure without rewriting
  finding disposition. These writes occurred only in the marked test copy.

Private browser receipts/screenshots are in the existing preview artifact folder.
User commits/pushes remain manual; no commit or deployment to the live app was made.
