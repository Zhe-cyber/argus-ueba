# Spec: L10 — live unsupervised autoencoder on the lab's own data (comparator, not alerting)

**Branch:** `l10-live-ae` off `l8-sprint` · worktree `C:\Users\yyzhe\argus-worktrees\l10-live-ae` · **Executor:** heavy (opus) · **Written:** 2026-11-12 · **Revised to v2:** 2026-11-13

## Goal
An unsupervised autoencoder trained on the lab's own persona account-days runs beside the baseline risk score:
every persona account-day (six AWS persona roles, six Cloudflare persona service tokens) gets an "ML anomaly score"
with a per-feature explanation, shown in the workspace, and the frozen model is evaluated on the same scenarios and
normal days as the baseline (declared as a comparator in `specs/L7a-autoencoder-comparator-addendum.md`). It never
raises alerts.

## History: v1 → v2 (13 Nov 2026, before any scenario)
v1 (8 raw daily counts of the V3 `aws_lab_daily_v1` contract, one population model 8-4-2-4-8, fixed 200 epochs, AWS
only) trained 13 Nov 00:33 MYT and reached validation MSE 0.9248 at the epoch cap: barely better than predicting the
mean and still improving. The owner-approved v2 design below replaced it before any evaluation scenario. v1 is kept
unchanged as history (`backend/live_ae_v1.py`, `backend/tests/test_live_ae_v1.py`, bundle `bundle-20261113T003343`).

## Non-goals
No change to the baseline score, its alerting, method v1.2 (the 47 reference cases still pass), or L7. No edits to
files in `scripts/reserved_study.py::SOURCE_FILES` or `scripts/train_clue_v2.py::TRAINING_SOURCES` (read-only
imports only). No commit/push. Pilot checkouts read-only. No cloud calls.

## Approach (v2, planner-decided; not tuned)
1. `backend/live_ae.py`:
   - `features(days, day)`: nine account-relative inputs from the account's own previous active days only (baseline
     history: active days in the previous 28 calendar days, `baseline_scorer.prior_days`; fewer than 5 → Learning):
     `event_count_log`, `unique_actions`, `unique_resources`, `outside_usual_hours_share`
     (`baseline_scorer.usual_hours`, ±1 h), `new_action_count`, `volume_log_ratio`, `new_resource_share` (0 when no
     resource today, `no_resource_today` stored), `action_mix_js_distance`, `hour_profile_js_distance` (base-2 JS
     distance, event-weighted, `scripts/clue_v2_features.js_distance`, 24 MYT hours). The same function builds
     training rows and live scores. (`prior_days`/`usual_hours` were extracted from `baseline_scorer.score_day`
     without behaviour change.)
   - `scope(events)`: AWS assumed-role `argus-*-persona-0N` (ARN account = source account) or a Cloudflare service
     token whose requests carry `/workloads/persona-0N/`; everything else not applicable.
   - `train(events_db, out_dir)`: every scorable account-day ≤ 12 Nov 2026 MYT from the events DB opened read-only
     (`?mode=ro`); fit ≤ 8 Nov, validation 9–10 Nov, calibration 11–12 Nov. Model 9-6-3-6-9, Tanh hidden, linear
     output; fit-only standardisation (zero variance → scale 1); CPU, seed 42, deterministic, one thread; full-batch
     Adam lr 0.001, weight decay 0.001, grad-norm clip 5; up to 2000 epochs; earliest minimum validation MSE (strict);
     patience 200. Threshold = `live_daily_method.empirical_threshold` on calibration scores (strictly greater flags).
     Bundle: weights, scaler, manifest (rows per split and provider, best validation MSE and the predict-the-fit-mean
     validation MSE, selected/stop epoch, threshold, artifact and source hashes, feature-contract hash).
   - `load` refuses another profile, feature contract or method, changed artifacts and synthetic bundles.
2. Storage: `ml_scores` (backend schema, SQLite and PostgreSQL) unique on `(account_key, day)`, with
   `model_version` ('v2'; v1-era rows default 'v1') and `no_resource_today`; `event_store.ensure_ml_scores` adds the
   columns to a v1-era table. Learning days are stored with a NULL score and the reason.
3. Scoring trigger: backfill command; ingest hook for AWS and Cloudflare events and the mirror pass (best effort,
   never blocking ingest); a late event also rescores the account's later stored days inside its 28-day window.
4. Workspace: "ML anomaly score (autoencoder v2)" row on the account panel and finding dialog (v2 rows only); Method
   & limits section updated.
5. Real training: `scripts/train_live_ae.ps1` (read-only source; fresh `data\live\live-ae\bundle-v2-<stamp>`;
   optional `-DemoDb` backfill of a marked copy). Python refuses before 12 Nov MYT has closed. Run once on
   13 Nov 01:06 MYT; numbers in L7a §3.
6. Tests (synthetic, `backend/tests/test_live_ae.py`): hand-computed features; Learning below 5 prior days; same
   features at train and score time; deterministic training; earliest-minimum early stopping; threshold rule;
   tampered/synthetic bundle refused; Cloudflare scored, GitHub bot not applicable; no data after 12 Nov (split
   asserted; adding 13 Nov+ events leaves the dataset hash and weights unchanged); store/backfill/ingest/view;
   v1-table migration.

## Acceptance
- [x] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures
- [x] `git diff --stat l8-sprint -- <SOURCE_FILES> <TRAINING_SOURCES>` empty
- [x] Synthetic end-to-end train → score → store → view works
- [x] Real v2 training run once; manifest summary in L7a §3; backfill only on a temporary copy
- [x] No 12-digit number, email or IP in outputs

## Escalation
Stop and report if: a read-only import cannot be used without editing its file; the dataset refuses on real data for
a reason other than the date; the same step fails twice.
