# Prospective live AWS lab method v1

Specified29 October2026 before real fitting starts, before validation/calibration
scores or reserved cases. Completes method choices required by protocolV2; code
and artifact hashes accompany the implementation/bundle. Amendments require a
new version before affected future data. No positive performance is assumed.

## Data and eligibility

Use only aws_lab_daily_v1 exports, exact contract hash
1612cd7401704efef92d0c462543f3eeebf5c7c0cbe39285998299b498688ebc.
Eight ordered MY-day counts and descriptive resource/action/hour counts retain
the contract's semantics. No CERT/CLUE/legacy-cloud weights, scalers or cutoffs.
Windows stay30Oct-5Nov fitting,6-7Nov validation,8-10Nov normal calibration;
29Oct warm-up and11Nov excluded;12Nov unannounced/13Nov approved control held out.
This implementation consumes normal export files only, never reserved cases.

Revalidate byte hashes, exact feature/export code bindings, unique role/date rows,
partition/date/closed-day labels, count/context consistency and native-verified
coverage. Require complete_day, at least90% planned actions verified and no
unresolved receipts. Missing/invalid IP rows are unscored for this first method;
they do not teach zero IPs as normal. Publish their exclusions. Recompute gates
after exclusions rather than trusting a ready flag.

Stricter bundle gate: all six roles must each have at least5 fitting dates
spanning7 calendar dates,2 validation and2 calibration dates. At least30 fitting
account-days and12 calibration account-days over3 calibration dates. All roles
are reported if the gate fails. This small correlated sample supports an
experimental controlled-machine case study, not enterprise detection accuracy.

## Primary: account-conditioned resource context

Fixed seven-category domain p01-p06/confidential. For role u, accumulate its
fitting event resource counts n_u only. Form a peer distribution from all OTHER
roles' fitting resource counts with0.5 added to each category and normalise.
Shrink the role toward that peer distribution with5 pseudo-events:

    p_u(c) = (n_u(c) + 5 * p_peer_without_u(c)) / (sum(n_u) + 5)

No per-role neural model. Freeze these probabilities after fitting. For a daily
resource histogram q, primary score is mean negative log probability minus the
role reference entropy:

    S_u(q) = sum_c q(c) * (-ln p_u(c)) - H(p_u)

q is normalised daily event counts. Natural logarithms; scores may be negative.
Entropy centering reduces per-role diversity offsets; it is not a probability or
guarantee of comparable false-alert rates. Known rare/unseen-for-role categories
retain positive prior mass. Truly outside-domain resources are unscored/refused,
not mapped to an arbitrary favourable token. Role labels select fitting reference
only; approved/unannounced scenario context never enters scoring.

## Fixed comparators

- Population resource score: pooled fitting counts +0.5/category, same entropy-
  centered cross-entropy, independent of role reference.
- Population AE: shared8-4-2-4-8, Tanh after each encoder layer and hidden decoder
  layer, linear output;98 trainable parameters. Transform counts with log1p then
  fitting-only mean/std (population ddof0, zero variance scale1). CPU PyTorch,
  seed42, deterministic algorithms, one thread, full-batch Adam lr0.001,
  weight_decay0.001, gradient norm clip5,200 epochs. Select earliest minimum
  validation MSE checkpoint by strict improvement; no hyperparameter search.
  Raw standardized reconstruction MSE is its score; no min-max clipping.
- Volume only: absolute log1p(event_count) deviation from pooled fitting median,
  divided by max(1.4826*fitting MAD,0.1).

AE requires at least two nonconstant fitting features. Constant/correlated count
features, actual training sample/parameter counts and validation loss must be
reported. An overfitting or ineffective AE remains a negative comparator result;
no automatic replacement of the primary method. Categorical resource evidence
is not inferred from the eight-count AE or presented as SHAP.

## Calibration and fixed decisions

Freeze reference/scaler/weights before calibration. For each component, sort its
n finite normal-calibration scores ascending; let k=floor(0.05*n). Set threshold
to value at zero-based index n-k-1. Alert iff score STRICTLY GREATER. Ties are
retained, never broken by role/label/random jitter. At n12-18,k=0: threshold is
the observed maximum, so strict calibration alerts are zero; this does not prove
zero future false alerts. Tail resolution is1/n; report denominators and counts.
No confidence/probability guarantee, no reuse of CLUE's0.764853 cutoff.

Report primary, all comparators and secondary fixed OR(primary,AE) normal alert
fractions separately. If OR exceeds5% of normal-calibration account-days, mark
the combined rule no-go; do not retune either threshold. A constant calibration
score, nonfinite score or primary threshold at/above any role's attainable
maximum yields a flagged no-go component/role, never silent Low coverage.
Attainable primary upper bound is max_c(-ln p_u(c))-H(p_u), not a fitted test score.
Report per-role calibration fractions and ceiling checks as well as pooled values.

No online updating during validation/calibration/test. Store normal validation
and calibration results and fixed thresholds, not detection-accuracy claims.
Validation chooses AE checkpoint only, never categorical hyperparameters.

## Artifact, evaluation and release boundaries

Save a fresh private bundle containing weights-only checkpoint, JSON scaler,
JSON frozen references, calibration report and manifest with exact dataset,
contract, method, source and artifact hashes, environment, seeds, windows and
exclusions. Recompute scores after reload and refuse drift/tampering. Synthetic
test bundles are explicitly tagged and cannot be used as real-study artifacts.
No joblib/untrusted pickle or automatic model installation.

At11Nov freeze, retain the bundle only if coverage/compatibility gates hold;
record no-go reasons. Scenario executor and evaluator must be separately tested
before the reserved12/13Nov cases; they must use these frozen references without
updates. Report target roles and all normal/control outcomes with missingness,
not malicious-intent accuracy. The matched approved-change case may be equally
unusual; analyst context is separate. No guaranteed superiority to comparators.

Training completion alone never activates live risk tiers. Keep the main view
Unknown pending a compatible, evaluated release and explicit activation decision.
First method scores only CLOSED eligible AWS lab days, not partial event streams,
genuine human accounts, Cloudflare/GitHub or linked multi-cloud identities. Legacy
shadow MSE continues independently.15Nov fallback remains pipeline plus frozen
offline/negative evidence if live qualification fails.
