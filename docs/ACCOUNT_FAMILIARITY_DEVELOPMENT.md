# Account familiarity: development comparison

28 October 2026. Fixed method spec committed in `eb03e80`; implementation
committed in `bbb1a70` before candidate calibration or switch scoring.
This is a separate **statistical companion**, not a retrained AE, live scoring
release or untouched evaluation. The original ten-feature AE stays frozen.

## Method

The ten-count personal reference missed the original switch cases. This
candidate represents which resources/actions were observed under each account,
using the separate source-scoped literal resource contract from PR #21.
Each account-day contributes distinct resource and exact native-action tokens;
repeated events do not increase a token's daily incidence. Actor identity is
never prefixed into a resource token. Fit only on 13-26 July 2017, with the
same frozen 55-account population. Later rows never update the vocabulary,
incidences, eligibility or reference, including normal calibration rows.

For a fitting-known token, the pooled daily-incidence estimate is
`(pooled_dates_containing_token + 1) / (total_usable_account_dates + 2)`.
The account estimate is
`(account_dates_containing_token + 5 * pooled_estimate) / (account_usable_dates + 5)`.
The token contrast is `max(0, log(pooled_estimate / account_estimate))`.
Average contrasts over the day's distinct fitting-known tokens in each dimension.
For a token the account never used, population popularity cancels exactly:
the contrast equals `log((account_usable_dates + 5) / 5)` regardless of whether
one or many other accounts used it. Popularity can affect previously seen
tokens, which contribute positively only when their account incidence is below
the pooled incidence. The score is therefore often close to the fraction of
fitting-known tokens new to the account times that history-dependent ceiling.
It is a heuristic contrast, not an attack probability or ownership assertion.

Two fixed candidates: **R**, resource contrast; **J**, maximum of resource and
action contrast, requiring both dimensions available. Neither was selected or
tuned from the new switch results. Each required dimension needs at least five
usable fitting dates and at least one fitting-known token on the scoring day.
Globally unseen tokens are counted separately and excluded from the contrast;
a day containing only globally unseen resources therefore produces unavailable scores, never
an automatic zero/Low. Invalid supplied paths, required-path gaps or unknown
native actions also make a day unavailable. A login with no applicable path
does not itself imply lost logs.

Calibrate R and J separately on 1-4 August normal data at the linear 99th
percentile, strict `score > threshold`. At least six scorable calibration days
across three accounts are required. The fixed shrinkage strength is five dates;
there is no parameter search, threshold lowering or boundary change.
Also report the unchanged AE and the fixed AE OR J union with tri-state missing
logic: an available positive can trigger the union; false plus unavailable
remains unavailable. Measure the actual normal union rate.

## Evaluation scope and checks

All 5-9 August dates and three reciprocal switch cases were previously inspected.
This is development evidence only. Native events are reassigned after 5 August;
paths/actions remain those of the donor. Both the frozen ten-count and new
set-based projections are rebuilt. Earlier partitions must match exactly.
The original AE must reproduce 2/191 normal alerts and 0/25 switched-day alerts.
Save reference and calibration JSON before case scoring, reload the reference
and compare every calibration row's inference, then check reference/input hashes
again at completion. No data, fitted dictionaries or model files enter Git.

Report the original 191 normal and 25 switched account-days, each method's
scored/unavailable counts, matched common-subset AE results, three case-level
outcomes, and per-day resource coverage. Repeated normal controls in individual
case summaries do not increase the aggregate sample size. Missing actor activity
is not a true negative. Validation counts apply later thresholds retrospectively
and are descriptive, not prospective validation performance.

## Limits and interpretation

CLUE is a single storage service. Equal literal paths do not prove physical
object identity, resource ownership, access rights or that the recipient could
perform the donor's operations. These reciprocal projections are behaviour
substitutions, not verified feasible credential-compromise attacks. Existing
cases informed the feature research question; positive outcomes would still
need fresh, reserved evaluation. Negative outcomes must also be retained.

Daily-incidence estimates and smoothing are a design choice. The token contrast
has an account-history-dependent ceiling `log((usable_fit_dates + 5) / 5)`;
a pooled threshold can consequently be unreachable for some sparse accounts.
Fitting coverage gates alone do not establish a fair or calibrated per-account
alert rate. Entirely new resources can be important but are only coverage in
this candidate, so this scorer is not a general novelty detector. Ordinary
resource sharing or job changes can also produce alerts. Identical approved
and unapproved actions require external context to distinguish intent.

The earlier raw novel-path fraction had saturated normal q99=1. This experiment
uses a different, explicitly versioned contrast; it does not change that earlier
result or claim the fraction suddenly works. No useful live detector, replacement
AE or competition performance claim is authorized merely by this comparison.

## Actual development result

Both R and J calibrated to **1.2237754316221157** in their own contrast units.
This is exactly `log((12 + 5) / 5)`: the ceiling for 12 fitting dates. A
report-only replay of calibration inference confirms **three exact ties** at
this threshold, all on 12-date resource histories. The global calibration
range is not constant, so the existing `degenerate_calibration=false` flag
does not imply an absence of ties or score saturation.
They produced identical classifications in this experiment; adding the action
dimension did not add detections. AE retains raw MSE **0.7648530006408691**;
the numbers have different units and are not comparable risk percentages.

| Normal development data: 191 original account-days | Scored | Unavailable | Alerts |
|---|---:|---:|---:|
| Frozen AE | 191 | 0 | 2 |
| Resource contrast R | 126 | 65 | 0 |
| Joint contrast J | 126 | 65 | 0 |
| AE OR J | 126 | 65 | 2 |

On the common 126-day subset the AE has two alerts (1.59%); R and J have none.
The new rule is not demonstrated to have a lower false-alert rate: it excludes
65 original days and this is a small, correlated development window. Of those
65 unavailable days, 12 lack five usable fitting dates and 53 have no
fitting-known resources under the original status ordering. Within the latter
53, **12 have no resource activity and 41 have only globally unseen tokens**.
Within the 12 insufficient-history days, five have no resources, six have only
globally unseen tokens and one has fitting-known tokens. These are distinct
coverage situations, not all new-resource days. Common rows span 37 accounts; the original normal
window has 49 active identities from the frozen 55-account population.

| Switched development data: 25 original account-days | Scored | Unavailable | Alerts |
|---|---:|---:|---:|
| Frozen AE | 25 | 0 | 0 |
| Resource contrast R | 20 | 5 | 6 |
| Joint contrast J | 20 | 5 | 6 |
| AE OR J | 20 | 5 | 6 |

This is six flagged days across **two of three cases**, not general attack
recall. Five of 25 days are unavailable: **two have no resource activity and
three have only globally unseen resource tokens**. They must not all be described
as new-resource or new-namespace days. Among the 20 commonly scorable days AE flags zero and R/J
flag six; reporting 6/20 alone would hide the five unavailable days.

| Case | Original days | Common scored | R/J alerts |
|---|---:|---:|---:|
| switch-01 | 8 | 7 | 0 |
| switch-02 | 9 | 8 | 5 |
| switch-03 | 8 | 5 | 1 |

The six positives exceed the threshold by about 0.1112 (five days) or 0.0572
(one day), so these positives are not last-bit equality artifacts. However,
**31 of 49 resource-eligible accounts have a theoretical score ceiling at or
below this pooled threshold**. In exact arithmetic those accounts cannot cross
the strict resource rule, even when all observed fitting-known resources were
never seen under that account. A synthetic regression test exposes this
history-length dependence. This is a substantial design limitation, not a
reason to lower the threshold after seeing the cases.

All six positives are saturated ceiling days: all their fitting-known resources
were absent from the recipient's fitting history. Five have 14 usable fitting
dates, one has 13. Only 18 of 49 eligible fitting accounts can exceed the
threshold in exact arithmetic. If previously seen tokens contribute zero, an
account with 14 fitting dates needs more than about 91.7% of its fitting-known
resources to be new to that account; with 13 dates it needs more than about
95.5%. These fractions are conditional illustrations, not necessary conditions
for every possible day, since previously seen tokens can also contribute.
The observed six hits are effectively long-history accounts touching wholly
foreign sets of fitting-known resources, not graded evidence of compromise.

Normal calibration has 121/169 days scorable by R/J (38 accounts) and zero R/J
alerts. AE flags two of the original 169, one on the common 121. The tri-state
union has 122 decidable rows and two alerts: an AE-positive with unavailable J
is still a positive, while AE-negative plus unavailable J remains unknown.
Its common-subset alert rate is 1/121 (0.83%). These denominators are intentional
and are not a guaranteed future 1% rate. Retrospective validation yields one
R/J alert among 117 scorable rows out of 188; it was not used to tune anything.

Interpretation: resource identities contain information the count-only AE
discarded, and the fixed contrast recovered some development substitutions.
The limited coverage and history-dependent ceiling mean **this candidate is
not recommended for live activation**. Keep it as a reproducible comparison.
A future candidate needs a separately fixed treatment of history length and
entirely new resources, followed by normal-only calibration and fresh reserved
evaluation. Do not promote the six hits as proof of live multi-cloud detection.

All invariant checks passed: native counts matched, earlier partitions stayed
unchanged, frozen AE results reproduced, persisted-reference inference matched,
and input/reference hashes stayed unchanged. Private artifacts are in
`data/processed/clue-account-affinity-development-v1`, including reference,
calibration and development report. Report SHA256:
`966622ad25ce51b3081f4fc5778543d5ecb0195e6910907956b91462914b276c`.

## Reproduction

```powershell
$env:DATABASE_URL = 'sqlite-local'
python -m pytest scripts/tests/test_account_familiarity.py -q
python scripts/evaluate_account_familiarity.py --data FROZEN_FEATURE_JSON --bundle VERIFIED_AE_BUNDLE --prefix EXISTING_PREFIX --plan ORIGINAL_SWITCH_PLAN --out data/processed/NEW_PRIVATE_DIRECTORY
```

The CLI refuses existing output folders or unknown frozen bindings and loads
trusted weights only after those checks. All inputs are existing local files.
There are no downloads, provider calls, application-database writes, runtime
registration, deployment actions or model activation.

Local regression before the actual comparison: 328 passed, one optional PostgreSQL test skipped with
`DATABASE_URL=sqlite-local`. Synthetic tests cover resource changes at constant
counts, fitting-only immutable state, incidence deduplication, missing coverage,
unknown tokens/accounts, eligibility, JSON reload, quantile equality, report
denominators and preserved pre-switch history. Native parsing and AE inference
are deliberately stubbed in the pipeline-assembly test; its artificial results
are not the empirical development result.

After adding the history-ceiling regression test: **329 passed, one optional
PostgreSQL skip**. No scoring/reference code changed after the real run.
The user supplied Claude's manual six-file review on 28 October. It found no
correctness/leakage blocker and identified the cancellation, ceiling/tie,
coverage-interpretation and namespace-dependence issues discussed here. Codex
did not transfer source for that review. The report-only follow-up is defined
in `specs/W6-review-diagnostics.md`; original scores, thresholds and artifacts
remain frozen.

## Report-only follow-up to the manual review

The supplemental tool checks hashes against the original result before reading
the already inspected prefix. It replays calibration inference from the saved
reference because per-day calibration scores were not stored; the original
calibration-row digest, q99 and alert counts reproduce exactly. It does not fit,
recalibrate, modify decisions or overwrite original artifacts. Normal and
switched score diagnostics use the saved values.

| Threshold diagnostic, identical for R and J | Calibration | Normal development | Switched development |
|---|---:|---:|---:|
| Scored days | 121 | 126 | 20 |
| Exact ties | 3 | 0 | 0 |
| Within absolute 1e-12 of threshold | 3 | 0 | 0 |
| Strict alerts, unchanged | 0 | 0 | 6 |

The reporting tolerance never changes `>`. The six positives are not last-bit
artifacts, and no saved normal/switched development non-alert is within this
tolerance either. The exact calibration ties still warrant numerical caution
for any future implementation; the strict rule has not been made tolerant or
changed to >=.

To check dependence on donor-specific resources, inspect native hit-day paths
privately and emit only counts. Across the first five hit days, all 85-88
fitting-known resources per day are absent from the recipient's fitting history,
but **none is exclusive to the donor** among the 55 fitting accounts. On the
sixth day, just one of six distinct resources is fitting-known; that token is
donor-exclusive and entirely determines its resource contrast. The other five
resources are globally unseen and excluded from the score. The six days contain
143 distinct resource tokens in total; summing their daily token counts would
repeat many resources.

For the coarse first-nonempty-slash-component proxy, none of the fitting-known
resources on the first five hit days has a component exclusive to the donor.
The sixth day's one known resource does. Two of the first five days each also
contain one globally unseen resource with a donor-exclusive fitting component;
those unseen tokens do not contribute to the contrast. No raw paths, component
strings, token hashes or native identities are published by the tool.

Literal reuse under other accounts does not prove a shared physical resource,
and an administrator could also touch a personal folder. The first-component
proxy cannot rule out deeper user-specific namespaces. Therefore this check
neither establishes ownership nor dismisses the reviewer's namespace-triviality
concern. The single-known-token hit is especially weak evidence of robust daily
behaviour detection.

Supplement: private
`data/processed/clue-account-affinity-development-v1/review_diagnostics_v1.json`,
generated with `scripts/review_familiarity_diagnostics.py`. Frozen W6 source/input
hashes and native positive-day resource counts matched. Regression including
the reporting helpers: **337 passed, one optional PostgreSQL skip**. New tests
also demonstrate that different pooled token popularities give the same
contrast for never-used resources, and that counting near ties does not change
strict classifications.

## Next-experiment decision after review

Equal five-date histories would remove this particular ceiling disparity, but
the suggested raw unfamiliar-path fraction is bounded at one, and an earlier
novel-path diagnostic already had normal q99=1. A five-date reference might
increase novelty further; success must not be assumed. Implement/check any new
version on inspected development data first and freeze its method and go/no-go
rules before consuming a genuinely reserved later window. Do not inspect a
fresh window to discover/tune away another saturation problem.

No new v2 candidate was scored or fresh data downloaded for this review. A later
native-data reservation must start after the already inspected partial 10 August
capture and account for the frozen exporter's 32 MiB prefix cap. Any future
source-aware live method requires its own data, eligibility, calibration and
release gates; it cannot inherit a CLUE threshold or be declared validated from
scripted resource substitution alone.
