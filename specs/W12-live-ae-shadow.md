# W12: refreshed live AWS AE engineering scores

Written 28 October 2026, before implementation. User requests starting live
scoring work now. This slice turns the existing one-off inference into a finite,
read-only refreshed engineering view; it does not qualify detection thresholds.

Use the locally trusted legacy 12-count cloud AE and its StandardScaler, pinned
by SHA256 before deserialisation, exact checkpoint/order/shape/type validation,
weights_only torch load, eval/inference mode and finite residual checks. Preserve
the frozen extractor's UTC windows and 07-19 UTC off-hours definition. That legacy
contract is separate from the prospective MY-time live study and CLUE/CERT models.

Read the actual connected SQLite store using mode=ro, query_only and a consistent
transaction. Isolate AWS source and configured account. Bound at 100000 rows;
overflow fails, never silently truncates. Group by account/principal. Latest UTC
day per principal is scored using strictly earlier same-principal history only.
Missing principals are counted and never assigned a score. Future timestamps,
invalid metadata/features and nonfinite model output fail closed. No event or
live_scores table writes, model registration, thresholds, probabilities or tiers.

Publish atomic local latest JSON and self-contained HTML with private-salted
stable principal aliases, observed dates/counts, raw MSE, largest reconstruction
residual features (not SHAP), source/model/feature hashes, latest snapshot age,
unverified completeness and provisional transfer limitations. No raw account IDs,
principal names, emails, IPs, resources or credentials in either output. Historical
latest days must be visibly distinct from current partial UTC days. Stale/failed
runs must not appear current. Preserve last successful report with failure marker.

Install one separately named current-user interactive hidden Windows task only
after a successful real run. Every30min, IgnoreNew, no stored password/no wake,
same deadline midnight15NovMY. It has no provider credentials or API calls.
Pin its own code/dependencies/configured artifacts separately; do not change or
restart source-pinned collection tasks. Expires without reading DB/model after
the deadline. Re-run refuses altered artifacts/source; no automatic pin refresh.

Acceptance: isolated SQLite tests cover namespace/history separation, invalid
timestamps, no phantom missing identity scores, bounds, privacy, failure/stale
labels, inference numeric contract and expiry. Verify actual live inference and
owned task run, existing collector health/source pin unchanged, full tests/CI.
No claims of real-human, compromise or multi-cloud model validation. Human merges
draft PR; user sends Claude review manually.
