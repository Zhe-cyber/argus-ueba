# W33 corrected training code: final pre-fit review

30 October 2026. Reviewed the corrected Claude handoff and training script.

All four requested fixes are implemented: engineering minima are recounted from
verified files and agree with manifest coverage; producer source hashes are
checked; C-norm represents the full selected cohort; and an experiment-level
exclusive claim prevents a second fit through another preregistration pathname.
No W33 model, feature, scenario or threshold-selection rule was changed.

Independent verification: **101 W33 focused tests passed**, including the 27
corrected training tests. Tests use synthetic exports and isolated workspaces.
The real pre-test export passes read-only validation: 74 selected accounts,
3,468 common fitting days, 275 validation days and 510 normal calibration days.
The reference builder covers all 74 accounts, including the three with no
eligible fitting rows. No real training claim or preregistration existed at
this review's completion.

Accepted implementation interpretations remain those in the earlier review:
per-detector seed reset, batched validation loss for early stopping, canonical
single-row reporting/parity, and BL on the declared float32 scaled inputs.
Source provenance validation does not require decoding the native archive.

Approve the one previously authorised B/C training attempt after its exclusive
preregistration is written and verified. Preserve the claim on any failure;
do not automatically retry. Keep original training outputs unchanged after
success. This is a training candidate, not the final evaluator release or a
claim of improved detection. No reserved-test or live-model release follows.

The final freeze gate remains 15 November 2026, 23:59 MYT; the one reserved
evaluation remains 16–17 November, with report by 17 November. AWS study dates
are unchanged. The earlier 11-test evidence in the handoff is historical;
its correction section and the independently repeated 101-test run are current.

## Pre-fit CLI correction

The first real preregistration invocation saved a complete, integrity-verified
`training-prereg-v1.json`, then returned failure while printing an obsolete
`nine_feature_rows` key. The corrected receipt schema names it `recounted_gates`.
No fit claim existed, no checkpoint was created, and no model fit occurred.

Codex corrected that output key and added an end-to-end `main()` preregistration
test that verifies the saved receipt, emitted summary and absence of a fit claim.
The v1 receipt is preserved as historical evidence; because source bytes changed,
the corrected implementation must be bound to a new v2 receipt before the single
fit. This is not a retry of B/C training or a changed W33 method.
