# User decision: AWS prospective study re-run as protocol V3

Recorded 31 October 2026 by Claude at the user's instruction, **before any 1 November study data
exists**. For Codex, which owns the AWS study implementation. This is a dated prospective
amendment, not a change made after observing new study data.

## What failed, and what stays on record

The original protocol V2 run cannot pass its release gate. All six roles need at least 5 usable
fitting dates **spanning 7 calendar dates** within 30 Oct–5 Nov (method annex;
`fit_ok = len(fit) >= 5 and span >= 7`). Four roles lost 30 Oct (<90% verified), so their maximum
span is 6 days. 31 Oct then lost all 16 planned actions (0 verified).

The cause is documented in `docs/COLLECTION_INCIDENT_RECHECK_2026-10-31.md`: Modern Standby and
battery operation. The scheduled tasks do not wake the laptop.

The V2 failure is preserved and reported as is. No receipts imputed, no days excluded by hand, no
gate lowered. 31 Oct cannot be used: it is already unusable for every role.

## Decision: V3, same rules, new dates

| Phase | V2 (failed) | **V3** |
|---|---|---|
| Fitting (7 calendar days) | 30 Oct–5 Nov | **1–7 Nov** |
| Validation | 6–7 Nov | **8–9 Nov** |
| Normal calibration | 8–10 Nov | **10–12 Nov** |
| Release / freeze | 11 Nov | **13 Nov** |
| Reserved cases (unchanged case design: first planned GetObject of persona-01/02 → p06) | 12–13 Nov | **14–15 Nov** |
| Final evaluation (after the arrival cut-off) | 14 Nov 20:00 | **16 Nov, after 20:00 MYT on 15 Nov** |

Unchanged:
- every gate (90% per role-day, ≥5 fitting dates spanning 7, all six roles, 2 validation and 2+
  calibration dates, minimum account-days);
- the method annex, generator, seeds, profiles and case strengths;
- the 5% calibration budget and strict `>`;
- receipt auditing, no backfill and no uncertain retries.

Also: the same day-of-week roles for the case slots must be re-checked against the frozen
generator, so each target has a planned eligible GetObject on 14 and 15 Nov. If a target has
none, report the slot as unavailable; do not choose replacement targets or days after seeing
data.

## Required changes (Codex)

1. Write `LIVE_EVALUATION_PROTOCOL_V3` as an amendment record: reason, dates above, everything else
   unchanged. Keep V2 and its failure record.
2. Update the hardcoded date guards (reserved dates, release-only-on date, arrival/evaluation
   cut-off, ordinary-runner refusal dates) in the AWS study scripts. Tests, commit and a controlled
   runtime release must be complete **before 13 Nov** (the V3 freeze). The bound-source rule moves
   with the freeze: last source commit before the V3 calibration start (10 Nov 00:00 MYT).
3. Extend the actor schedule through 15 Nov and the laptop pilot services to about 16 Nov 23:59
   MYT. This does not touch W33.
4. The 1 Nov fitting days are valid **only if collection runs normally**; nothing is backfilled.

## Operating condition (user)

The laptop must be **plugged in, awake, lid open and online, 08:00–20:00 MYT, every day 1–15 Nov.**
One lost fitting day for any role in 1–7 Nov makes the V3 span gate unattainable as well. The user
sets the power settings directly; Codex and Claude change no global power settings without a direct
instruction.

## Unaffected

W33 (released; single test 16–17 Nov), the live compatibility diagnostics, the explanations and the
dashboard work. The W33 and AWS evaluations are independent. The V3 evaluation on 16 Nov must not
use, tune from, or be tuned by W33 results.
