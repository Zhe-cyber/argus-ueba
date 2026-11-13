# W13: start live-method preparation while history collects

Written29 October2026 before implementation. User requests starting earlier.
Start engineering now, without changing the prospective V2 calendar or counting
29 October warm-up as fitting. No model training or threshold selection today.

Implement a read-only V2 history audit against existing actor ledger and actual
connected events. Reconstruct exact plans from frozen V2 profile/hash, scope
AWS account/stack and validate action IDs/fields. Only inspect30Oct-10Nov study
rows; never consume reserved case data. Recheck claimed provider receipts by
unique native ID, requestID, assumed principal, operation, bucket, success and
MY local day; no trust in a status string alone. Bound ledger query, use read-only
consistent per-database snapshots, no event_store import, no AWS calls or writes.

Report each role/day as future/current-partial/usable/incomplete with denominators,
unresolved receipts, verified/planned coverage and reasons. Usable closed dates
require at least90% planned actions, every successful receipt verified, no unknown
claims, no unexpected plans or ambiguous native IDs. Missing rows are missing,
not confirmed inactivity. Keep commissioning/warm-up out of all fitting gates.
Check V2 minimum fitting5usable dates spanning7calendar dates, validation2,
calibration2perrole and pooled12accountdays4roles3dates. These are history gates
only, not a model release decision or proof of statistical sufficiency.

Save versioned private report outside live DB; safe summary contains no raw
identities, requestIDs, IPs or resources. Document why existing manifest-based
exporter / UTC trainer / legacy calibration are not silently reusable for this
MY-time ledger pilot, and the remaining method-annex decisions before5Nov.

Tests: deterministic expected plans, warm-up exclusion, native proof refusal,
unknown/missing actions, timezone/closed-day boundaries, provenance and complete
history-gate pass on isolated synthetic fixtures (never counted as pilot data).
Verify current private history report and unchanged collector/shadow source pins.
No running-task/source/config change. Human merges draft PR.
