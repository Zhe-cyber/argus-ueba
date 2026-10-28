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
This favours tokens more familiar to the population than to the current account.
It is a heuristic contrast, not an attack probability or ownership assertion.

Two fixed candidates: **R**, resource contrast; **J**, maximum of resource and
action contrast, requiring both dimensions available. Neither was selected or
tuned from the new switch results. Each required dimension needs at least five
usable fitting dates and at least one fitting-known token on the scoring day.
Globally unseen tokens are counted separately and excluded from the contrast;
entirely unfamiliar namespaces therefore produce unavailable scores, never
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
fitting-known resources. Common rows span 37 accounts; the original normal
window has 49 active identities from the frozen 55-account population.

| Switched development data: 25 original account-days | Scored | Unavailable | Alerts |
|---|---:|---:|---:|
| Frozen AE | 25 | 0 | 0 |
| Resource contrast R | 20 | 5 | 6 |
| Joint contrast J | 20 | 5 | 6 |
| AE OR J | 20 | 5 | 6 |

This is six flagged days across **two of three cases**, not general attack
recall. Five of 25 days are unavailable because none of their paths are in the
fitting vocabulary. Among the 20 commonly scorable days AE flags zero and R/J
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
Independent Claude review has not run: the user will send the six-file review
request manually. No source was transferred by Codex for that review.
