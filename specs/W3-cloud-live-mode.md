# W3: Standalone cloud live mode

Branch: codex/w3-cloud-live-mode. Base: 0d45b4e. Date: 2026-10-27.

Goal: opt-in ARGUS_MODE=live starts without CERT scores, SHAP or daily features;
the dashboard reports cloud monitoring separately from benchmark evaluation.
Legacy DEMO_MODE and benchmark deployments remain compatible.

Changes: explicit validated application mode; empty benchmark store in live mode;
cloud-only ingest and counts; disable offline score seeding in live mode; show
mode/ground-truth availability in dashboard metadata; PR-triggered backend,
collector and frontend CI; temporary isolation for all test stores.
Preserve unavailable AE scores as null/Unknown, not Low. Disable live seeded
pseudo-SHAP and CERT-oriented AI guidance until verified live explanations exist.

Acceptance: regression suite green; live startup never reads benchmark files;
real HTTP tests cover empty live startup, cloud ingest with stubbed scorer,
list/detail/stats/investigation behavior and rejection of CERT/seeded records;
frontend production build passes. Stubbed scoring verifies plumbing only.

Non-goals: changing frozen feature contracts/scoring semantics; authentication,
identity mappings, new provider collectors, SHAP generation, production deployment.
Run a dedicated database for live mode; this slice does not retrofit account/tenant
scoping or certify production readiness. Do not expose real logs publicly yet.

Review: Codex reviews API behavior and regression evidence before draft PR.
Only the user merges or approves the first production deployment.
