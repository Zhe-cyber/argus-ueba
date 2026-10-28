# W10 stage 1: normal-only context-score calibration

28 October 2026. Fix before computing the new JS calibration scores. W8's
inspected normal-validation diagnostic informed this design; this is not an
independent preregistration of an entirely unseen experiment. No fresh data,
switch scoring, AE change, backend registration or live activation in this stage.

Reuse the unchanged W8 fitting-only reference and source semantics: equal-day
mean distributions over13-26July, at least five usable dates per required view.
Load its hash-bound JSON with strict validation; do not refit or modify it.
Per-view score is base2 JS divergence between today's distribution and that
account's reference. Include globally unseen categories, with coverage reported.
Unknown/unresolved/no-resource views have no score, never a zero/Low fallback.

Primary candidate J = max(action_mix JS, parent_depth1 JS), requiring BOTH.
This fixed heuristic uses the same divergence units, not calibrated probabilities.
Depth1 is chosen before calibration because depth2 already had six normal
validation maxima; do not choose depth2 solely for higher profile separation.
Report individual action_mix, parent_depth1 and parent_depth2 as fixed controls,
with their own availability/thresholds, regardless of result. Do not silently
replace a failed primary with a passing control.

Calibrate only1-4August normal account-days (169 original rows): linear q99,
strict score > threshold, minimum six scorable days across three accounts per
candidate. Preserve original denominators and statuses. Report exact and within
absolute1e-12 ties, maximum-distance days and actual normal alerts/fractions.
If too little calibration, report insufficient_normal_calibration. If threshold
>= 1-1e-12, report near_ceiling_no_go. That is an operational rejection gate,
not a tolerance change to > or a threshold reduction. Otherwise the result is
ONLY ready_for_development_comparison, never validated/live-ready.

Primary outcome is J's gate, not the best control. No control search, weight
adjustment, feature changes, alert-budget change or >= after results. Reference
must remain unchanged. Save new calibration/report in a new private directory.
Switch evaluation is NOT RUN here; no measured0/25 or attack recall. The next
fixed development comparison would preserve the original AE and report AE OR J
with the actual union normal-alert fraction; those are not executed by this gate.

Verify original W8 report/reference/prefix/manifest/source hashes and the frozen
feature JSON hash before analysis. A separate versioned period projector keeps
the W8 exporter untouched; test parity on synthetic fitting/validation inputs,
then check actual calibration native counts/action/path coverage against the
frozen feature export. No time rewriting, feature-vector swaps or labels.
No source changes to the running laptop pilot; isolated scripts do not alter
its runtime pin. No data, fitted dictionaries, keys or provider records in Git.

Tests: strict JSON/source contracts and immutable reload, JS scores include new
categories, max primary requires both views, unresolved/sparse/no-resource
coverage, chronological/duplicate rejection, calibration minima/ties/near-ceiling
gates, exact primary versus controls, projector parity and artifact binding.
Full tests force DATABASE_URL=sqlite-local. Keep negative results unchanged.
