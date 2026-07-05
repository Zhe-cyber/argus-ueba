# Standing research questions (product evaluation — outward)

*The researcher agent picks from here (or is given an ad-hoc question). Answered → brief
in research/, line in LOG.md, question updated or retired. Planner reviews before each
workstream; anything that changes a decision moves into UPGRADE_PLAN.md as an R-finding.*

## Open

| # | Question | Feeds | Priority |
|---|----------|-------|----------|
| Q1 | ~~What are the best published CERT r4.2 results (AUROC/F1, per-scenario) as of 2026 — is 0.976 label-free still competitive, and has anyone beaten supervised 27/30 on Scenario 2?~~ **Answered 2026-07-03** → [research/q1-cert-sota-2026.md](q1-cert-sota-2026.md) | Paper positioning, viva defence, CUSUM buffer study | Done |
| Q2 | ~~Has Wazuh (or OpenUBA/HELK) shipped ML-based or multi-source UEBA since our Table 2 comparison (mid-2025)? Any change that invalidates a row?~~ **Answered 2026-07-04** → [research/q2-competitor-2026.md](q2-competitor-2026.md) | Paper Table 2, differentiation slide | Done |
| Q3 | ~~EventBridge → SQS end-to-end latency for `AWS API Call via CloudTrail` under free tier: measured numbers from practitioners, not just docs (we verified "seconds to ~2 min" from docs — find field reports)~~ **Answered 2026-07-03** → [research/q3-eventbridge-latency.md](q3-eventbridge-latency.md) | W1-B design, <60s success criterion | Done |
| Q4 | Azure AD (Entra) sign-in log access via Graph API on the M365 dev sandbox: current E5 entitlements, renewal policy 2026, known API rate limits | W7/P2 Azure poller, plan risk table | Medium |
| Q5 | ~~Label-free threshold calibration methods used in production anomaly detection (alert-budget / percentile / extreme-value theory) — what's citable for W4's method choice?~~ **Answered 2026-07-04** → [research/q5-threshold-calibration.md](q5-threshold-calibration.md) | W4 study methodology | Done |
| Q6 | Any new public insider-threat or account-compromise datasets since CERT r4.2 / flaws.cloud usable for a third external validation? | Evaluation chapter strength | Medium |
| Q7 | Triage-time user-study designs in security XAI literature (n<5 participants): accepted metrics, statistical treatment for tiny samples | W8 ECLOGIC study design (planner needs this before wk 12) | Medium (rises to High by wk 10) |
| Q8 | MSP tooling landscape: what do small MSPs in SEA actually use for client security monitoring, and what's the integration surface Argus would need (PSA/RMM hooks?) | FYP2 specialty thesis, ECLOGIC conversations | Low |

## Retired

*(none yet — move answered/obsolete questions here with the brief link)*
