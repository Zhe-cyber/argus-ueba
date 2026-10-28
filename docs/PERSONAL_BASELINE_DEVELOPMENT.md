# Account-conditioned numeric baseline: development result

28 October 2026. Implemented on the PR #19 chain in the separate
`personal-baseline-development` branch. Fixed method: spec commit `9747049`.
This is an offline companion experiment, **not a newly trained AE, live model
activation, untouched test or demonstrated solution to account compromise**.

## Method and reason

The frozen CLUE AE scores population behaviour and missed the three original
reciprocal account-switch cases. This experiment isolates one change: give the
same ten numeric features a different fitting reference centre per account.
An otherwise identical pooled baseline controls for this change.

Both references use log1p counts, fitting-only medians and the same pooled
feature scales, `max(1.4826 * pooled MAD, 0.25)`. The score is the mean absolute
scaled deviation. Personal centres require five distinct active fitting dates;
unknown/sparse accounts return unavailable, never zero. The shared scale is an
intentional control: this is centre conditioning, not a full model of each
account's individual variance, sequence, resource preference or peer group.

Fit 605 rows from 55 fitting-selected identities. Calibrate each new reference
independently on 169 separate normal-calibration account-days at q99, linear
interpolation, strict `score > threshold`. Validation is descriptive only;
its alert counts, if inspected in the JSON, apply the later calibration
threshold retrospectively and are **not prospective validation performance**.
No switch result selected the method, scale floor, feature set or threshold.

The original AE, weights, scaler, ten-feature extractor, source dataset,
native prefix and switch plan stayed unchanged. Hash checks and native rebuilds
reproduced the original AE's 2/191 normal alerts and 0/25 switch-day alerts.
The new reference and calibration artifacts were saved before case scoring.

## Results: existing development data only

| Detector/rule | Publisher-normal days flagged / 191 | Switched account-days flagged / 25 | Cases with any switch-day alert / 3 |
|---|---:|---:|---:|
| Frozen AE | 2 (1.05%) | 0 | 0 |
| Pooled numeric reference | 1 (0.52%) | 0 | 0 |
| Account-conditioned numeric reference | 1 (0.52%) | 0 | 0 |
| Frozen AE OR account-conditioned reference | 2 (1.05%) | 0 | 0 |

All 191 normal and 25 switched development rows were scorable by all methods.
The frozen population is 55; only 49 identities have normal activity in this
window. Missing activity is not a true negative. The 25 projected days span
six accounts and three disjoint pairs; cases have 8, 9 and 8 active days.
Original normal controls are counted once in the aggregate, even though the
case-local control summaries repeat overlapping subsets.

On calibration, each method individually flagged 2/169 normal rows. The AE OR
personal union flagged 3/169 (1.78%). The union rate is measured, not assumed
to remain 1%, and calibration quantiles do not guarantee future rates.

Thresholds have different units: AE raw MSE 0.7648530006408691; pooled absolute
deviation 1.616509521210565; personal absolute deviation 1.7778896160376354.
Do not compare these raw numbers as calibrated probabilities or display them
on one risk-percentage scale.

Personal scores exceeded the pooled-reference scores on 22/25 switched days,
but no day exceeded its independently calibrated threshold. The largest
personal score reached 0.8404 times its threshold. This is a diagnostic
observation, not evidence of successful detection or a reason to lower the
threshold. The personal normal alert was dominated by permission-change,
new-action and sharing deviations. These are score components, not SHAP or
proven causes of malicious behaviour.

The result does not establish that personal baselines cannot work. It shows
that this fixed ten-count centre-conditioning candidate did not repair the
gap on these development cases. No detector winner, replacement or live
deployment was selected from this experiment.

## Representation check and next model work

The added synthetic test
`test_resource_only_change_can_be_invisible_to_the_frozen_ten_counts` changes
an account's accessed path while preserving event/action/time/count patterns.
Both native projections produce identical ten-feature vectors and identical
personal-reference scores. `unique_paths` measures how many distinct paths
occurred, not whether this account has previously accessed them.

This matters for the registered future live resource-substitution scenarios:
their counts and timing are deliberately held constant. A count-only model
cannot detect a resource change if the feature vector does not represent it.
More layers or attack-labelled threshold tuning cannot recover discarded
information. This counterexample is about observability, not a proof that all
three original switch cases had identical features.

Next work is a **separately versioned source-aware feature contract** that
represents action/resource familiarity relative to strictly prior account
history, with coverage and unknown-resource handling. Check resource semantics
first: a literal path is not necessarily a globally unique object or an ACL
ownership assertion. In live AWS data, the current normalizer stores a bucket
resource; object-key familiarity is not available by assuming the key was kept.

The earlier raw path-novelty diagnostic is also negative evidence: its normal
q99 is 1.0, so a strict bounded `fraction > 1.0` rule cannot fire. Do not quietly
switch to >= or promise that adding this scalar will solve the problem. A
small future candidate set and its normal-only calibration must be fixed
before its next comparison; keep this report and all misses.

The entire 5–9 August window is inspected development data. The existing prefix
also includes the **partial 10 August capture**, so a future untouched test
must start after that inspected capture, not simply be renamed 'after 9 Aug'.
Later native data require a new bounded exporter/reservation protocol; none
was downloaded or inspected for this experiment. CLUE is one storage service,
not proof of AWS/Cloudflare/GitHub generalisation. The live method annex,
scenario executor and scoring release gates remain separate work.

## Artifacts, reproduction and checks

Code: `scripts/personal_baseline.py` (pure immutable references and JSON reload),
`scripts/clue_native_projection.py` (native causal projection),
`scripts/evaluate_personal_baseline.py` (pinned development comparison).
Private output directory used locally: `data/processed/clue-personal-development-v1`.
It holds `reference.json`, `normal_calibration.json`, `development_report.json`;
no data, fitted references, weights or native identifiers are committed.

```powershell
$env:DATABASE_URL = 'sqlite-local'
python scripts/evaluate_personal_baseline.py --data PATH_TO_FROZEN_FEATURE_JSON --bundle PATH_TO_VERIFIED_CLUE_BUNDLE --prefix PATH_TO_EXISTING_NATIVE_PREFIX --plan PATH_TO_EXISTING_SWITCH_PLAN --out data/processed/NEW_PRIVATE_OUTPUT_DIRECTORY
python -m pytest scripts/tests/test_personal_baseline.py -q
```

The development CLI refuses existing output directories and unknown artifact
bindings. It reads trusted pinned artifacts only, verifies hashes before
deserialisation, reproduces native rows and recalculates switched prior-action
history. It never calls providers, opens the application database, trains an
AE, overwrites frozen inputs or registers a live score.

Full local backend/script regression: 276 passed, one opt-in PostgreSQL test
skipped. Tests include immutable fitting references, calibration separation,
quantile boundaries, missing scores and OR logic, input rejection, native
history projection, report assembly/control denominators, earlier-partition
contamination and the resource-observability counterexample. Claude's
independent code-only review found no blocking issue; its requested case-
assembly coverage was added. CI runs the new tests in both the backend job
and the pinned CPU model-training environment.

Report SHA256:
`36dd3d77ef60219796613bd49246a4d5c1dd9a84388591cf81b65fa0b5450f57`.
Public summary is development evidence with small correlated samples. It is
not a statistically powered superiority claim or real-world attack recall.
