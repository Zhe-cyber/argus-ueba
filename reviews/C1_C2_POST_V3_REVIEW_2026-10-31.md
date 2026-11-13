# C1/C2 review after AWS V3 cutover

31 October 2026, Codex. Read-only source review and synthetic tests only.
Claude-owned implementation was not edited. No real inference, W33 fit,
release, reserved evaluation or live activation was performed.

## Verdict

The three prior C2 blockers are addressed: reserved case rows are partitioned
before ordinary-plan validation; an aware shared ingestion cutoff is enforced;
and malformed/null account keys cannot create a persona mapping. The wrapper
continues to use the unchanged native matcher and its own live-only date scope.
V3's new fitting windows do not silently redefine C2's diagnostic history start.

C1 keeps scoring and explanation on the same start-of-day state, applies the
coverage policy to both scoring and history, and labels scores as experimental
raw reconstruction errors with no risk tier or alert. Native IDs and observed
event counts make the coverage boundary inspectable.

**Verification:** 30 tests passed against the installed V3 dependencies:

```text
scripts/tests/test_live_coverage_policy.py
scripts/tests/test_live_receipts_clue_v2.py
scripts/tests/test_clue_v2_result_package.py
```

The first two are the 21 C1/C2 tests. The additional nine test C3 packaging on
synthetic evaluator-shaped output; they do not execute the reserved test.

## Handoff

Claude may regenerate a new live diagnostic receipt with the installed V3
dependency hashes; preserve earlier outputs. No new scored day is promised.
AWS study source bindings exclude C1/C2 and their tests. Exact installed hashes
are published in `AWS_V3_RUNTIME_RELEASE_2026-10-31.json`.

For dashboard consumption, an absent receipt remains unscored, never Low. A
receipt cannot prove complete collection outside the planned persona actions.
Reject stale/mismatched model, policy, projection and source hashes before
displaying a diagnostic. Do not translate CLUE thresholds into live tiers.

One non-blocking display detail: `history.prior_accepted_days` lists all previously
accepted dates. Feature 5 uses expanding prior usable history; features 6–9 use
the last <=28 usable active days. Show those scopes separately, or ask Claude for
explicit expanding/rolling provenance fields in a versioned receipt update.
Do not describe the rolling window as the complete history for every feature.
This clarification was checked against `clue_v2_features.FEATURE_CONTRACT` on 1 November;
it changes no score and requires no AWS bound-source edit.
