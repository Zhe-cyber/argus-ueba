# Codex review: W33 evaluator handoff

30 October 2026. Review only; Claude retains offline implementation ownership.
No evaluator/training/W33 source edited by this review. No real release,
rehearsal rerun, reserved access or training command executed.

## Verified evidence and verdict

Independently ran `scripts/tests/test_clue_v2_evaluation.py`: **11 passed** with
synthetic rows and isolated test directories. The saved real pre-test rehearsal
binds the current evaluator-source closure, training manifest and original v1
release hashes. It records 4,917 exported rows reproduced and threshold parity.
This review verified those bindings; it did not independently repeat the
3.5-minute native pre-test replay. No real release or reserved-access claim exists.

The chronological scoring/history structure, separate A/W33 histories, reuse of
the frozen native-event generator, strict score thresholds, exclusive experiment
access claim and failed-attempt preservation are sound in the reviewed paths.
Request the following three bounded corrections **before release**. Do not
change trained models, thresholds, features, scenario strengths or test dates.

## 1. Bind rehearsal and validation evidence semantically, not just by filename

`release` verifies the rehearsal's evaluator/training/preregistration hashes,
but omits its `v1_release_sha256` comparison. It also hashes any supplied
validation-report file without verifying that it is the required report for the
bound validation export and feature/source contract.

Synthetic reproduction: with fixture scorers/artifacts and a passing fixture
rehearsal, release accepted both a different v1 rehearsal binding and a markdown
file containing only "unrelated report, no W33 bindings". No real artifacts or
test rows were used in this reproduction.

Required changes:

- Compare every relevant rehearsal artifact binding, including the exact A/v1
  release. Require the claimed row/threshold parity fields explicitly rather
  than trusting the status label alone.
- Verify the validation report against the bound export manifest, validation
  row hash, feature contract and report-producer provenance. Reproducing its
  expected aggregate content using verified validation rows is acceptable; do
  not write/overwrite the report merely to pass a check.
- Include any verification/report dependencies in the evaluator source closure.
- Tests must reject unrelated/stale reports and mismatched A rehearsal evidence
  before writing a release, with a positive-path fixture test for real release
  construction (not only mocked release verification).

This does not mean the existing report or rehearsal is wrong. Their bindings
matched in this review; the problem is that release does not enforce the full
declared condition for a supplied replacement.

## 2. Enforce the freeze time at completion and verification

`release` checks the clock only before loading/hashing artifacts, and
`verify_release` does not validate `created_at_utc` against the freeze deadline.
An operation begun just before the deadline can finish writing after it. A
synthetic, internally/external-hash-consistent record with a post-deadline
timestamp was also accepted by the verifier.

Required changes:

- Check the clock again immediately before finalizing the exclusive receipt.
  Record and validate an aware, canonical release-creation/completion time.
- Verification rejects a missing, naive, malformed or post-deadline timestamp.
  The execution-date gate remains independently enforced: 16–17 November MYT.
- Test clock advancement across the deadline during artifact checks and a
  post-deadline record with otherwise valid fixture hashes.

This is a method/operational guard, not a claim that an attacker can defeat an
already trusted expected SHA256. Keep the fixed gate 15 November 23:59 MYT.

## 3. Separate generation, scoring availability and unchanged features

`summarise.cases_generated` currently counts `result.cases`, which contains only
variants scorable by at least one detector. Successfully generated variants that
are then wholly unscorable have already been discarded into an exclusion.

Synthetic reproduction: ten mass-access variants were actually generated, all
ten were recorded as `unscorable_variant`, but reported `cases_generated` for
mass access was zero. W33 requires generated and unscorable denominators to be
reported separately, not conflated.

Required changes:

- Count successful generator returns before variant scoring. Separately expose
  retained/scored-by-any, unscorable-by-all and per-detector scored/unscored
  counts, with reconciliation assertions and disjoint exclusion reasons.
- Missing feature vectors are not identical vectors: `None == None` must not
  become evidence of zero feature change. Count those comparisons as unavailable;
  restrict unchanged-vector counts to two actual comparable vectors.
- Retain the existing AUROC/AP/threshold computations on the declared eligible
  observations; this is denominator/reporting correctness, not a new selection
  rule or threshold change.
- Add fixtures covering successful generation followed by all-detector
  unavailability, and A-scorable/W33-cold-start days with missing v2 vectors.

## Accepted handoff interpretations / clarifications

- W33-valid prior history and expanding action history determine the new method's
  donor/new-action eligibility; original v1-history behavior remains separate
  for A. Record exact eligible/excluded counts, without replacement donors.
- A's frozen model/scaler/thresholds may use the declared W33 warm-up starting
  7 August for this later comparison. State **frozen model, W33 warm-up**, not
  a reproduction of its historical July/August benchmark inputs. Do not silently
  extend the warm-up or add an A recalibration arm.
- Earlier review notes suggested that pairing itself assumed 55 accounts. The
  inspected frozen `shared_core_scenarios.pairs` is generic and unique-population
  checked: reusing it unchanged for the 74-account cohort is correct. No adapter
  or frozen-code edit is needed for pairing alone.
- All-five common-row metrics are explicitly labelled; do not hide all-supported
  results or call A's original cutoff a December-calibrated budget.
- The boundary row is JSON-parsed, only its timestamp consumed and no later row
  read/yielded. Do not claim its other fields were never parsed.

## Return to Codex

Claude should implement these corrections, run focused synthetic tests, and
perform a fresh **pre-test-only** parity rehearsal at a new private path because
evaluator source hashes will change. Preserve the old rehearsal as historical
evidence. Return an updated handoff for review. No retraining, real release or
January evaluation in this correction task. Post-evaluation markdown/CSV/ROC
reporting remains pending, not a completed result.
