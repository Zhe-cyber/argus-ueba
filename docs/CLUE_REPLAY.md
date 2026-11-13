# CLUE benchmark replay

The connected dashboard and `/clue` show separate data contexts. Replay is a
read-only export of actual inference from the frozen ten-feature CLUE AE. It does
not populate connected users, scores, alerts or investigation records.

## Prepare private artifacts (offline, two steps)

Use the same trusted local bundle and dataset as the Colab normal report, and
the pinned CPU training environment in `scripts/requirements-cloud-training.txt`
plus torch 2.12.0. No retraining or Colab session is required for this export.
Verify artifact provenance before supplying a pickle/joblib scaler; a file hash
binding detects changes, but does not make an untrusted bundle safe to load.

```powershell
python scripts/build_clue_replay.py freeze-policy --data PATH_TO_FEATURES_JSON --bundle TRUSTED_CANDIDATE_DIR --out data/processed/clue-replay-policy-v1.json
python scripts/build_clue_replay.py export --data PATH_TO_FEATURES_JSON --bundle TRUSTED_CANDIDATE_DIR --policy data/processed/clue-replay-policy-v1.json --out data/processed/clue-replay-v1
```

The first command scores only normal calibration rows, checks that the candidate's
99th-percentile threshold reproduces, and writes the new Medium boundary. It never
scores fitting, validation or held-out values. The second checks those bindings
and reproduces the supplied normal holdout report before exporting calibration
and held-out account-day scores. Existing output files/directories are refused.
Keep the policy/export private and gitignored, like the original model/data.

High retains the exact frozen candidate rule: raw MSE strictly greater than its
99th-percentile normal-calibration threshold (0.7648530006408691 for the supplied
candidate). Medium is strictly greater than the linear 95th percentile of the
same separate calibration errors, unless already High. Equality goes to the
lower tier. These are review priorities, not attack classes, calibrated compromise
probabilities or guarantees of future false-alert rates. Medium is a new display
policy; no model parameter or original High threshold changes.

For the supplied candidate, the reproduced Medium threshold is
`0.12822140753269196`. Held-out output is 185 Low, 4 Medium and 2 High account-days;
calibration diagnostics are 160 Low, 7 Medium and 2 High. These counts describe the
existing normal benchmark, not attack detection. Do not substitute these example
counts in the UI: it derives counts from the verified artifact.

The export contains cohort aliases, UTC dates, ten counts, raw MSE and numerical
residual contributions. It excludes native IDs, raw logs, paths, fitting and
validation rows. Residual contributions are not SHAP or proven causes.

## Run locally beside connected sources

Set the following before starting the backend. Use the existing dedicated live
state directory; do not point at a mixed benchmark database or production Neon.

```powershell
$env:ARGUS_MODE = 'live'
$env:DATABASE_URL = 'sqlite-local'
$env:LIVE_STATE_DIR = 'PATH_TO_DEDICATED_LIVE_STATE'
$env:CLUE_REPLAY_DIR = 'ABSOLUTE_PATH_TO_EXPORTED_REPLAY'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Start the frontend with NEXT_PUBLIC_API_URL pointing to this local API. `/` retains
connected data and unavailable scores as Unknown; `/clue` defaults to held-out
normal days and separately labels calibration diagnostics. Training/validation
rows and account-switch scenarios are never displayed. Missing or invalid replay
artifacts show an unavailable notice, without generating sample results.

The API reads JSON only; it does not import torch/joblib for replay. Local manifest
checksums detect accidental replay/policy changes, not malicious local rewrites.
This change does not provide authentication or authorise public deployment.

## Interpretation and demonstration

The supplied frozen candidate has 191 held-out normal active identity-days across
49 active identities and 2 High days. A quiet view is expected for normal data.
These dates were already inspected: they remain a reproduction of this frozen
candidate, but are development evidence for later revised models. Calibration
diagnostics are not independent test results. Missing activity is not a benign
observation. All counts are account-days unless explicitly labelled accounts.

Population novelty can miss plausible account misuse. The separate preregistered
switch study found 0 detections on 25 switched account-days; it is intentionally
outside this normal-data replay, not invalidated or hidden from research reporting.
Do not claim that these scores demonstrate detection on AWS, Cloudflare or GitHub.

Validation: strict boundary tests, invalid artifact refusals, calibration-only
policy derivation, frozen holdout reproduction, and replay/live store isolation.
No external deployment or cloud credentials are required by the tests.

Optional local browser check: use `scripts/tests/clue-replay-ui.mjs` with an
installed Playwright entry point in ARGUS_PLAYWRIGHT_MODULE, a dedicated local
preview at ARGUS_UI_URL (default 127.0.0.1:3010), and its API at ARGUS_API_URL
(default 127.0.0.1:8010). The check expects the supplied candidate's counts and
a live instance whose connected accounts are unscored. It uses a fresh headless
Chrome profile, blocks non-GET page requests and external page origins, checks
both tabs/filters/residual details, and compares connected statistics before/after.
ARGUS_UI_OUTPUT selects a private screenshot/report directory. It never attaches
to the user's Chrome session or sends telemetry to cloud services.
