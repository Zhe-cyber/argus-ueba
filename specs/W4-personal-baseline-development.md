# W4: account-conditioned numeric baseline development

Written 28 October 2026, before this candidate is fitted/scored. Branch:
`personal-baseline-development`, based on the PR #19 chain. This is a fixed
development experiment on already-inspected CLUE data, **not** a new untouched
evaluation or the completed live-detector method annex.

## Goal

Implement an isolated account-conditioned statistical companion to the frozen
CLUE AE. Determine whether conditioning the reference centre on account helps
the three existing account-switch development cases, while reporting all
normal alerts, misses and coverage. Keep an otherwise identical population
baseline to isolate the effect of account conditioning.

## Fixed method, decided before candidate results

Use the unchanged ten `clue_behavior_v1` counts and `log1p` preprocessing. Fit
only the frozen fitting split. An account needs at least five distinct active
fitting dates; absent/unknown/ineligible identities yield unavailable personal
scores, never a normal/zero fallback.

For each feature j, the pooled centre is median(log1p(x_j)) across fitting
account-days. The personal centre is the same median within the account.
Both candidates use the **same fitting-only pooled scale**:
`max(1.4826 * median(abs(log1p(x_j) - pooled_median_j)), 0.25)`.
The fixed positive log-space floor handles constant/sparse features and is an
explicit development choice, not a learned parameter or a calibrated noise
model. Scores are the mean of ten absolute scaled deviations from the relevant
centre. Components sum to the total; they are numeric deviations, not SHAP,
attack probabilities or causal explanations. Report the floor and zero-MAD
features. No per-account neural model and no parameter/feature grid search.

Use the frozen population/splits. Validation rows are descriptive diagnostics,
not a method-selection contest. Calibrate each candidate independently at the
normal-calibration 99th percentile, linear interpolation, strict score >
threshold. Keep both candidates regardless of results. Do not change constants,
inequalities or thresholds after viewing the existing switch cases and call a
rerun independent. Any future refinement gets a new version and report.

Compare the frozen AE using its unchanged scaler, model and 0.7648530006408691
threshold. Report personal-only, pooled-only, AE-only and AE OR personal on the
same scorable rows, especially the actual union normal-alert fraction. Quantile
calibration does not guarantee future 1% alert rates. Do not silently install
these thresholds or review tiers into the live dashboard.

## Execution and provenance

- Verify dataset/prefix/manifest/model/scaler and existing switch-plan hashes
  before deserialising the frozen artifacts. Verify ten-feature contract and
  native unswitched rows against the original export, row for row.
- Rebuild switched features from native records, with reciprocal reassignment
  only from 5 August and unchanged earlier rows. Recompute causal prior-action
  history; never swap finished feature vectors. Normal and switched rows still
  use the frozen v1 feature-history policy. Account reference centres/scales
  stay fitting-only and do not adapt on validation/calibration/test rows.
- Reproduce the 191-row/2-alert original normal report and 25 switched days /
  zero original AE alerts before interpreting the companion comparison.
- Write new artifacts into a new private output directory only. Record method,
  source hashes, cutoffs, fitting population, fitting/calibration row digests,
  environment, thresholds, coverage and status `development_only`, activated
  false. Reports use cohort aliases and counts, never raw paths/native IDs.
- Normal controls are counted once in aggregate. The same controls recur
  across cases and must not inflate evidence. Inactive recipient/actor days
  are unavailable/missing, never true negatives. No synthetic idle rows.

## Scope and limits

Files: a pure statistical scorer, a separate native projection helper and
development CLI under scripts/, isolated tests, one documentation report and
CI coverage if required. Do not edit frozen `clue_features.py`, exporters,
training code, original artifacts or their manifests. No raw data/weights in
Git. No AWS, Cloudflare, GitHub activity generation, downloads, live DB writes,
scorer registration, deployment or activation. CERT and legacy-cloud contracts
remain unchanged; a legacy CERT AUROC replay is not this experiment's validation.

The entire 5–9 August window and its three switch pairs are development data.
Native donor resources can imply permissions the recipient did not have; the
numeric companion avoids raw path semantics but does not remove that scenario
limitation. CLUE is one storage service, not a live multi-cloud effectiveness
test. Before later-data evaluation, reserve a new window and freeze a new
protocol/version without inspecting future behaviour for tuning.

## Acceptance

Synthetic tests: account-specific centres change the score for identical
features; references and scales are fitting-only; no same-day/future leakage;
nonfinite/negative/wrong vectors rejected; duplicate/overlapping split dates
rejected; sparse/unknown accounts unavailable; constant features stay finite;
quantile equality and OR availability handled explicitly; native switches
rebuild novelty and preserve earlier dates. Test artifact bindings and input
immutability. Run isolated backend/scripts regression with
`DATABASE_URL=sqlite-local`, never the production .env database. Execute the
bounded local development comparison, retain zero results, and document what
actually changed and any normal-alert tradeoff. No success target or guaranteed
live compatibility is assumed.
