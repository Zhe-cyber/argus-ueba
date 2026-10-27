# W3: CLUE benchmark replay, separate from connected sources

28 October 2026. Based on PR #17, commit 506241b. No model training/activation,
cloud provisioning, scenario replay or edits to tomorrow's poster.

Policy fixed before rendering the dashboard:
- High iff raw reconstruction MSE > the candidate's frozen 99th-percentile
  normal-calibration threshold. Never replace or retune the High rule.
- Medium iff not High and MSE > the linear 95th percentile of the same separate
  normal-calibration errors. Equality at either boundary goes to the lower tier.
- Otherwise Low. These are review priorities, not compromise probabilities.
- Write a hash-bound policy from calibration only first; separately export normal
  calibration and held-out rows with the verified candidate. Never export fit or
  validation rows, native identifiers, raw events or paths to the dashboard.
- Default to the held-out window. Calibration is a separately labelled diagnostic
  partition, not independent test evidence. Exposed held-out dates are now development
  evidence for subsequent changes. This candidate's original frozen rule is retained.
- Preserve raw MSE and residual contributions. Residuals are not SHAP or causes.

An offline job writes a new private immutable artifact directory; the API reads
and validates its JSON through explicit CLUE_REPLAY_DIR. No pickle/torch loading
or model downloads in the API. No replay row enters live tables, alerts, identity
mappings or investigation records. Missing/invalid bundle fails closed.

Frontend: connected-source and replay tabs; account-day rows, split/date/priority
filters, distribution, threshold context and numerical reconstruction details.
Show "Normal benchmark data: few alerts are expected." Never imply High confirms
an attack. Preserve connected Unknown. No account-switch data is included; the
population-model limitation remains documented.

Validate boundary ties, calibration-only policy derivation, tamper/refusal cases,
holdout-only defaults and API/live separation. Reproduce the supplied normal
report (191 active identity-days, 2 High) without modifying private inputs. Run
isolated backend/script tests and frontend production build. Human merge/deploy.
