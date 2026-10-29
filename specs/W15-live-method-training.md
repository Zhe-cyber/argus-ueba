# W15: prospective method and compatible daily trainer

Written29 October2026 before implementation or live fitting/validation/calibration
scores. See LIVE_METHOD_ANNEX_V1.md for exact method decisions. No reserved cases
are consumed. Keep running collector and legacy shadow job/source pins unchanged.

Implement pure frozen-fit categorical resource baseline and comparators, exact
empirical at-most5% calibration order statistic/strict equality/OR union reporting,
and pooled8-count AE training with JSON scaling (no pickle) on audited exports.
Require checked contract/source/data hashes and recomputed model eligibility;
filter missing/invalid-IP rows as unscored coverage, never benign values. Save
versioned hash-bound bundle; reload/recompute check before returning success.
Primary is personal resource excess cross-entropy; population resource, AE and
volume are fixed comparators. Secondary OR=primary OR AE; no selector/tuning.

Test mathematically distinct account baselines, samecountdifferentresource case,
intent-label absence, sparse empirical threshold ties, combined-alert budget,
fit-only reference/scaling/weights, validation-only checkpoint choice,
calibration-only thresholds, contract/provenance/partial/empty refusal and
weights-only reload parity/tamper refusal. Synthetic training only until actual
normal windows close; artifacts from synthetic smoke tests explicitly tagged.
CLI check real early export should refuse without writing/training; report that
as expected, not detector failure. No activation/dashboard/risk updates. Draft PR,
human merge, manual Claude review remains user-controlled.
