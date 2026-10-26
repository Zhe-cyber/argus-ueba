# W3 cloud live mode: Codex self-review

Reviewed 2026-10-27 against master 0d45b4e. This is the author's Codex self-review,
not an independent second reviewer or a production-readiness certification.

## Result

No remaining blocking correctness finding identified within this slice. Keep the
PR draft until CI and an independent review are complete; only the user merges.

## Corrections made during review

- Preserve model-unavailable values as SQL NULL and Unknown risk in live mode;
  do not silently turn them into Low-risk zero scores.
- Separate local live runtime state from the tracked benchmark investigations file
  (60 records). Live mode uses data/live/ by default.
- Return null for live ground-truth fields, hide research-model cards on cloud
  details, and disable unverified seeded attribution/AI routes in live mode.
- Exclude score-only seeds and CERT-only accounts from live user counts/details.
- Isolate investigation JSON in the test fixture, not only the event database.
- Remove unsubstantiated calibrated-comparability language from dashboard tooltips.
- Update Next.js and matching ESLint config to 14.2.35, the current patch in the
  existing 14.2 line. This is not a complete dependency/security audit.

## Verification

- Baseline: 80 passed.
- Final backend + collector regression suite: **93 passed** on Python 3.14.4 using
  sqlite-local, isolated temporary state and mocked inference in workflow tests.
- Actual startup subprocess: live mode starts against missing benchmark data and
  returns no tracked benchmark investigations, with independent temporary state.
- Frontend production build passes on Next.js 14.2.35. The existing configuration
  skips lint/type checks; build success is not a lint/security verdict.
- Browser check on the actual localhost build: labelled synthetic AWS event,
  unavailable model -> Unknown account, null score, no benchmark source filter,
  one AE score card, disabled AI guidance, and recorded source-tagged activity.
  Screenshots: live-dashboard.png and live-account.png (synthetic records only).
- git diff --check passes.

No model feature order, training parameters, numeric inference algorithm or
threshold value changed. No new model accuracy result is claimed or rerun needed
for unchanged feature semantics; only unavailable-result handling changed.

## Remaining release blockers

Authentication/authorization; per-provider/account identity keys; provider collectors
and durable dedup/retry integration; faithful live AE explanations; live calibration;
observed cloud detection quality; independent review. A live event payload remains
client-supplied until collector identity/provenance is enforced. PostgreSQL requires
a separate fresh live database; this slice does not migrate mixed historical rows.
The new PR CI runs must be checked remotely before merge. No deployment performed.
