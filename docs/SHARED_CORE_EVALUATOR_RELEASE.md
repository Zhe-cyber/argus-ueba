# Shared-core evaluator release protocol, 30 October 2026

This is a pre-test operationalisation of the training-frozen shared-core method.
No model retraining, scenario changes, new datasets or live activation.
The 11–24 August 2017 UTC reservation is unchanged. Training preregistration and
its model/scaler/manifest/documents remain immutable and available for audit.

## Validation and independent review

The previous build's 26 core/training/audit tests pass. Claude Code performed a
source-only, tool-disabled review at the user's request. It found no method/data
leakage blocker. It approved a pre-test calibration/inference numerical-path
alignment, conditional on regression tests, explicit freezing and retention of
the original thresholds. Private original review: data/live/shared-core-review-v1/.

An evaluator review initially flagged missing scenario/reader hash binding. The
omitted review context was training.SOURCE_FILES: it already includes both and
the feature extractor; candidate_scorer verifies those hashes before access.
A regression test proves a scenario edit is rejected by that existing chain.
The reserved release additionally binds these dependencies explicitly, so the
dependency chain is visible without relying on transitive training checks.
Rehearsal dates must equal 5–9 August; switch reports separate donor-only and
unpaired-account counts. These changes do not alter scenario selection or scores.

Review also found that GitHub/Cloudflare action issues could be masked by a
simultaneous missing resource. The frozen CLUE path is unaffected. Rather than
editing training-frozen code, shared_core_live_guard.py gives unknown/default
action issues priority and prevents them entering live novelty history. Live
diagnostic counters report the prioritised issue, not every co-occurring defect.
This guard is not a new live model or activation. Cosmetic duplicate quantile
computation in the frozen trainer is intentionally unchanged.

## Numerical calibration supplement, before test access

Original calibration was a 167-row float32 forward batch; chronological evaluator
inference is one row at a time. Independent preflight found maximum raw-MSE
difference 3.5762786865234375e-07 from CPU reduction order. Applying the original
numeric cutoff to single-row inference gives 2 calibration alerts rather than 1.

Authoritative evaluation path: CPU float32 single-row model forward, then mean
squared error along the feature dimension. Use this same path on the SAME 167
normal calibration rows; apply the SAME higher quantile and strict-greater rule
at nominal 1% and 5%. This is not attack-informed threshold tuning. Weights,
scaler, data selection, architecture, scenarios, nominal budgets and quantile
policy are unchanged. No decision epsilon or random tie-breaking is introduced.

| Budget | Original training AE cutoff | Canonical inference AE cutoff |
|---|---:|---:|
| 1% | 1.5837986469268799 | 1.5837987661361694 |
| 5% | 0.7423310279846191 | 0.7423310279846191 |

The comparator cutoffs are unchanged. Canonical calibration alerts remain AE
1/167 at 1%, 8/167 at 5%; comparator 0/167 and 8/167 respectively, with ties
reported. The 30-October candidate-status document records the original training
numbers; this supplement supersedes those numbers for this evaluator, without
silently editing the old document or manifest.

The release records BOTH original and canonical thresholds and the numerical
diagnostics. Batch-path calibration must still reproduce original thresholds
exactly, proving checkpoint/scaler integrity. Single-row saved-model regression
must be exact. A 1e-5 calibration batch-vs-single discrepancy check is an
engineering failure guard only, NOT an alert margin. Larger discrepancy blocks
release instead of accepting changed model behavior.

## Rehearsal before the reserved window

Run the full native ZIP reader, feature/history reducer, scenario generation,
model/comparator scoring and metrics engine on the already-inspected 5–9 August
development window. Require complete native-history/feature parity with the
original prefix export through 9 August. Report engineering status and case/
exclusion counts only, not independent benchmark performance. Do not retune.
The rehearsal stops at the first 10-August boundary row; it cannot read 11 August.

## Reserved release and access receipt

Freeze evaluator/tests/this protocol hashes, model/scaler/training manifest,
training preregistration, development feature export, successful source-matched
rehearsal, and the official archive SHA256 in a new release file. Freeze canonical
calibration and numerical-path details in that same release. Invocation supplies
the expected release SHA256; changed files or a wrong official archive fail
before opening its JSON member. Model, scaler and manifest paths must agree.

The evaluator saves an access-start receipt before native iteration. Unexpected
failures afterward are marked failed_after_access_started; never claim a clean
untouched test after a partial failed access. Do not silently repair and present
such a rerun as untouched. No model/scenario changes on the test outcomes.

Original account-days update chronological history only after all variants. Valid
normal days are negatives; injected cases are positives; excluded/unscorable
cases and unobserved account-days are not negatives. Feature-identical switches
remain positive cases. Every scenario uses all eligible untouched normal days as
its negative set. AUROC and average precision are primary; fixed-budget recall
and observed normal alert fraction are secondary. No pooled headline is required.

Sort and validate native IDs/days and require one post-window boundary row to
establish the final day's closure. That decodes one first 25-August boundary row;
25 August must not subsequently be described as wholly uninspected. Stop there.
UTC days with reversals, malformed records or absent closure fail rather than
being silently clipped, reordered, scored Low or treated as attack misses.

## Interpretation

Semi-synthetic counterfactual account-days, based on publisher-described normal
storage activity. Not real attack accuracy, verified human takeover, general
multi-cloud detection performance, or numerical superiority over CERT. AP is
prevalence-dependent; account-days and variants are dependent. Eligibility/cap
exclusions and one-day original-history updates limit generalisation.
Existing AWS study, collectors, identity mappings and live scores are untouched.
