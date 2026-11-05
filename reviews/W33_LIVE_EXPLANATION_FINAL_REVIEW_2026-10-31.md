# Corrected live compatibility/explanation modules: Codex review

31 October 2026. Reviewed the updated workspace copy of
`docs/CLUE_AE_V2_LIVE_COMPATIBILITY.md` and the two implementation modules/tests.
The supplied OneDrive document path did not exist; the updated corrections were
present in this worktree.

## Verdict

**The three previously reproduced blockers are addressed.** Independently ran
the corrected targeted suite: **12 passed** (five audit, seven explanation tests).
No new blocking correctness finding in this review. This approves the modules
for their stated read-only diagnostic/explanation use, not live risk activation,
transfer accuracy, a production deployment or the missing dashboard receipt.

## Verified corrections

- Cutoff validation rejects naive input and normalizes aware input to UTC.
  Ingestion times are parsed as instants; malformed/future ingestion gets counted
  exclusions. SQL no longer applies an offset-sensitive lexical cutoff.
- `explain` accepts the History before commit, recomputes the snapshot, and
  rejects committed/future chronology and differing snapshot fields. Facts and
  error terms therefore use the matching start-of-day features through this
  entry point. Callers must use `explain`, not call the internal fact helper with
  arbitrary mutable state. Full source/scope/account/day identity is returned.
- Uniform hourly histories no longer imply all events are outside usual hours.
  The descriptive 5% hour convention is explicit and is separate from detector
  reference hours and rarity-rule timing.
- Lifetime-novelty and majority wording are corrected. Action-share ties have
  deterministic name ordering.
- Per-feature output distinguishes squared residuals, additive MSE terms and
  shares of reconstruction error in transformed/scaled space. Sum agreement is
  algebraic with floating-point tolerance, not a bit-for-bit summation guarantee
  in arbitrary clients.
- Actual fitting min/max are computed from bound fitting rows, separately from
  the descriptive large-|z| statistic. Neither is a live accuracy estimate.
- Handoff wording now preserves unsupported service/infrastructure entities as
  security subjects and distinguishes projection-valid observed days from
  complete normal history. The 3–4 Nov date is conditional, not a promised result.

I did not independently rerun the reported full 615-test suite or repeat model
inference on real live data. No training, release, reserved-window access, source
map mutation, activation or live-store write was performed for this review.

## Remaining integration contract

The audit remains an aggregate compatibility diagnostic. The dashboard needs a
versioned per-account/day receipt with:

- full source/scope/account/day identity and cutoff;
- model/scaler/profile/extractor/explainer hashes and source projection version;
- start-of-day history provenance, source timezone and transformed feature names;
- explicit input eligibility, why-unscored and completeness-unknown status;
- raw detector score, additive/share terms, facts and stated limitations;
- clear diagnostic-only / no-live-activation labels, with no live risk tier derived
  merely from a CLUE reference cutoff.

**Do not wait for the first real eligible day to define this interface.** Build
and test the receipt on synthetic fixtures now, then populate it from eligible
live data under the same verified contract. Codex can consume it in the isolated
UI as account-day diagnostic context, not the asserted cause of a legacy rule
finding. That association must be explicit.

GitHub repository activity still needs a separately versioned live projection.
Leave the frozen W23 map, original native event labels, W33 features and reserved
evaluation unchanged. Unsupported activity remains unavailable until that adapter
is reviewed. This review does not restore the failed AWS study coverage gates.

## Minor documentation cleanup

The original explanation section still lists the earlier five tests, “never seen”
and “dominant/mostly” wording, while the correction section supersedes it. Update
the main section to the final API/wording and keep the dated correction record as
history, so future readers do not implement the old interface by mistake.
