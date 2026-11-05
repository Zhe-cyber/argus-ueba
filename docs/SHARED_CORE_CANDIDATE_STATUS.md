# Shared-core candidate status, 30 October 2026

One isolated shared_behavior_core_v1 AE is trained. It is not independently
evaluated or activated. No reserved CLUE test records were inspected.
Existing CERT71, CLUE10 replay, cloud12, live rules and the frozen AWS study stay
unchanged. Identity links remain an investigation layer, not model inputs.

## Completed

- Exact five-feature projector/reducer, source-specific resource rules and
  time-of-day-only off-hours definition. Chronological k=5 history commits only
  original days; missing resources invalidate a day instead of becoming zero.
- Four deterministic native-event scenario transformations, hash-selected
  disjoint switch pairs and explicit exclusions/caps. No model-guided selection.
- Bounded development ZIP reader that rejects reserved-window access.
- Re-extraction from the inspected prefix: 532 eligible fitting, 183 validation,
  167 normal-calibration account-days, across all 55 fitting identities.
- Training preregistration before the single real run, binding source, protocol
  and feature-data hashes. One CPU AE 5-16-8-3-8-16-5, 100 epochs, best validation
  checkpoint. Fit-only log1p counts/StandardScaler; saved/reloaded scores exact.
- 23 core/training tests pass, including engineering-only training on synthetic
  fixtures. Those fixture runs are not additional real-data candidates.

## Normal calibration diagnostics only

| Nominal budget | AE raw-MSE threshold | AE calibration alerts | Max-deviation calibration alerts |
|---|---:|---:|---:|
| 1% | 1.5837986469268799 | 1/167 | 0/167 |
| 5% | 0.7423310279846191 | 8/167 | 8/167 |

Both use higher empirical quantiles and strict greater-than. The comparator's 1%
cutoff has ties, yielding zero calibration alerts. Report that operating-point
difference; it is not evidence of AE superiority. AUROC/AP remain the headline
metrics once the reserved evaluator is released. These thresholds belong only
to shared_behavior_core_v1, not the older CLUE10 threshold 0.764853.

No AUROC, attack recall, independent normal false-alert rate or live detection
performance is available from this training run. Calibration is not holdout.

## Live input audit

Read-only snapshot at 30 October 2026 01:28 MY; 2,804 stored events. No model
inference, new cloud actions or activation occurred.

| Source | Closed observed account-days | Native accounts | Eligible input days |
|---|---:|---:|---:|
| AWS | 30 | 12 | 0 |
| Cloudflare | 2 | 1 | 0 |
| GitHub | 6 | 2 | 0 |

All are below k=5 prior observed active days per native account. Observed days
include setup/workload activity and are not certified normal baseline days.
AWS additionally has 2,307 events outside the initial reliable resource semantics;
the implementation currently supports the S3 workflow and three resource-free
actions, not every AWS service. Do not call this all-service compatibility.
GitHub/Cloudflare projections have no feature issues in this snapshot, but there
is insufficient eligible history or evidence for a live transfer-performance claim.
Cloudflare's missing allowed field does not prevent native login-kind features;
success/failure is not in this five-feature contract and must not be inferred.

## Private artifacts and provenance

Below data/processed/shared-core-v1/:
- development-features-v2.json: source-bound feature export.
- training-prereg-v1.json: immutable training preregistration.
- candidate-v1/model.pt, scaler.json, manifest.json: dormant candidate and diagnostics.
- live-input-audit-20261030.json: descriptive compatibility snapshot.
- source-snapshots/: exact earlier v1 producer bytes, preserved before the
  GitHub unknown-label correction. CLUE feature rows are unchanged in v2.

Training preregistration SHA256:
c4cd2470a65fbbed4eaa01b2b5b08e19eb72a5ed76ccf491cd3770e15fa95651.
The verified full archive's compressed prefix matches the original inspected
prefix exactly. Full-archive checksum checks did not inspect reserved events.

## Next planned task

Implement the reserved evaluator and rehearse its entire path with engineering
fixtures. Freeze a separate release binding evaluator, fixed protocol, source
archive, model, scaler and thresholds BEFORE opening 11–24 August. Then report
per-scenario AE/comparator AUROC, AP, frozen-budget recall, normal alert fraction,
ties, zero-change cases and unscored/excluded denominators. Do not tune on results.

Afterward complete per-provider applicability decisions and a separate user
release decision for any experimental live display. Continue existing collection
and the AWS study without changing their frozen definitions. No extra dataset,
persona programme, public deployment or automatic live model activation.
