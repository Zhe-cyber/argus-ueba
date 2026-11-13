# L7b — clarification of "planned calls" in the coverage rule (L7 §3)

Written 13 November 2026 (MYT), before the first scenario call. It clarifies wording in
`specs/L7-live-evaluation-rules.md` §3 condition 2; it changes no method, threshold, scenario,
expected tier or reported outcome.

## The ambiguity

L7 §3(2) requires at least 90% of an account's "planned or scripted calls" that day to be
provider-confirmed. On 14 and 15 November 2026 the closed V3 study's reserved runner refuses to
act (its model release was never created), so the personas' ordinary daily plan is generated but
**never executed**: no call is claimed or sent. Read literally against the plan generator, every
persona day on 14–15 November — including all scenario days — would fail condition 2 even though
nothing was lost in collection.

## Clarification

"Planned calls" means calls that an executor actually **claimed** for that account and day: rows
in an executor ledger (the pilot's AWS/Cloudflare/GitHub ledgers, or the post-study persona ledger
from 16 November) plus the calls listed in a scenario run record. A plan entry that no executor
claimed (because no executor ran for that persona that day) is not a planned call for §3(2). Days
where an executor claimed calls are judged exactly as before (unresolved or unknown claims count as
not confirmed).

Consequence: on 14–15 November a scenario account-day is judged on its scripted calls alone, and
ordinary persona days without claimed calls simply have no activity (they are not account-days
under L7 §4). The report lists, for every day, which executors ran, so the reader can see this.

This clarification applies to every account-day in the evaluation window, scenario and normal
alike, and was fixed before any scenario result existed.
