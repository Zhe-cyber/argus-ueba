# W3: Explain unknown risk and model readiness

27 October 2026. Branch codex/w3-scoring-readiness, stacked on PR #9.
User reports every live account has Unknown risk. The running worktree lacks
gitignored cloud AE artifacts. The original checkout contains a compatible 12-D
checkpoint/scaler, verified in memory with matching feature order. Its training
script uses the flaws.cloud AWS benchmark, not the new three-provider accounts.

Expose safe model readiness/reason/provenance in live stats and account detail.
Show that explanation on the dashboard and detail page, add an Unknown summary
and filter, and label live rows as accounts. Never reinterpret missing scores as
Low or replace AE risk with rarity/rule scores. Do not expose server paths, raw
load errors, credentials or personal records in readiness responses.

The user has been asked whether to enable clearly labelled provisional benchmark
scores or keep accounts unscored pending baseline validation. Model activation
and rescoring await that choice; the readiness/UI work is independent. If
provisional scoring is selected, verify/copy only the 12-D cloud model/scaler,
label their AWS benchmark provenance, preserve events/receipts, and refresh
existing account scores explicitly. Do not use the 71-D CERT model for cloud data.
No fabricated malicious labels, baseline sufficiency or cross-cloud accuracy claim.

Acceptance: safe distinct missing-artifact/not-loaded/load-failure/ready statuses;
no inference forced by a status request; live stats/detail include readiness;
benchmark mode remains unchanged; SQLite test suite and frontend build pass;
verify the running local dashboard/API after restart. No public deployment or
merge, no training or frozen feature/scoring changes in the readiness work.
