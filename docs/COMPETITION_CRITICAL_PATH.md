# Competition critical path after Claude review

29 October 2026. Working priorities after review of plan-review-2026-10-29.md. This does not amend frozen study data, method thresholds or actor profiles. New priorities can be revised by the user; no automatic public deployment or global laptop setting change is authorized by this document.

## Deliverable to protect

A real three-source collection prototype, with a prospective controlled AWS case study if its frozen coverage/method gates pass. Cloudflare and GitHub contribute descriptive activity/coverage evidence. They are not promised independent validated detectors, population baselines or a unified cross-provider risk score for this competition.

## Priority order

1. Operational coverage: W20 now installs a standalone daily 08:15 MY/at-logon check of yesterday's planned/verified/missing roles, unresolved receipts and source collector status, reusing the existing read-only readiness audit. Absence of a Cloudflare sign-in/GitHub change is not inherently a collection failure. Source polling health and observed activity are separate. Reports need user review; no notifications or automatic repairs are installed. Check sleep/credential risks without changing global power/update settings automatically.
2. Scenario execution and evaluation: W21 implementation and synthetic tests are now complete; review/commit target remains 5 November, before calibration begins on 8 November. The local pilot routes reserved dates through a release-gated wrapper reusing durable claims, budgets, non-root scope and no uncertain retries. Exact receipt auditing and frozen-bundle evaluation refuse pre-cutoff use. No reserved case has run. Complete independent review and commit the bound sources; operational instructions are in RESERVED_AWS_STUDY_RUNBOOK.md.
3. Normal export, training and freeze: follow existing windows/gates. No training on warm-up, current days, missed days, setup probes, scenarios or controls. Review exclusions and per-role calibration/reporting. Freeze model/method/threshold/source hashes on 11 November before reserved cases.
4. Cases and reconciliation: execute only the frozen reserved 12 November case and 13 November approved control; reconcile through 14 November. Missing evidence produces unscored/unknown cases, not negatives or retrospective replacement cases. Final decision by 15 November.
5. Presentation consistency: prepare outcome-conditional wording now. After finalization, rehearse the live workflow and offline evidence, limitations and failure/recovery story for 25–26 November. Audit poster/paper/public deployment claims against the actual code; no public deployment or paper edits are assumed complete.

## Deferred implementation

Hosted webhook deployment, Cloudflare/GitHub scoring, full native-evidence migration, unified score, automatic identity resolution, security-log importer and further familiarity replication are outside the critical path. The local W19 receiver remains a tested but inactive development artifact. Existing three-source collection continues; the W18 projection export is descriptive and optional to the AWS study.

An adaptive GitHub lookback/pagination improvement is a bounded reliability proposal, not installed yet. It must specify last-success meaning, overlap, startup watermark, late-event recovery, page/request caps, API budget, partial failures and cap-hit telemetry, and preserve the owned pilot's source-pin release process. A one-day local filter cannot recover older events automatically, but events are not necessarily permanently lost if GitHub still exposes them. A later manual/versioned backfill may remain possible.

## Frozen persona variation and limitations

persona_profiles_v2.json is already byte-pinned at SHA256 150529b73fa71ac75eab06b162ad4bc913d7d0a19e3ff52c009d60ef3ba3899c. persona_history_plan.py uses a fixed global seed combined with persona ID/date, bounded varying action count, weighted operation/resource choices, selected session windows and varied within-window minutes. V2 deliberately sets weekday/weekend activation probabilities to 1 to support history eligibility. These parameters were fixed before fitting; do not change them after observing results to create easier anomalies.

This is reproducible scripted variation, not evidence of independent human habits. Occasional off-pattern behavior is only whatever the frozen resource/operation probabilities already produce; no new off-pattern mechanism is asserted or added. A successful case may demonstrate sensitivity to a controlled departure from a workload script, not real-world compromise detection.

## Outcome wording, to fill only after evaluation

If eligible: "In a prospective controlled AWS workload study, the frozen method flagged X of N scorable reserved case account-days and Y of Z scorable approved-control account-days. Report excluded/unscored cases separately. These descriptive counts do not estimate general attack recall or population false-positive rates."

If ineligible or ineffective: "Argus demonstrates live evidence collection and normalisation across AWS, Cloudflare Access and GitHub. Offline development experiments expose limitations of population-only and account-familiarity methods; the prospective live study reports its coverage, eligibility and observed outcomes without claiming validated compromise detection."

Do not say the detector passed merely because training completed or calibration alerts are low. Do not say the frozen protocol is complete until scenario/evaluation code and the necessary artifact-release checks are actually frozen.

## Review clarifications and actions

- Confirmed PR-review counting defect: fixed in github_projection_daily_v2; PR review remains unclassified. Original v1 data/manifest and exact producer script preserved privately. Full backend tests: 171 passed, forced SQLite.
- Closed dates remain explicitly completeness-unknown in the exporter. Poll history is not assessed; this is a limitation, not permission to treat a day as normal or complete. Constant one-repository counts remain context, not justified model inputs.
- Exact source-byte hashes intentionally identify the producing artifact, including line endings. They do not normalize across checkouts; preserve bytes and compare the correct artifact. The standalone exporter records the current source hash rather than loading a cross-platform expected hash.
- The existing AWS readiness evaluator is now reused by W20's installed daily task. Future-date status is not a missing-history failure.
- The live method annex uses k=floor(0.05*n), a strict greater-than cutoff and a 5% calibration budget, not a 99th-percentile rule. With 12–18 calibration rows it still sets the cutoff at the maximum and cannot establish future alert rates. The old CLUE AE/familiarity work used other thresholds under separate contracts.
- Current ACCOUNT_FAMILIARITY_DEVELOPMENT.md already explicitly explains cancellation of popularity for never-used tokens. The old review may refer to an earlier description. Do not change frozen scores or code on that basis; investigate remaining missingness wording separately if needed.
- SHAP/paper/HF/Vercel concerns are review leads, not newly verified facts in this task. Verify exact file/deployment versions before changing them or repeating claims.
