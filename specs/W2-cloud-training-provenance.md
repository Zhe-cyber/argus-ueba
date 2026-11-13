# W2: Reproducible cloud AE training provenance

27 October 2026. Branch codex/w2-cloud-training-provenance, stacked on PR #11.

## Goal

Audit the legacy cloud pipeline and provide an offline, reproducible Colab path
for a replacement 12-feature AE. Preserve the separate 71-feature CERT work.
Do not train/activate a replacement on the present single-day lab sample.

## Approach

Export only completed baseline-run SDK actions independently matched against the
local native CloudTrail database by the existing audit. Reject stale hashes,
failed runs, overlapping event IDs and mixed accounts/stacks. Select actual
stored actor identity; maintain UTC user-day windows and strictly prior-day
history through the frozen shared aggregate_window function. Pseudonymise
identities in the feature export and omit raw logs, IPs, keys and bucket names.
Record included/excluded counts, input/audit hashes and feature code hash.

Train from this versioned export only. Explicit, disjoint UTC-day cutoffs select
normal fitting, model-selection validation and independent normal calibration.
Refuse incomplete days, nonfinite/negative features, invalid contracts, too few
rows/days and degenerate calibration; thresholds/normalisation see no attacks.
Fit StandardScaler on train only; retain existing AE architecture and serving
score formula. Write to a new directory only, with model/scaler SHA256, data,
code/environment provenance and a frozen manifest compatible with actor gates.
Report that small row-count gates are operational checks, not statistical proof.
Evaluation remains a future chronological period; no performance claims here.

## Files and checks

New export/training scripts, isolated regression tests, generated notebook,
audit/runbook documentation and notebook generator only. Legacy pipeline gets
explicit warning comments; no frozen features, runtime scoring or CERT changes.
Test train-only scaling, day isolation, normal calibration independence, source
evidence refusals and artifact compatibility on clearly synthetic unit fixtures.
Run full tests with DATABASE_URL=sqlite-local. Export real local evidence only
to gitignored data/live; never commit real events/model artifacts. Open draft PR;
human merge only, independent review pending. No cloud provisioning or deployment.
