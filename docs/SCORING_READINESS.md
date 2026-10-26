# Why connected accounts can have Unknown risk

Collection and inference are separate. Real events can be normalized, stored and
displayed even while the cloud AE is unavailable. Unknown means no AE score; it
does not mean Low risk or a confirmed attack. Rule/rarity output does not silently
replace the final AE risk score.

The live worktree has no cloud model/scaler because these artifacts are excluded
from Git. The original checkout contains a separate 12-feature cloud checkpoint
and scaler. In-memory inspection confirmed input dimension, exact feature order
and scaler dimension match the frozen cloud contract. The 71-feature CERT model
is a different detector and is not a substitute for cloud events.

The existing cloud training workflow uses the flaws.cloud AWS benchmark. That
checkpoint is a prototype option, not evidence of calibrated accuracy on the
new AWS/Cloudflare/GitHub population. Its checkpoint does not embed a complete
training-data provenance manifest. No artifact was copied, activated, overwritten
or retrained by the readiness change. All real events and stored scores remain
unchanged. Original models are preserved.

Live stats and account detail now return a safe scoring_status: missing artifacts,
not loaded, load failed, or ready. This does not run inference, disclose server
paths or echo load errors. The dashboard/detail notice explains the state; the
dashboard separately counts unscored accounts and avoids ranking them as high risk.
Ready models remain labelled provisional pending local/source validation. An
explicit flaws-cloud-prototype profile identifies the benchmark origin; the
default profile leaves provenance unverified.

## Planned cloud AE training

This is training a new checkpoint of the same AE-only architecture and cloud
feature contract, not changing the detector to IF+AE or inventing a new algorithm.
Training is not currently running.

1. Collect representative normal activity from approved test identities/personas.
2. Separate normal training and calibration periods chronologically.
3. Fit the scaler and AE using training data only; calibrate thresholds using
   separate normal activity. Save feature order, model/scaler hashes, dataset
   hash, source coverage, split boundaries and threshold version in a manifest.
4. Freeze the model, then evaluate later normal activity and a controlled account
   behaviour change. Keep scenario labels out of model inputs and report missed
   detections and false positives.

The current 54 events establish connectivity and ingestion; they do not support
an enterprise detection-accuracy claim. Follow CONTROLLED_EVALUATION.md for the
six-persona proposal and limitations. Historical CERT results remain separate.
