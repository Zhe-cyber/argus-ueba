# W2: Separate CLUE AE and reproducible Colab workflow

27 October 2026. Prepare new offline files in the original master checkout,
preserving existing edits. Publish only explicitly selected files on the review
branch w2-clue-colab (parent PR #15), leaving master checked out and uncommitted.
No user changes or datasets enter the review commit; do not merge draft PRs.

Implement a separate ten-input CLUE AE/scaler with log1p then train-only
StandardScaler, normal validation model selection and independent normal
calibration. Predeclare a 99th-percentile calibration MSE threshold. Store
model/scaler/data/profile/code/environment hashes, UTC cutoffs, frozen fitting
population and partition counts. Never install these as AWS/CERT artifacts.

Training must not consume held-out feature values. Explicit evaluation is a
separate command against the frozen bundle, reporting held-out normal alerts,
rate/uncertainty and coverage only, not attack recall or enterprise accuracy.
Validate schema/quality, fit-only eligibility, closed capture boundaries,
disjoint dates and output non-overwrite. No live-data training or deployment.

Create a Colab notebook pinned to an immutable reviewed implementation commit,
accepting only the local feature JSON after SHA256 verification. Training and
evaluation require separate explicit flags. Tests use synthetic fixtures only;
check saved inference, scaler fitting, calibration, artifact tampering, held-out
isolation and deterministic repeat fits. Preserve the 71/12-feature contracts.
