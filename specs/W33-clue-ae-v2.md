# W33: one bounded CLUE AE v2 experiment

30 October 2026. User approved creation with all five Codex review corrections,
a fixed C-norm denominator, and a hard freeze gate. The user subsequently amended
the W33 gate to 15 November 2026, 23:59 MYT, before any reserved-test access.

Status: approved prospective method specification; implementation, availability
checks, data bindings, engineering tests and final release are pending. This file
is not evidence of training, test access, improved detection or live activation.
Profile: `clue_ae_v2`. Companion review:
`reviews/CLUE_AE_V2_CODEX_REVIEW_2026-10-30.md`.

## 1. Question, scope and protected work

Evaluate whether a larger later training set and an account-relative feature
bundle improve the specified detectors on recorded normal activity with fixed
injected deviations. C is the primary new candidate; C-norm is a secondary score
ablation of C, not another trained model. B is the five-feature comparison; A is
the historical reference; BL is our own simple comparator.

Only two new AE fits, B and C, are permitted. No architecture, feature, threshold,
scenario-strength or seed search. No CLUE-authors code or additional download.
Use the existing checksum-verified archive, streamed outside OneDrive; do not
fully unpack it. Private events, features, models and account-level scores stay
under ignored checkout data directories, not Git or third-party review messages.

Preserve CERT71, legacy cloud12, CLUE10, shared_behavior_core_v1, consumed results
and the frozen AWS study byte contracts. W29 and earlier no-go findings remain
reported. W33 supersedes the earlier stop on further experiments only for this
newly user-approved bounded experiment. It does not reopen or retune W29.
Keep collection operating. AWS study commitments/rehearsal take priority.

No model activation, public deployment, new cloud workload or change to live
history is authorised. One offline experiment cannot establish multi-cloud
transfer or remove a real live account's cold start.

## 2. Fixed dates and access boundary

All benchmark intervals are inclusive UTC dates:

| Role | Dates | Permitted use |
|---|---|---|
| Warm-up | 7 August–3 September 2017 | Chronological history only |
| Fitting | 4 September–26 November 2017 | Cohort, scaler, B/C fitting, C-norm references |
| Validation | 27 November–3 December 2017 | Early stopping and engineering diagnostics only |
| Normal calibration | 4–17 December 2017 | Fixed thresholds only |
| Holiday gap | 18 December 2017–14 January 2018 | Original-event history updates only |
| Reserved test | 15–28 January 2018 | Single released evaluation |

Previously inspected August windows and the decoded 25 August boundary are
development/known data, never independent test evidence. Warm-up may overlap
known data; this does not restore its independence.

Before new archive access, write an exclusive, immutable access-plan receipt
binding this specification, the existing archive checksum/manifest, reader code,
date bounds and allowed output fields. Do not claim a final model release yet.

The availability check may emit only total event counts by full calendar month
for August 2017 through January 2018, plus parse/error totals. No account counts,
identifiers, event types, feature distributions, reserved-day aggregates or
scores. Its scanner may parse timestamps to count but must not retain or expose
reserved records or pass them into feature code. This aggregate access is
declared, so January is not described as entirely unaccessed: its records,
identities and outcomes remain sealed for evaluation.

Split fallback rule: **no shifts**. If required archive coverage is absent,
monthly checking fails, or later pre-test gates fail, report no-go. Do not move
the test or inspect later months to find a better cohort. Monthly totals do not
prove account-level sufficiency.

All pre-release feature readers reject dates after 14 January 2018 and never
export January history to a diagnostic viewer. Gap events update history only;
do not compute diagnostic scores or choose methods from the gap. Reserved rows
are processed only by the released evaluator, once. No test-based retry with a
modified method; an engineering failure produces a disclosed failed attempt and
requires a new prospective decision, not an invisible rerun.

## 3. Cohort, day quality and history

Native parsing, attributable-account rules, action kinds, resource-validity
table, top-level path namespace extraction and UTC day boundary reuse the frozen
W23 definitions. Do not call namespaces buckets. Resource tokens remain
source-qualified; no invented cross-dataset identity links.

Candidate accounts have at least five original active fitting days, counted
using fitting dates only. Choose at most 500 by ascending SHA256 of UTF-8
canonical JSON `[42,"clue_ae_v2_cohort",account]`, with `ensure_ascii=False`,
separators `(',', ':')`; break any digest tie by account's UTF-8 byte order.
Fix this cohort before validation/calibration inspection. No replacements for
accounts with poor later coverage. Freeze the actual selected-cohort hash.

Do not manufacture inactive/zero-event days. A usable history day must satisfy
the existing W23 required-field/resource-quality rules. An invalid original day
is excluded from features and history, with explicit counts; do not partially
salvage it. Require at least five usable prior active days before scoring. This
is an eligibility convention, not proof that five days is a stable baseline.

Maintain two states per account: expanding prior action set for W23 feature 5,
and the last 28 usable original active days for features 6–9. Neither includes
today, an injected variant, other accounts or future observations. Warm-up and
original validation/calibration/gap days update history chronologically without
fitting the model. Original reserved days update history after that day's normal
and all variant scores have been computed. Every variant uses the same target
account's start-of-day snapshot, including C-norm's target denominator.

This benchmark assumes publisher-described original activity is normal. Live
history could contain misuse; the update policy does not prevent contamination.

## 4. Ordered feature contract

| Index | Feature | Exact definition |
|---|---|---|
| 1 | event_count | W23 accepted original/native-derived day event count |
| 2 | unique_actions | W23 distinct native action kinds |
| 3 | unique_resources | W23 distinct valid top-level namespaces |
| 4 | off_hours_fraction | Fraction outside 07:00 inclusive to 19:00 exclusive UTC, every day identically |
| 5 | new_action_count | W23 distinct kinds absent from expanding prior original history |
| 6 | volume_log_ratio | `log1p(today count) - log1p(median prior active-day counts)` |
| 7 | new_resource_share | Fraction of today's distinct valid resource tokens absent from the prior-28-active-day resource union |
| 8 | action_mix_js_distance | Base-2 JS distance between today's native-action histogram and the prior-28-active-day histogram |
| 9 | hour_profile_js_distance | Base-2 JS distance between today's 24-bin UTC-hour histogram and the prior-28-active-day histogram |

Feature 6 uses all available prior active days up to 28, requiring at least five.
An even-sized median is the arithmetic mean of the two middle values. Feature 7
uses the same bounded history, not all prior time. Globally unseen resources are
new, not unavailable. With zero distinct resources today, feature 7 is
unavailable; C, C-norm and BL exclude the day, rather than filling zero. B/A may
still score a valid resource-free day; report differing coverage.

Both histograms in features 8–9 are **event-weighted**. For action mix, take the
sorted union of kinds observed today and in the prior window. There is no
fit-only vocabulary that drops unseen kinds. For hours, always use bins 0–23.
For each distribution separately, add total pseudocount mass 1, spread uniformly
over its common support of K bins: `(count_i + 1/K)/(sum_counts + 1)`.
Compute `m=(p+q)/2`, then distance
`sqrt(0.5*sum(p*log2(p/m)) + 0.5*sum(q*log2(q/m)))` in float64.
Clamp round-off within 1e-12 of [0,1] only; reject values further outside. Reject
nonfinite results. This is JS **distance**, not the older W29 JS divergence.

Reference hours are a declared UTC convention, not inferred personal working
hours. Weekends are not automatically off-hours. W7's earlier saturated resource
novelty remains a known risk; incorporating it into a bundle does not guarantee
improvement or reverse the historical no-go.

## 5. Preprocessing and detectors

Apply log1p to count columns 1, 2, 3 and 5 only. Feature 6 is already a signed log
difference; do not log it again. Leave fractions and JS distances unlogged. Fit
StandardScaler on eligible fitting rows only, using population SD (`ddof=0`),
and scale 1 for zero variance. Persist ordered means/scales and transformations.
Use float64 feature/scaler arithmetic and float32 AE inputs/weights. Freeze
dependency versions and single-row scoring semantics before calibration.

| Detector | Method and inputs | Role |
|---|---|---|
| A | Exact existing five-feature model, transform and scaler, unchanged | Historical reference |
| B | Five W23 features; AE `5-16-8-3-8-16-5` | Larger later training-set comparison |
| C | Nine features; AE `9-16-8-3-8-16-9`; raw mean squared reconstruction error | Primary new candidate |
| C-norm | Same C checkpoint and raw error divided by fixed account denominator | Secondary scoring ablation |
| BL | `max(0,z_1,...,z_9)` using C's fit-only transformed/scaled inputs | Our own simple comparator |

B and C use Adam lr 0.001, batch 64, maximum 100 epochs, LeakyReLU(0.1) hidden
layers, linear output, seed 42, validation-loss early stopping patience 10, and
restore the best checkpoint. Validation ties do not replace the earlier best.
Use Adam betas (0.9,0.999), epsilon 1e-8, weight decay 0, amsgrad false and mean
MSE loss. Use CPU float32 training, seed Python/NumPy/Torch with 42, and shuffle
fitting rows with a dedicated Torch generator seeded 42; batch size 64,
`drop_last=False`, no worker processes. Canonical initial row order is UTC date,
then account UTF-8 byte order. Validation is unshuffled. Require deterministic
Torch algorithms; record thread/runtime settings and dependency versions in the
manifest before fitting. No scenario labels or hyperparameter search. Saved/reloaded
and canonical single-row score parity are mandatory.

B and C train on the **same nine-feature-eligible fitting days**, and early-stop
on the same validation days, B selecting its five columns. This prevents missing
resource rows from confounding their feature comparison. Record which additional
five-feature-only days were excluded. Their final comparisons also use common
eligible test/calibration days, with separate all-supported coverage tables.

A versus B changes cohort, calendar period and fitted scaling as well as data
size; it does not isolate the causal effect of data volume. B versus C compares
the feature bundle; added inputs also change the input/output parameter count.
BL is positive-deviation only and can miss decreases; do not silently change it
to an absolute-deviation baseline. No external baseline implementation is used.

### Fixed C-norm denominator decision

For each selected account, use **all of its C-eligible original fitting days**,
scored by the final restored C checkpoint with the frozen scaler and canonical
single-row inference. Require at least five such days. Let `r_u` be their median
raw MSE (usual midpoint median for an even count). Define once:

`denominator_u = max(r_u, 1e-8)`

`C_norm(u,day) = C_raw_mse(u,day) / denominator_u`

This denominator is frozen per account before normal calibration and never
updated with validation, calibration, gap, test or injected days. Nonfinite or
negative reference errors invalidate the account's denominator; fewer than five
reference days is unavailable. No population/other-account fallback. Record raw
median, sample count, denominator, floor-used indicator and excluded accounts.
The fixed numerical floor prevents division by zero; it is not tuned for
performance. All training errors are in-sample and may be optimistically small;
ratios can magnify that bias and are not probabilities of compromise.

C-norm needs its own normal-calibration thresholds. Its coverage may be smaller
than C's. Report a common-coverage comparison as well as each detector's full
eligible coverage. Never treat an unavailable denominator as Low.

## 6. Fixed scenarios and thresholds

Reuse the exact W23 native-event injection algorithms, deterministic ranking,
ID rules and safety caps in the unchanged shared_core_scenarios.py and
SHARED_CORE_RESOURCE_RULES.md, binding their actual source hashes before test.
Use the new fitting-selected cohort as the generator's declared input, without
changing the algorithm. Four scenarios only:

1. Append four copies of each eligible file-access event (five-times reads).
2. Remap eligible activity to 00:00–05:59 UTC, preserving order and date.
3. Add five resource-bearing `permission_changed` events where absent from the
   target's expanding original action history.
4. Same-date account switch with disjoint hash-ranked donor/target pairs from the
   fixed cohort, always using target history. No similarity-selected donors.

Report generated/ineligible/zero-change/invalid/unscored/scored counts. Injected
variants are offline copies, never actual attack records or cloud operations.
Mass reads do not prove exfiltration; time/action changes are not inherently
malicious. No injection-strength sweep after seeing any new scenario results.

For B, C, C-norm and BL, calibrate separately on eligible original December
calibration rows at nominal budgets 1% (primary) and 5% (secondary). Require at
least 100 calibration rows for each reported threshold. Use NumPy's empirical
`quantile(scores, 1-budget, method='higher')`; alert strictly `score > threshold`.
Record sample size, ties, index/order-statistic convention, achieved alert rate
and score precision. No top-percentage selection from mixed test data.

A uses its **original frozen** scaler and thresholds for the historical-reference
table; no December recalibration arm is added. Therefore its operating points
are not claimed to have the same December normal-alert budget. Rank metrics and
normal alert burden remain reportable on common rows. No A retraining or update.

## 7. Evaluation and predeclared interpretation

Headline: per-scenario AUROC and average precision (`average_precision_score`,
not trapezoidal PR area), with injected cases against all untouched eligible
normal test days. Secondary: recall at frozen thresholds, normal-day alert
fraction, paired original/variant score change, prevalence, accounts, calibration
resolution and all exclusions. Report both all-supported and common-scorable
comparisons; exclusions are never negatives. Pooled scenario scores, if shown,
are secondary and disclose their artificial prevalence and duplicated originals.

Predeclared descriptive comparisons:

- B versus A: report signed AUROC/AP differences by scenario and each original
  operating-point burden; describe a larger later training-set comparison only.
- C versus B: report the same deltas plus recall and normal-alert-fraction deltas
  at both December-calibrated budgets on common rows.
- C-norm versus C: report those deltas with denominator coverage and floor counts.
- BL versus C: report every scenario even when the simple method wins.

No undefined "clearly better" or automatic winner selection. C remains the
primary candidate regardless of test ranking. Call a comparator descriptively
dominant at a budget only if all four recalls are no lower, at least one is
higher, normal alert fraction is no higher, and coverage is no lower, on the
common evaluation; otherwise describe the trade-off, not a single winner. This
is a descriptive reporting convention, not statistical significance or an
activation criterion. Report AUROC/AP independently, including conflicting ranks.

Near-chance switch results mean only that these specified representations and
detectors did not distinguish these injected cases in this sample. They do not
prove an intrinsic dataset limit or impossibility of takeover detection.
Dependent account-days and variants do not justify independent-binomial or
unqualified significance claims. Do not pick a new method using this test and
then call that selected method independently validated.

Label all results: **semi-synthetic: real recorded normal behaviour with injected
deviations**. No CERT numerical superiority or real attack accuracy claim.
Do not compare unverified CLUE-author README numbers as equivalent experiments.

## 8. Engineering gates and immutable release

### Validation-only descriptive report of features 6–9

Before the freeze, produce `results/clue-ae-v2/validation-feature-descriptives.md`
using only original validation days (27 November–3 December 2017). Compute
features 6–9 with the already specified start-of-day histories; prior original
warm-up/fitting events may supply that history but are not report observations.
No injected variants, calibration days, gap days or reserved-test days enter
the descriptive report.

For each feature, report eligible/unavailable/nonfinite row counts and reasons,
account coverage, minimum, median, 5th/25th/75th/95th percentiles and maximum.
Also report exact-zero/one fractions for bounded features 7–9, and the number of
distinct values, to expose constant or saturated inputs. Use the same `higher`
empirical quantile convention for these descriptive percentiles. Record the
source, feature-contract and validation-export hashes. Keep account-level data
private and identify this as validation evidence, not independent evaluation.

This report is descriptive only: no scenario recall, method selection, feature
changes, threshold tuning or new acceptance cutoffs. It does not replace the
existing validation early-stopping rule or change any other gate. Complete and
bind the report in the immutable release before reserved-test access.

Pre-test minimum gates, fixed without new data inspection:

- At least 10 fitting-selected accounts, 1,000 common eligible fitting rows,
  100 common validation rows and 100 common normal-calibration rows for B/C/BL.
  These are pragmatic engineering sufficiency gates, not power calculations.
- C-norm requires at least 100 eligible calibration rows; if it fails, omit its
  threshold results and report the secondary arm unavailable. It does not block
  C's release. No replacement denominator or lowered minimum.
- Reader date barriers, fit-only cohort/scaler, chronological updates, untouched
  originals, variant-history isolation, all feature maths, resource missingness,
  denominator/floor handling, scenario identity, threshold ties and save/load
  parity pass meaningful tests on synthetic fixtures. Use SQLite for tests.
- Freeze source hashes, archive binding, exact cohorts/row hashes, split counts,
  feature manifest, B/C checkpoints/scalers, C-norm reference table, BL settings,
  thresholds, dependency/runtime versions, scenarios, evaluator and output schema.
- An exclusive final preregistration/release receipt binds those artifacts before
  the reserved reader can execute. Reject missing/mutated bindings. Record test
  attempt start/completion and failures. No raw reserved data in logs or reviews.

No test-based gate is used to change training or scenarios. A technically valid
but weak result remains a completed experiment, not permission to tune.

## 9. Hard time gate and deliverables

| Deadline, Asia/Kuala_Lumpur | Required state |
|---|---|
| 31 October | W33 review/access-plan implementation and binding |
| 1–5 November | Bounded extraction, engineering checks and one B/C fit each |
| **15 November 2026, 23:59 MYT** | **Complete immutable release, including the validation-only descriptive report, with every mandatory gate passed** |
| 16–17 November | Single released reserved evaluation |
| 17 November | W33 report complete by 23:59 MYT |
| 15 November | Existing project/AWS sign-off dates unchanged; W33 reporting follows the explicitly amended dates above |

Missing the 15 November, 23:59 MYT gate is **no-go for W33 reserved evaluation**. Do not move
the date, compress review, open test early or relax gates. Record development
work and protect the AWS study instead. Its commit-by-5-November, 6-November
rehearsal and later frozen study dates remain intact. User handles Git commits;
no automatic staging, push or publication.

Deliver `results/clue-ae-v2/report.md`, `metrics.csv`, per-scenario ROC plots and
provenance/coverage summaries. Preserve negative and unavailable arms. Any later
CLUE replay UI is separate, labelled offline, and requires integration checks;
it is not part of this model's live activation. The real multi-provider POC
continues through collection, native attribution, approved identity links and
investigation timelines while detection evidence is evaluated separately.

### Prospective amendment record

On 30 October 2026, before 7 November and without reserved-test access, the user
explicitly authorised moving only W33's freeze gate to 15 November 23:59 MYT,
the single reserved evaluation to 16–17 November, and report completion to
17 November, and adding the validation-only descriptive report of features 6–9.
This supersedes W33's original 7 November / 8–10 November delivery dates and its
15 November reporting deadline only. Benchmark split dates, features, detectors,
C-norm denominator, scenarios, thresholds and other gates remain unchanged.
AWS study dates remain unchanged. The original W33 specification SHA256 was
`119b9c2e7d44bffe62330ee6c98e49f05f565baa3a028a8f651bc19185c8f6dc`.
