# Codex review: CLUE AE v2 draft

30 October 2026. Reviewed against the frozen W23 contract, training implementation
and W29 no-go. Input: the user's relayed `clue-ae-v2-spec-for-codex.md`.
This is a design review, not a preregistration or training release. No fresh CLUE
rows, monthly counts, reserved data, or new model scores were accessed.

## Decision

Support one bounded offline v2 experiment, subject to the corrections below.
It can strengthen the detection evidence behind Argus. It does **not** by itself
deliver live multi-cloud scoring: matching feature definitions, real account
history, source applicability and transfer checks remain necessary. Do not pause
the collection pilot or alter the frozen AWS study to run this experiment.

The user's relayed scope permits our own baselines only. Do not download or run
the CLUE authors' code. Treat their reported numbers as unverified contextual
claims until the original publication/README and exact definitions are checked;
omit them from the result comparison meanwhile.

## Required corrections before W33 is frozen

### 1. Remove the network/training confound

W23 actually uses `5-16-8-3-8-16-5`, batch 64. The draft proposes
`d-32-16-4-16-32-d`, batch 256. Thus its A/B comparison changes the network and
optimisation as well as data. It cannot isolate data volume.

Recommended bounded design:

- A remains the exact historical frozen model/scaler; report its original frozen
  thresholds as external-reference operating points.
- B retains W23's architecture, transformations and training settings, with only
  the declared later fitting/validation data changed.
- C uses `9-16-8-3-8-16-9` and the same training recipe as B. Record that adding
  inputs changes the input/output parameter count, even with fixed hidden layers.
- C is the predeclared primary new candidate. C-norm is a secondary scoring
  ablation of that same checkpoint; BL is the fixed simple comparator.

A versus B still changes cohort, calendar period and normalisation statistics.
Call this a **larger later training-set comparison**, not causal proof that data
volume caused a gain. Do not add another training arm just to rescue attribution.
B versus C is the account-relative-feature bundle comparison, not evidence of
which individual new feature helped. There is no individual-feature ablation.

### 2. Freeze the feature maths, not just feature names

Keep the first five W23 feature meanings, including time-of-day-only off-hours,
source-qualified top-level namespaces and start-of-day rolling history.
Declare the following before extraction/training:

- The exact 28-active-day queue, eligibility, smoothing mass and action vocabulary
  for each JS calculation; distinguish JS **distance** from JS divergence and
  record log base, zero-mass handling and bins. Unseen action kinds stay visible.
- Whether new-resource share uses all prior history or the prior 28 active days.
  Prefer the latter for this new contract to reduce unequal history horizons;
  document the change explicitly. Globally new namespaces remain novel.
- Resource-free days cannot silently become zero novelty. Specify unavailable
  feature handling and report excluded days; no manufactured resources.
- Feature 6 is already a signed log difference. Never apply log1p to it again.
  Apply log1p only to the four original count columns; leave ratios, fractions
  and JS values as declared before fit-only standardisation.
- Define whether prior histograms are event-weighted or day-weighted. Use the
  same choice in benchmark and any later live implementation.

W7 already found saturated equal-history resource novelty on CLUE. This is a
known risk, not an untested breakthrough. Adding it to an AE is a new bundle
experiment; it does not invalidate the earlier no-go or guarantee improvement.

### 3. Bind history and the archive-access boundary

Before the permitted monthly count check, save the exact check implementation,
output fields and split fallback rule. Example deterministic fallback: shift all
partitions together by whole weeks, with a declared maximum number of shifts,
then stop if insufficient. Monthly totals alone do not establish per-account
eligibility; sparse cohorts discovered later must trigger the declared gate,
not an improvised split change.

Do not decode January account rows while doing the availability check. Record
what was accessed. Verify archive coverage without assuming the proposed dates
exist. Do not treat the prior archive download as permission to inspect the test.

Choose and freeze fitting warm-up dates and how they affect cohort eligibility.
The cohort rule uses fitting activity only. Freeze the SHA256 ranking encoding,
seed representation and tie-break. Report eligible/selected/excluded accounts.

The holiday gap needs a clear history policy. Recommended: ingest original gap
events into chronological feature history only, with no model fitting,
calibration or score-driven decisions. Before test release, all access remains
bounded to pre-test dates. Inside the test, score every variant against the same
start-of-day state, then update once from the original day only. Report the
assumption that original benchmark history is normal and the live contamination
limitation.

### 4. Fix thresholds, denominators and the C-norm definition

A has two distinct possible roles. Keep its **original frozen** operating points
as historical-reference results. If also reporting an A threshold recalibrated
on December normals, label that as recalibrated and freeze it separately before
January access. Never call a changed threshold the original frozen detector.

For C-norm, freeze precisely which original, eligible fitting days contribute
MSEs, numerical zero handling and minimum denominator history. Training-day
errors are in-sample and can be optimistically small; disclose that limitation.
Nonfinite/zero denominators cannot silently produce Low. Define unavailable
scores and coverage without looking at test outcomes. This operation is an error
ratio, not a probability of compromise.

BL must use the identical eligible nine-feature rows and fit-only transforms as
C. Freeze whether max deviation is positive-only or absolute, handling of zero
fitting SD and ties. Positive-only deviation deliberately ignores decreases.

Report per-detector coverage and comparisons on common eligible days. Calibration
counts and the exact order statistic/strict `>` must be recorded separately for
every scoring rule and budget. Empirical calibration budgets do not guarantee
the same future false-alert rate.

### 5. Narrow the interpretation and freeze the acceptance decision

Replace "near chance for every detector means dataset/task limit" with:
"these specified representations and detectors did not distinguish these
injected switches on this reserved sample." It cannot establish an intrinsic
limit of CLUE, all activity logs, or all takeover detection.

Replace "clearly better" with predefined descriptive comparisons, including
normal alert burden and coverage. Do not choose a new winning model, threshold,
feature set or scenario after seeing the test and then claim independent
validation. Any selection based on this test must be labelled exploratory.
Account-days and paired injected variants are dependent; avoid treating them as
independent observations for significance claims.

Reusing the four scenario definitions is reasonable, but bind the exact generator
code and parameters, donor pool/ranking and eligibility/exclusion rules. Report
all scenarios and failures. Keep mass access a volume injection, not proof of
real exfiltration; night-time and new-action changes are not inherently attacks.

## Delivery and time gate

The 7 November freeze remains a hard gate; a missed gate means no reserved test,
not a shortened release review. The AWS source-commit/rehearsal dates remain
protected. Do not describe an estimated week of work as a guaranteed result.

Before any new data access, create W33 plus an immutable access/protocol receipt.
Then implement extraction and tests, run the bounded availability/cohort gates,
train B/C once, freeze their artifacts and the evaluator, and only then release
the reserved test. Synthetic engineering rehearsals must remain clearly separate
from the reported evaluation. No live activation is authorised by this review.

For the lecturer: "We propose one controlled AE revision using longer history and
account-relative features, compared with the previous model and our own simple
baseline. Its untouched test will determine whether it helps. The live collection
and investigation workflow continues independently; live detection is not yet
validated."
