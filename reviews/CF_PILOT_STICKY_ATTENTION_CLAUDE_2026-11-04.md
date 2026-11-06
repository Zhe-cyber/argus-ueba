# Cloudflare machine pilot: "attention required" never clears (Claude → Codex, 4 Nov 2026)

**Owner of the fix:** Codex, who owns `scripts/cloudflare_machine_pilot.py`.
**Claude's checks:** read-only. Nothing was edited or re-run.

## Symptom

`Argus-Cloudflare-Machine-Pilot` reports a last result of **1** on every 5-minute tick, even when
the tick is healthy. At 12:49 MYT on 4 Nov, for example, a tick returned `new_actions` 0 while
today's three due actions were already `provider_verified` and in `events.db`.

## Cause

`tick()` derives its status from the **all-time** action counts:

```python
return {'status':'attention_required' if states.get('claimed_unknown') else 'completed', ...
```

`__main__` then exits with code 1 for `attention_required`.
- `claimed_unknown` rows are never retried, by design ("no backfill or retry of claimed actions").
  Once one exists, every later tick exits with 1 for the rest of the pilot.
- The task status therefore cannot separate "a new problem happened now" from "an old problem was
  already counted". A real new failure would be hidden behind the permanent red flag.

## Stuck rows (ledger `machine-ledger.db`)

| Day | Persona | Claimed (UTC) | Ray ID | HTTP |
|---|---|---|---|---|
| 30 Oct | 03 | 07:49 | none | none |
| 31 Oct | 03 | 06:05 | none | none |
| 31 Oct | 06 | 06:41 | none | none |
| 31 Oct | 04 | 10:09 | none | none |
| 3 Nov | 02 | 04:14 | none | none |

- **3 Nov, persona-02:** the journal shows a `stopped` result with `ConnectionError` at
  04:15:10 UTC, 15 s after the claim. This is consistent with the Wi-Fi drop that morning. The
  request most likely never reached Cloudflare, but that is unproven: there is no ray ID either
  way.
- Also 5 `missed` rows (30–31 Oct). Those are expected outcomes, not the bug.

## Suggested fix (Codex's choice)

Use the smallest change that keeps the fail-closed meaning:
1. Set `attention_required` only when **this tick** created a `claimed_unknown` row, or hit an
   exception. Keep `action_states` in the journal as it is, so the totals stay visible.
2. Optionally, add a separate field such as `historical_unknown` for the total count, for
   reporting.

Also check whether `scripts/github_machine_pilot.py` has the same pattern. It currently reports
`completed`, but only because it has no `claimed_unknown` rows yet.

## Reporting impact (no action needed now)

- Cloudflare evidence (B2 completeness): report the 5 unknown claims as **unknown, not failed and
  not negative**, and give the 3 Nov cause as a connectivity loss.
- Confirm the change does not alter the pinned `source_sha256` contract unexpectedly. The script is
  in `SOURCE_FILES`, so `validate` will reject the running config until its pinned hash is
  refreshed. Plan that step with the fix.

## Status on 4 Nov, 12:53 MYT (for context)

- **Cloudflare:** personas 01, 02 and 05 verified today; 03, 04 and 06 still inside their
  windows. 3 events ingested today.
- **GitHub:** 11:37 action verified; 14:20 and 18:03 pending. Task result 0.
- **AWS V3:** all due actions verified; 218 events ingested today.
