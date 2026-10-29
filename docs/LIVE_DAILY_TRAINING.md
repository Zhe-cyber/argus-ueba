# Compatible closed-day training pipeline

The method is specified in LIVE_METHOD_ANNEX_V1.md before pilot fitting starts.
Implementation: scripts/live_daily_method.py and scripts/train_live_daily.py.
This is a new aws_lab_method_v1 bundle, not replacement legacy model files.
No dashboard, deployment, collector or shadow configuration changes are made.

The primary resource baseline answers whether a role's resource mix differs from
its frozen fitting reference, shrunk toward its peers. The small shared AE answers
whether its numeric counts reconstruct poorly under a pooled fitting model.
Population-resource and volume comparators remain separate. Both behaviours can
be unusual without being malicious; neither method observes intent. The second
registered case has approved analyst context outside the detector inputs.

## Commands once history qualifies

```powershell
python scripts/train_live_daily.py --data <daily-export-directory> --check-only
python scripts/train_live_daily.py --data <daily-export-directory> --out <fresh-private-bundle-directory>
```

The CLI has no synthetic-data mode, clock override, epoch selector or automatic
activation flag. It requires all six roles' actual closed fitting/validation/
calibration history under the annex's stricter gates. Before windows close, a
refusal is expected and leaves no trained bundle. Repeating after new audited
history arrives uses a fresh export/bundle version; never weaken the gate.

Input binding checks include byte hashes, current exporter sources, exact feature
contract, role/date/partition uniqueness, closed MY dates, coverage and categorical
count consistency. Missing/invalid-IP observations are excluded with reasons and
history gates recomputed. Ordinary fit/validation/calibration export cannot include
warm-up, setup or reserved case dates. Data files are local trusted artifacts:
hash consistency is not a cryptographic signature proving human normality.

Eight-count inputs use fitting-only log1p then mean/std scaling. Six frozen
resource references and volume statistics are also fitting-only. The98-parameter
AE trains200 deterministic CPU epochs with fixed settings and selects the earliest
best validation checkpoint. Calibration does not select the model or references.
Full details, equality/tie rules and failure handling are in the annex.

For the planned12-18 normal calibration account-days, the at-most5% empirical
review budget allows zero strict exceedances of the observed maximum. Report
this discrete resolution; it does not establish zero future false alerts. The
report keeps components, constant-score/role-ceiling failures, per-role rates,
combined OR rate and its separate budget decision. It also shows validation
counts against these fixed thresholds, explicitly noting checkpoint-selection
reuse. No raw MSE or context score is converted to a probability or live risk tier.

## Bundle and reload

- weights.pt: weights-only checkpoint, exact new profile and ordered features.
- scaler.json: log1p transform, fitted means/scales and constant feature names;
  zero-variance features use scale1. No pickle.
- references.json: fixed personal/peer-derived probabilities and volume statistics.
- normal_report.json: normal validation/calibration scores and empirical gates.
- manifest.json: input/source/method/contract/artifact hashes, partitions,
  exclusions, environment, selected epoch, parameter count and reload parity.

The trainer reloads and recomputes calibration scores before marking parity true.
Loading requires the caller's expected account/stack scope digest and verifies
both method sources and the exporter/feature source bindings.
The default loader refuses altered artifacts, source/method mismatches, malformed
scalers/references, nonfinite model parameters, unverified reloads and synthetic
test bundles. Tests use explicit synthetic flags and temporary fixture datasets;
they must never be quoted as actual pilot model performance. A failed partial
bundle is inspectable but not qualified by the default loader.

## Remaining before live review priorities

The compatible offline trainer is implemented, but actual pilot weights,
normal-calibrated thresholds and held-out results do not exist yet. Build the
separate receipt-audited scenario executor/evaluator before11Nov freeze, evaluate
the reserved12/13Nov cases and record negative/control outcomes. A compatible
closed-day scoring release needs a separate explicit activation decision and UI
handling for incomplete days. Keep legacy raw shadow inference independent;
this pipeline does not qualify partial-day, human or multi-cloud scoring.
