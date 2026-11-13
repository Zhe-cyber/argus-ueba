# W23: shared-core behavioural candidate

Status: definitions fixed for the first isolated training preregistration,
30 October 2026. Separate reserved-evaluator release pending; no live activation.
Source: manually relayed direction-decision handover v2.

## Goal and boundaries

One public-data-trained AE, the same extractor applied to each account/source/day,
and a separate approved-identity investigation timeline. Detection does not require
two providers to deviate. Benchmark detection, live compatibility and identity
correctness are separate claims. Existing contracts and the AWS study stay unchanged.
Candidate profile: shared_behavior_core_v1. No deployment or shadow activation.

## Proposed inputs

Every event needs source namespace, attributable account, native evidence reference,
zoned timestamp, canonical native action, optional resource and provenance/missingness.
Deduplicate native IDs within source namespace; conflicting duplicates fail.
Group closed reference-timezone days per account/source. Do not invent zero-event
days when collection completeness is unknown. Identity links are not model inputs.

Ordered features:
1. event_count: accepted deduplicated events.
2. unique_actions: distinct canonical native kinds.
3. unique_resources: distinct observed identifiers at declared granularity.
4. off_hours_fraction: fraction outside the declared time-of-day interval,
   identically on every day of the week.
5. new_action_count: distinct kinds absent from history strictly before that day.

Resource-free event types do not imply missing required data. Missing a resource
required by its event type makes the day incompatible, rather than silently
dropping events. Freeze an expected-resource table before training. A legitimate
day consisting only of resource-free events may have zero resources.

## Source definitions and verified adapter gaps

| Source | Action | Resource | Reference hours |
|---|---|---|---|
| CLUE | exact type | first nonempty primary-target path component, audited on fitting data | Daily 07:00–19:00 UTC |
| AWS | eventSource plus eventName | service-specific; S3 bucket in current adapter | Daily 08:00–20:00 Asia/Kuala_Lumpur |
| GitHub | native type via exhaustive tested label mapping | repository full name | Daily 08:00–20:00 Asia/Kuala_Lumpur |
| Cloudflare | native action; decision separate when available | application domain | Daily 08:00–20:00 Asia/Kuala_Lumpur |

Start inclusive, end exclusive; weekends use the same time-of-day rule as weekdays.
Decision recorded 30 October 2026: choose option A, time of day only, before new
training or reserved-test inspection. This feature deliberately does not measure
weekend novelty. Moving activity to night hours changes its timing representation
but does not guarantee detection or establish maliciousness. Existing CLUE10,
CERT71, legacy cloud12 and frozen AWS-study definitions remain unchanged.
Reference hours are not verified
personal working hours. Resource tokens are source-qualified. A CLUE top-level
namespace is not called a bucket. Do not case-fold or filesystem-resolve paths.
CLUE's UTC window is a reference convention, not users' European local hours;
no personal timezone or actual working-hours inference is claimed.

Checked backend/normalizer.py: AWS retains eventSource and eventName, but its
stringified request-parameter fallback needs explicit handling. GitHub persists
display labels, so unknown/ambiguous reverse mappings fail compatibility.
Cloudflare defaults absent allowed to True and does not persist the boolean.
An unsuffixed action cannot prove allowance. Native action projection can be
considered separately; old decisions cannot be recovered by assumption. The implemented shared core uses native Cloudflare action kind, not access success; see SHARED_CORE_RESOURCE_RULES.md for exact eligibility and limited AWS support.

## History

Set k=5 prior observed active days for this candidate. The development audit
retains 543/605 fitting days and 169/169 calibration days at k=5; k=7 retains
454/605 and 168/169. Choose five as a pragmatic history/coverage compromise,
not evidence that five days establishes a reliable baseline. No injected recall
was used. See docs/SHARED_CORE_DEVELOPMENT_AUDIT.md.
Below k, Unknown; unavailable novelty is never zero-filled. Use chronological
prior-day history only. Use expanding history of original observed events through
the previous day, including earlier test days. Score all variants against the same
start-of-day snapshot, then update once using only that day's original events.
Never update with injections. Keep model, scaler and thresholds fixed. This is
chronological online feature state, not fitting on test labels. In the benchmark
original events are publisher-described normal; in live use observed events may
contain misuse, so history contamination remains a limitation. The policy can
match live operation without proving distributional transfer or live accuracy.

## Proposed single training run

Fit-only log1p on four count features, unchanged off-hours fraction, then fit-only
StandardScaler. AE: 5-16-8-3-8-16-5; LeakyReLU hidden layers, linear output;
score is mean squared reconstruction error in transformed/scaled space.
Adam learning rate 0.001, batch 64, seed 42, max 100 epochs, validation-loss early
stopping patience 10; restore best checkpoint. No architecture search or scenario
labels in fitting, checkpoint selection, scaling or calibration. Pin dependencies;
persist ordered features, scaler and hashes; verify saved/reloaded score parity.

## Training freeze and reserved-release boundary

The namespace audit, k choice, exact resource/action rules, generator rules and
core/training tests are complete for the first isolated candidate. Exact tables
and all fixed hyperparameters: docs/SHARED_CORE_RESOURCE_RULES.md.
A training preregistration binds this document, the protocol, source files and
native-derived development feature export before fitting. No reserved rows enter
that export. Capture-start warm-up observations count as prior observed activity;
only the declared fitting/validation/calibration rows are model inputs.

A separate evaluator/replay implementation and immutable release binding the
model, scaler, thresholds, evaluator and protocol must precede any reserved test
access. The development ZIP reader currently rejects reserved access outright.
A failed gate is a documented no-go, never invented input or an automatic live
priority. No live model release is authorised by this training freeze.
