# CLUE Colab training and frozen normal evaluation

This workflow trains the separate ten-input clue_behavior_v1 research benchmark.
It preserves the 71-feature CERT model and 12-feature AWS prototype. It never
deploys, installs or automatically retrains a live model. The population AE is
not an individually conditioned per-user model, and CLUE results cannot establish
AWS/GitHub/Cloudflare or cross-cloud identity detection accuracy.

The original checkout stays on master with existing edits preserved. The new
offline files are uncommitted there; selected files are published separately
on review branch w2-clue-colab, stacked on PR #15. Nothing is merged to master.

## Run in Colab

Open clue_ae_training.ipynb from the review branch (or its immutable commit).
It pins the exact implementation commit, installs the tested CPU dependency
versions and verifies the feature export's SHA256. Use this local file:

`data/processed/clue-v1/colab-features.json`

Expected SHA256:
`c151ccd687f09175ee06f827168525c31a28cd000df0a67a8cda9a1ed187c4f3`

Upload only that feature JSON. No AWS/Cloudflare/GitHub credentials, .env, raw
provider logs, ZIP prefixes or model files are needed. Pseudonymised features
still require care; they are not guaranteed anonymous. The source is Landauer,
Skopik, Hoeld and Wurzenberger (AIT), CLUE-LDS (2022), DOI 10.5281/zenodo.7119953,
CC BY 4.0. Partial-prefix integrity/coverage and publisher-declared normality
limitations accompany the source export.

Run setup/upload, verify the printed population and counts, then deliberately
set RUN_TRAINING=True. Training outputs a candidate, not an active detector.
Only after the candidate is frozen, set RUN_NORMAL_EVALUATION=True to run the
later normal holdout. Download the bundle at the end. Re-running training or
evaluation requires fresh output paths; existing artifacts are not overwritten.

## Data and model contract

The fitting-selected cohort has 55 named pseudonyms. Warmup ends 12 July 2017;
fit ends 26 July; validation ends 31 July; normal calibration ends 4 August;
held-out evaluation ends 9 August. The prepared export has 605 fitting, 188
validation, 169 normal calibration and 191 later normal rows. Boundary dates and
out-of-population rows were excluded by the export/selection protocol. Some
cohort members have no later activity; that absence is reported, not treated as
a correctly classified normal day. No synthetic zero-activity days are created.

Inputs are log1p-transformed counts in exact profile order, then StandardScaler
fitted on fitting rows only. The CPU AE is 10-32-16-8-16-32-10 with LeakyReLU(0.1),
Adam, fixed default 100 epochs and seed 42. Normal validation selects weights.
Independent normal calibration sets the predeclared 99th-percentile raw MSE
threshold. A score strictly above that threshold alerts. This does not guarantee
a 1% future alert rate and does not represent a compromise probability.

Training never builds tensors from held-out feature values. The separate
evaluation command loads a frozen, hash-checked bundle and applies the stored
transform, scaler, weights and threshold. It reports normal alerts, denominator,
observed cohort coverage and a descriptive Wilson interval. Active user-days
are dependent, so that interval is not a dependence-aware confidence guarantee.
No attack recall, precision, PR-AUC or production reliability is claimed.
Do not tune the threshold after viewing the holdout and still call it untouched.

## Artifacts and local equivalent

Artifacts are clue_ae_v1.pt, clue_scaler_v1.pkl and clue_model_manifest.json.
The frozen manifest records exact input/profile/transform, fitting population,
cutoffs, counts, hashes, seed and environment. It retains not_evaluated status
from freezing; normal_holdout_report.json is the separate later evaluation
record. Never overwrite cloud_ae_v1.pt, cloud_scaler_v1.pkl or CERT artifacts.
Only load locally generated/trusted bundles; hashes do not authenticate an
untrusted manifest, and pickle-based scalers must not be accepted from strangers.

```powershell
python scripts/train_clue_ae.py train --data data/processed/clue-v1/colab-features.json --out data/processed/clue-v1/NEW-candidate --cutoffs 2017-07-12 2017-07-26 2017-07-31 2017-08-04 2017-08-09
python scripts/train_clue_ae.py evaluate --data data/processed/clue-v1/colab-features.json --bundle data/processed/clue-v1/NEW-candidate --out data/processed/clue-v1/NEW-normal-report.json
```

These commands are opt-in instructions, not evidence they ran on the real
dataset during implementation. Only synthetic unit fixtures were fitted locally.
The next evaluation stage is a separately specified offline account-switch
experiment with scenario labels withheld and normal controls preserved.
