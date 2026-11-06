# W21: Reserved AWS scenario execution and evaluation

29 October 2026, before fitting, validation, calibration or reserved native cases. Implements protocol V2 and method annex v1 without changing generator parameters, normal partitions or decision thresholds. User commits/pushes manually.

## Locked design
- Targets persona-01/persona-02 on 12 November (unannounced) and 13 November (approved control). Replace each target's chronologically first planned GetObject with the existing p06 fixture. Retain action ID, role, operation, time, count, budget and every other scheduled action.
- Pure offline date planner supports tests; execution CLI has no date/clock/target override. Reuse existing claim-before-I/O runner/ledger, SDK and HTTP budgets, no retries, non-root identity, scoped trail and fixtures.
- Ordinary executor refuses reserved dates. Local pilot routes those dates to the reserved wrapper. A missing or invalid release fails before claims/provider calls, even for remaining ordinary actions on those dates.
- Write-once release can be created only on 11 November MY from a real compatible reload-verified bundle with all-six-role history gates and a passing primary calibration gate. Recompute calibration from frozen normal scores; do not select a replacement method. Bind bundle artifacts, protocol/annex/feature/export/method/execution/evaluation sources and scope. Require selected source files committed with no changes at freeze. Local release is operator provenance, not independent cryptographic attestation.
- Never auto activate or install the bundle. Keep live account risk Unknown.
- Final evaluator cannot run before 14 November 20:00 MY. Read-only ledger/native snapshots; cutoff applies to native ingested_at, not just native eventTime. Late/missing/ambiguous/failed/unclaimed records are counted separately and never become normal negatives.
- Reconstruct expected substituted plans and independently verify exact account/action/resource/request/principal/assumed-role ARN/success/native ID, time bounds and duplicate receipts. Ledger status alone is insufficient. Score only closed role-days with >=90% verified planned actions, no unresolved claims, and complete valid IP context. Require the target substitution's verified receipt for target-case eligibility.
- Score using the frozen bundle only; strict greater-than component thresholds, primary and fixed OR gate. No refitting or threshold changes. Approved-change context never enters feature extraction/inference. Four target account-day slots remain the reporting unit, with all six role/day coverage shown. Report no-go and unknowns, not attack accuracy.
- Synthetic bundles permitted only through explicit internal test arguments, never CLI or real release.

## Implementation scope
New scripts/reserved_study.py, scripts/run_reserved_study.py, scripts/evaluate_reserved_study.py; minimal guarded changes to run_persona_history.py and local_pilot.py; tests and runbook/update notes. Pause owned runtime before editing pinned files, inspect/preserve config, refresh ONLY reviewed pins, verify health and restore collection after tests. No cloud calls/reserved execution now.
