# Addendum L7a — unsupervised autoencoder declared as a comparator (v2)

Addendum to `specs/L7-live-evaluation-rules.md` (v1.2 rules). Written 12 November 2026 (MYT); model replaced by v2
on 13 November 2026 before any scenario (see §5). Committed with the trained model's hash before the first scenario
call; otherwise L7 is unchanged. The baseline risk score v1.2 remains the only method that raises alerts and the
primary subject of the evaluation.

## 1. What is added

An unsupervised autoencoder trained only on this lab's own collected persona account-days, reported beside the
baseline for the same scenarios and the same normal days. It does not raise alerts and does not affect the baseline
result. Code: `backend/live_ae.py` (v2).

| Item | Fixed value |
|---|---|
| Model | Autoencoder 9-6-3-6-9, Tanh after each hidden layer, linear output, 168 trainable parameters |
| Inputs | Nine account-relative features per (account, MYT day), computed only from that account's own previous active days (the baseline scorer's history: active days in the previous 28 calendar days, at least 5; otherwise **Learning**, not scored): events today (log1p), distinct actions, distinct resources, share of today's events outside the account's usual hours (`baseline_scorer.usual_hours`, ±1 h), new actions, volume log-ratio against the median prior active day, share of new resources (0 when none today, flagged in storage), base-2 Jensen–Shannon distance of the action mix and of the 24-hour MYT profile (`clue_v2_features.js_distance`). One function builds training rows and live scores |
| Accounts | The six AWS persona roles and the six Cloudflare persona service tokens. Monitoring-infrastructure accounts, people and the GitHub bot are not applicable |
| Data | Every scorable persona account-day dated up to and including 12 Nov 2026 MYT, from the pilot events database opened read-only; events dated 13 Nov or later are dropped before any feature is computed |
| Split (MYT date) | Fit ≤ 8 Nov; validation 9–10 Nov (checkpoint and early stopping only); calibration 11–12 Nov (threshold only) |
| Training rule | Inputs standardised with fit-only mean/std (zero variance → scale 1); CPU, seed 42, deterministic, one thread; full-batch Adam lr 0.001, weight decay 0.001, gradient-norm clip 5; up to 2000 epochs; checkpoint = earliest epoch with the minimum validation MSE (strict improvement); stop after 200 epochs without improvement |
| Threshold | `live_daily_method.empirical_threshold` on the calibration scores (k = floor(0.05 n), value at index n − k − 1); a day is **flagged** only if its score is strictly greater |
| Secondary operating point | `live_daily_method.empirical_threshold` on the v2 scores of **all** scorable persona account-days dated up to and including 12 Nov 2026 MYT (the 104 fit + validation + calibration rows; AWS persona roles and Cloudflare persona tokens), computed with the frozen bundle and the same feature function, events DB read-only, nothing dated 13 Nov or later: k = floor(0.05 n), value at index n − k − 1, flagged only if strictly greater. Stored as `secondary_threshold` in `config/live_ae_v2.json` (`python -m backend.live_ae secondary-threshold --db <events.db>` reproduces it); stored per day as `ml_scores.flagged_secondary`. Not used for alerts; reported alongside the primary, which remains the declared main comparator |
| Score | Standardised reconstruction MSE, with each feature's share of the squared error as the explanation |
| Frozen bundle | Model sha256 (manifest) and weights sha256 recorded in §3 before the first scenario |

## 2. What is reported (in addition to L7 §5)

1. Per scenario, for the AWS account-day and the Cloudflare account-day separately: the autoencoder score, flagged
   yes/no at the primary threshold **and** at the secondary operating point, and the top three feature shares.
2. Normal comparison (the same evaluable persona account-days as L7 §4, AWS and Cloudflare): flagged out of N at
   the primary threshold and at the secondary operating point, each reported twice — all days, and excluding
   12 November (a calibration day of this model and inside the secondary's 104 days), so the held-out result is
   visible on its own.
3. The model manifest hash actually loaded by the running deployment, recorded before the first scenario; it must
   equal the hash in §3, otherwise the comparator is reported as not evaluated.
4. Side by side per scenario: baseline tier (alert = Medium or High) and autoencoder flag, as both / baseline only /
   autoencoder only / neither.

Days the autoencoder cannot score (Learning) are listed as not scored, with the reason; they are never counted as
negatives. Counts with denominators only; no accuracy percentage.

## 3. Pre-registration record (filled after training, before the first scenario)

| Item | Value |
|---|---|
| Training run (MYT) | 13 November 2026, 01:06 (bundle `bundle-v2-20261113T010640`, git-ignored under `data/live/live-ae/`) |
| Accounts | 6 AWS persona roles, 6 Cloudflare persona service tokens |
| Rows fit / validation / calibration | 56 / 24 / 24 (AWS 37 / 12 / 12; Cloudflare 19 / 12 / 12). Learning (not scored) days up to 12 Nov: AWS 30, Cloudflare 30. Last day used: 12 Nov |
| Best validation MSE | 0.1356 (predicting the fit mean, the comparison baseline: 0.7289) |
| Selected epoch / stop epoch | 1038 / 1238 |
| Threshold | 0.283617 (calibration days above it: 1 of 24; validation days above it: 3 of 24) |
| Secondary operating point (13 Nov 2026, 05:55 MYT, before any scenario) | 0.509095 (`0.5090951323509216`); n = 104, k = 5; days above it: 5 of 104 (AWS 5 of 61, Cloudflare 0 of 43). Primary threshold on the same 104 days: 15 above (AWS 15 of 61, Cloudflare 0 of 43). Loaded manifest sha256 = the one below; last day used 12 Nov |
| Trainable parameters | 168 |
| Model sha256 (manifest) | `d41e86a92cc24e6db706b161caef780a10d54f5f7c82592bcd7da6f2d7a2ffc0` |
| Weights sha256 | `b446da78e8625d39ef26d40812f18c563674ae38b1479f0aa54c3b77706f411c` |
| Commit SHA of this file | (the commit itself) |

## 4. Limits

104 training account-days (56 fitted) from twelve controlled machine workloads; one shared model across accounts,
but every input is relative to the account's own history, so it compares each account with itself. Nothing from
13 November onward is used.

Stated after training, before any scenario: the validation error (0.14) is well below predicting the fit mean
(0.73), so the model learned structure beyond the average. The threshold rests on 24 calibration days (k = 1, so it
is the second-largest calibration score) and is tight: on a backfill of a copy of the training data, 3 of 24
validation days and 11 of 56 fitted days lie above it, all AWS (15 of 61 scored AWS days, 0 of 43 Cloudflare). On
normal days the comparator should therefore be expected to flag AWS persona days more often than 5%; the evaluation
reports the count as it is. Cloudflare tokens average about one request a day, so their features vary little and a
single extra request moves them strongly. 12 November is a calibration day and also falls inside the L7 §4 normal
comparison window; it is reported but marked as a calibration day.

## 5. Changes before freeze (disclosed)

**Secondary operating point added, 13 November 2026 (MYT), before any scenario call.** The primary threshold was set
on 24 calibration days (k = 1) and already exceeds the 5% budget on normal pre-freeze days (15 of 104 above it, all
AWS). A second, pre-declared operating point (§1) applies the same 5% budget rule to all 104 pre-freeze scorable
persona days with the frozen bundle; its value and counts are in §3. The primary threshold remains the declared main
comparator; both flags are reported (§2). The model was not retrained and the bundle, its manifest hash and the
primary threshold 0.283617 are unchanged.

**v1 → v2, 13 November 2026 (MYT), before any scenario call.** v1 was a population autoencoder 8-4-2-4-8 on the
eight raw daily counts of the `aws_lab_daily_v1` contract (AWS persona roles only), trained 13 Nov 00:33 MYT
(bundle `bundle-20261113T003343`): rows fit / validation / calibration 37 / 12 / 18; best validation MSE 0.9248 at
epoch 200, the fixed epoch cap (still improving); threshold 1.974107; model sha256
`b206876ad3962c61196c3359d8ccad62e3102a04072c782970f9e6ec924d1171`. It was replaced because its validation error
showed it had not learned beyond the mean. v2 changes the inputs (account-relative instead of raw counts), adds the
Cloudflare persona tokens, re-dates the split (fit ≤ 8 Nov, validation 9–10, calibration 11–12) and replaces the fixed
200 epochs with up to 2000 epochs and early stopping. The v2 design was fixed by the planner from v1's validation
error and the CLUE v2 feature definitions; no evaluation-window data (13 Nov onward) and no scenario were used to
choose v2, and v2 was trained once. v1 code (`backend/live_ae_v1.py`) and its bundle are kept as history; the
workspace and `ml_scores` (`model_version` column) use v2 only.
