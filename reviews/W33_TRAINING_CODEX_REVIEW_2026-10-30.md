# Codex review: W33 training handoff

30 October 2026. Reviewed `docs/CLUE_AE_V2_TRAINING_HANDOFF.md`,
`scripts/train_clue_v2.py` and its tests in the active worktree. Independently
ran all 11 training tests: passed. Tests use synthetic exports/checkpoints.
Read the already exported real pre-test data to verify coverage only; no model
was fitted, no preregistration created, no reserved row or archive record opened.

## Verdict

The core numerical flow matches W33: common B/C rows, fit-only transforms,
declared architectures/optimiser, deterministic seeding, strict early-stop ties,
canonical single-row score parity, fitting-only C-norm medians frozen before
calibration, separate thresholds and no live activation.

Do not consume the real training attempt yet. Fix the following guards and
coverage accounting first, without changing W33's method, splits or thresholds.

## 1. Recompute the engineering gates before preregistration and fitting

`load_export` checks only `engineering_gates_pass is True`. It does not recount
and enforce the actual selected accounts or common eligible partition rows.
A synthetic reproduction was accepted with 8 selected accounts, 214 common fit
rows and 56 validation rows, below W33's 10 / 1,000 / 100 minima.

Required change: recompute the existing W33 minima (including calibration >=100)
from the verified cohort/row files before any attempt claim or model call, and
check consistency with the manifest's gate/coverage claims. Validate cohort
uniqueness and row eligibility/finite numeric invariants. Bind the gate constants
in the training method/preregistration. Test fixtures may explicitly patch/bind
smaller engineering minima; production defaults remain W33's exact constants.

The actual reviewed export passes the declared counts, so this is a guard fix,
not a request to change its cohort or collect more data.

## 2. Verify the export's source provenance, not only its file checksums

`load_export` currently ignores `manifest.source_sha256`. The training receipt
then binds current code alongside potentially stale exported features. Changing
feature implementation without updating its contract label could therefore pass
these checks, even though the export was produced by different code.

Required change: compare the export's full expected source/dependency binding
with the producing sources, fail on missing or changed entries, and carry that
binding into the preregistration. Preserve the existing successful reader and
availability provenance; don't reconstruct an apparently new origin from the
current code. It is sufficient to verify the bound pre-test artifact chain;
training need not decode or reopen the native archive.

Add regression tests showing stale/missing producer bindings stop before fitting
even when row files and their listed checksums are otherwise valid.

## 3. Include zero-fitting-row accounts in C-norm coverage

`c_norm_references` enumerates only accounts appearing in C-eligible fit rows.
The real cohort has 74 accounts, but only 71 appear in those rows: **three selected
accounts currently disappear from the reference table and unavailable count**.
Calibration already skips absent references, so the problem is incomplete
coverage accounting, not a request to invent a denominator.

Required change: pass the fixed cohort into the reference builder; emit an
explicit unavailable record with `reference_days: 0` for selected accounts with
no eligible fit rows. Preserve the exact minimum-five, midpoint median, floor
1e-8 and no-fallback rules. Reject accounts outside the bound cohort. The
available/unavailable totals must sum to the selected cohort, and calibration
exclusions must remain visible. Add a zero-row-account test.

## 4. Protect the single experiment, not only a receipt pathname

The exclusive attempt currently prevents reuse of the same preregistration,
but another preregistration pathname permits another B/C fit of the same W33
experiment. The module docstring's "rerun needs a new visible preregistration"
must not imply that this is authorised automatically: W33 permits only one real
B and one real C fit.

Required change: add a shared experiment-level exclusive attempt claim covering
all real W33 preregistration/output paths in this checkout, bound to the declared
experiment/profile. A failed attempt stays claimed and disclosed. A new receipt
alone must not permit another real fit. Synthetic reproducibility tests should
use separate isolated experiment workspaces, without a production bypass flag.
Test that two receipt paths in one experiment cannot trigger duplicate fitting.

## Accepted implementation interpretations

- Seed reset for each detector is consistent with seed 42 and independent
  reproducibility. B/C have different input sizes, not shared weights.
- Batched validation MSE for early stopping is acceptable; canonical single-row
  inference remains the rule for persisted scores and calibration.
- BL's float32 scaled inputs match the established comparator convention.
- Exact preregistration/training environment matching is appropriate. Record
  Python/platform versions as additional provenance if convenient; this is not
  permission to change pinned model/training settings.
- Keep the validation-only descriptive report bound into the final release as
  W33 requires; the training receipt is not that final release.

## Return requested from Claude

Implement these corrections and focused regression tests only. Do not run the
real preregistration or training commands. Return the changed paths and test
evidence for one final Codex review, preserving all existing private artifacts.
No scenario recall, reserved access, feature tuning, model activation or AWS
study changes. Final gate remains 15 November 23:59 MYT; single test 16–17 Nov.
