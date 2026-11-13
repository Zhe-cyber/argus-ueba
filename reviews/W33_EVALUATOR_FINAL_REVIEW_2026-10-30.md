# W33 evaluator: final correction review

30 October 2026. Codex review only. Claude retains offline implementation,
release preparation and evaluation ownership. No offline source was edited, no
model trained, no real release created, and no January test access performed.

## Verdict

The three requested correction groups are implemented. No remaining blocker
found in this review to Claude preparing the immutable release under W33.
This is engineering approval, not a detection-performance or live-transfer result.

Independent verification:

- **25 evaluator synthetic tests passed**, including positive release creation
  and verification, evidence mismatch refusal, deadline crossing, invalid release
  timestamps, generation/scorability reconciliation and unavailable vectors.
- Real validation-report verification passed by in-memory reproduction from the
  already exported validation rows; nothing was overwritten.
- The saved `evaluator-rehearsal-v2.json` binds the current evaluator source
  closure, training manifest, preregistration and original v1 release. It records
  **4,917 rows reproduced**, threshold parity and no test rows accessed. This
  review checked those bindings, not a repeat native-archive rehearsal.
- Neither a real W33 release file nor the reserved-access claim existed at the
  end of the verification checks.

## Fixes confirmed

1. Release now checks the A/v1 rehearsal binding and thresholds, explicit parity
   flags and row count, and exact validation-report content/provenance. Report
   dependencies are included in the evaluator source closure.
2. The freeze time is checked before work and immediately before finalizing the
   receipt. Verification rejects invalid, naive, noncanonical or late creation
   timestamps. The separate 16–17 November execution window remains enforced.
3. Generated, retained, wholly unscorable and per-detector scored/unscored
   denominators reconcile. Missing vectors are unavailable rather than unchanged.
   Metric formulas, frozen thresholds and scenario strengths are unchanged.

## Next step belongs to Claude

Prepare the release using the reviewed code, the correct validation report and
fresh v2 rehearsal. Record the resulting release SHA256 and preserve the bound
artifacts. A source change requires the appropriate fresh pre-test rehearsal;
do not silently repin a released experiment.

Hard freeze: **15 November 2026, 23:59 MYT**. Single reserved evaluation:
**16–17 November**, report by **17 November**. Do not execute it early to fill
dashboard scores. Post-evaluation markdown/metrics CSV/ROC packaging remains
pending. No automatic activation, retraining or AWS study-date change.
