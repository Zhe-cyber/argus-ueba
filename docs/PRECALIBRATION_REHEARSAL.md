# Pre-calibration rehearsal and review response

Saved 29 October 2026 in response to Claude's four risks. Production protocol, generator, primary method, scenario strength and date guards stay unchanged. The earlier handover has a new W22 section; it is no longer the saved content reviewed at 16:35.

## 1. Expected sensitivity

See EXPECTED_SENSITIVITY_PRECALIBRATION.md for the analytical prediction saved now. Exact score change is ln(p(old)/p(p06))/n. Dilution can limit sensitivity, but the estimated 50 fitting events/20 daily events do not match our workload: targets plan 15 and 25 fitting events, with daily caps 4 and 5. The AE can change when unique_resources increases; identical input vectors necessarily give identical errors, but not all substitutions preserve diversity.

scripts/live_development_checks.py fits references on fitting rows only and compares hypothetical one-read changes on development days with observed normal development spread. Available CLOSED fitting/validation rows only; calibration/case rows and use from 8 November MY onward are refused. Output is a prediction, not a calibrated threshold or held-out result. Do not change the scenario/model after this diagnostic.

Current actual result: pending_fitting_history. A private pending report came from the existing empty normal export, not warm-up/setup activity. Fitting begins 30 October; earliest complete fitting window is 6 November. Before 8 November, validation day 7 November is not closed; use only available closed validation dates and report their count.

## 2. Partial check 2–3 November; full rehearsal 6 November morning

The full qualifying path cannot finish before 8 November: real calibration runs 8–10 November and release is on 11 November. The separate harness rehearses on a COPY without weakening production guards:

    python scripts/export_live_daily.py --pilot-config <private-pilot-config.json> --out <fresh-normal-export-directory>
    python scripts/live_development_checks.py --data <normal-export-directory> --out <fresh-prediction.json>
    python scripts/rehearse_live_study.py --data <normal-export-directory> --out <fresh-rehearsal-directory>

The first command performs real read-only auditing/export. The harness selects fitting aggregates ONLY; available validation rows are ignored. It copies fitting aggregates onto explicitly synthetic validation/calibration dates, recalculating weekday-dependent off-hours counts. This intentional reuse leaks fitting data into those test partitions: engineering only, not generalisation or statistical evaluation.

The bundle is synthetic_contract_test under dummy account 000000000000. Synthetic case receipts use REHEARSAL identifiers and documentation-only IPs in isolated files. Only the harness scopes a simulated release clock and synthetic-loader injection to release creation, then invokes the evaluator with its explicit internal synthetic allowance and simulated cutoff. No source files, provider resources, actual ledger, current collection or production CLI guards change.

Actual Git checks still apply to a real rehearsal: bound sources must already be committed/clean before calibration. Only synthetic tests stub Git metadata. No fake commit or clean-status claim is made for this worktree.

The default production loader MUST reject the bundle afterward. A failed normal gate gives rehearsal_normal_gate_no_go, not a forced threshold. REHEARSAL-ONLY.json binds the original dataset and harness source; SYNTHETIC-case-report.json, when produced, is never real attack evidence. Keep derived files private and separate from connected stores/model folders.

Run export plus live_development_checks.py around 2–3 November using the real closed rows available then. A pending result is expected: this is an early real export/validation-path check, not a reason to relax gates. Keep its original report.

Run the full fitting rehearsal FIRST THING on 6 November, not initially on 7 November. Fitting closes 6 November 00:00 MY; this leaves time to fix/review/commit before 8 November 00:00. Use 7 November only for reruns/fixes and an updated prediction with available closed validation data.

Status today: implemented and tested on synthetic fixture history. Actual partial real-data check and full fitting rehearsal remain PENDING their dates/eligible history. No automatic future task or reminder was installed.

Verification: 563 full-suite tests passed, one optional PostgreSQL skip; after distinguishing engineering errors from legitimate normal-gate no-go, all seven focused development tests passed. Do not label either test run as the pending real-fitting rehearsal.

## 3. Clean commit by 5 November

Worktree-local core.autocrlf=false is explicitly set. Source bytes were not rewritten. Manual commit remains the user's preference; no commit/push/merge performed. See COMMIT_PILOT_CHECKLIST.md. Clean commit is NOT complete until user commands succeed and git status is empty. Never blindly refresh source pins after a checkout/line-ending mismatch.

The checklist now excludes update.md from staging and a worktree-local exclude rule preserves it as a local handover. The deferred W19 receiver IS in the reviewed inactive-code batch; committing it does not deploy it.

## 4. Operational routine

- Review last_attempt.json and latest.json each morning. No notifications; a failed attempt can leave an older good report.
- Keep laptop awake/logged in/online 08:00–20:00 MY. Global power/update/reboot settings remain unchanged; update pauses are a user decision.
- Reserve 14 November evening for reconciliation/evaluation AFTER 20:00 MY, then sign off 15 November. No calendar event/reminder created.
- Fix/review/commit bugs before calibration. After the freeze, report no-go rather than quietly altering a method or repeating cases.
