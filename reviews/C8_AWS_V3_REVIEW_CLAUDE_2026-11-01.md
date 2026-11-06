# C8: Claude's read-only review of installed AWS V3 (1 Nov 2026)

**Scope:**
- `aws_study_v3.py`, `reserved_study.py`, `run_reserved_study.py`, `evaluate_reserved_study.py`;
- the case-date branch of `run_persona_history.execute`;
- `live_history_readiness.history_gates`, the partition and gate checks in `train_live_daily`, and
  the actor routing in `local_pilot`;
- `specs/W34-aws-study-v3.md` and `docs/LIVE_EVALUATION_PROTOCOL_V3.md`.

**What was not done:** no Codex-owned file was edited. No provider call, release, training or
reserved access was made. The only store access was one read-only query for ingestion lag.

## Verdict

**No blockers.** I found no defect that needs a bound-source fix before 10 Nov.

## Verified as specified

- **One calendar source.** Exporter, readiness, trainer, freeze and evaluator all take their
  partitions, cases, cut-off and evaluation start from `aws_study_v3`. No stale V2 date remains in
  the bound sources, apart from the consistent duplicate noted in F2.
- **Freeze:**
  - allowed on 13 Nov MYT only, using the real clock with no override;
  - sources must be clean, and untracked files count as dirty;
  - the latest bound-source commit must be strictly before 10 Nov 00:00 MYT;
  - V2 artifacts are rejected through the binding;
  - all six roles must pass, and there are partition minimums;
  - the result is validated after it is written.
- **Reserved execution** re-validates the release before claiming any action. The ordinary runner
  refuses case dates. Plans are regenerated, never taken from the caller.
- **Evaluator:**
  - nothing runs before 16 Nov 00:00;
  - receipts ingested after the 15 Nov 20:00 cut-off make a day unscored, never negative;
  - a target day needs its substitution verified;
  - the unavailable persona-01 slot on 15 Nov is reported as `unavailable_no_planned_target_read`
    and counted in `unavailable_slots`, not as a negative, and it blocks no other role;
  - release, source and bundle drift are re-checked after scoring;
  - the CLI cannot enable synthetic mode.
- **Receipt cut-off margin.** The latest case-day actions are at 17:55 on 15 Nov and 17:22 on
  14 Nov. Add the 15-minute grace and the worst observed ingestion lag of 20.8 min (82 real
  persona events: median 11.6, p95 20.5). That still leaves about 1.5 h before 20:00.
- **Consistency with C2.** My diagnostic coverage policy's ingestion-at-cut-off rule and its
  case-date exclusion agree with the evaluator's semantics. They are not shared code and do not
  need to be.

## Findings (none blocking)

**F1. Gate fragility. Operational; important for the user and X3.**
- Fit requires span ≥ 7 inside a 7-day window, so **1 Nov and 7 Nov are mandatory**.
  Validation requires 2 of 2 days, so **8 and 9 Nov are mandatory** too.
- The release requires all **six** roles. That makes 24 role-days where nothing may fail.
- With 1–5 planned actions per role-day, the 90% rule means **every planned action** that day
  must be verified.
- The generator is structurally feasible: every role has activity on every gate day (tested).
- This is the unchanged frozen rule; I do **not** propose changing it.
- Recommendation: X3 checks each of these four days the same evening, so a failure is known
  immediately rather than discovered on 13 Nov. The user should treat 7, 8 and 9 Nov as the
  laptop days that must not be missed.

**F2. Duplicated case dates. Minor.** `local_pilot.py:200` hard-codes
`('2026-11-14', '2026-11-15')` instead of using `aws_study_v3.CASES`.
- It is consistent today, so no change is needed.
- Fix it only if `local_pilot.py` is being edited anyway before the deadline.

**F3. No-go behaviour on 14–15 Nov. Labelling.** If the 13 Nov release is refused, the reserved
runner fails every tick on 14–15 Nov.
- This is correct, and collection continues.
- Daily reports should label these failures as an expected no-go, not as incidents.

**F4. Commit-time check. Limitation to document.** The check uses the committer timestamp
(`%ct`).
- It proves the honest process, not tamper resistance; committer dates can be set by hand.
- State this in the report's limitations.

**F5. Collector blip near an action. Question for Codex.** Actors are skipped on any tick where
AWS collection fails (`blocked_collection_or_unknown_claims`). With a 15-minute action grace, a
collection outage covering an action's due time causes a miss. On an F1 day, that means a no-go.
- Please state the tick interval and how many retries fit in the grace window.
- No code change is proposed; this is the unchanged safety rule against uncertain retries.

## Independent tests

New file, owned by Claude: `scripts/tests/test_aws_v3_independent_review.py`. 7 tests, all
passing. They cover:
- every role has planned activity on every fit, validation and calibration day, and the fit
  window has exactly 7 days of span;
- losing any one of 1, 7, 8 or 9 Nov for a single role drops `eligible_roles` from 6 to 5;
- the latest case-day action plus grace plus the observed lag stays more than 1 h before the
  cut-off;
- the declared slot availability matches the frozen generator.

The tests are pure: no store, provider or clock dependence.
