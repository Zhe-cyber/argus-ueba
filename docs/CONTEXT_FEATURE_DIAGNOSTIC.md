# Action and resource-context diagnostic

28 October 2026. Exploratory normal-behaviour separation only. Spec fixed in
`d418ed7`, implementation saved in `9cd4224` before results. No detector,
threshold, peer-group system, AE retraining or live scoring was implemented.

## Why and what was compared

Literal path novelty saturated normal calibration even with equal histories.
This checks whether coarser resource context and action proportions preserve
account-specific patterns without depending on changing leaf names.

Use the frozen 55 CLUE accounts: fit on 13-26 July (605 account-days), compare
later normal validation on 27-31 July (188 account-days from 49 active accounts).
All these data are already inspected development data. No calibration, switch
case or fresh-window scores enter this diagnostic.

Three fixed views:

- Action mix: proportions of exact native action types by event count.
- Parent depth 1: distribution of the first literal parent component, weighted
  by distinct paths that day.
- Parent depth 2: distribution of the first two literal parent components,
  weighted by distinct paths that day.

The parent proxy drops the final nonempty slash-delimited component and uses
one root bucket if no parent remains. This is a string convention, not verified
file/directory semantics. Case, encoding and literal `..` are not resolved.
Actor identity is never added to a category. No path activity is unavailable
for context, not a fabricated root observation. Category tokens are hashed and
source-scoped; native strings are not published.

Each eligible account reference averages its fitting daily distributions with
equal day weights, requiring at least five usable dates. Daily volume therefore
does not choose the reference weighting. References never adapt after fitting.
Compare a normal validation day's distribution using base-2 Jensen-Shannon
divergence, including unseen categories. Calculate its own-reference distance,
median distance to other eligible accounts, and whether its own reference is
uniquely closest. Ties within 1e-12 count as ties, never unique identification.
The global-category coverage flag uses all fitting accounts, including sparse
ones, and never drops observations from a distance calculation.

## Results: normal validation, not detection accuracy

| View | Comparable days / 188 | Own reference closer than median other | Own reference uniquely closest |
|---|---:|---:|---:|
| Action mix | 188 | 158/188 (84.0%) | 25/188 (13.3%) |
| Parent depth 1 | 158 | 144/158 (91.1%) | 65/158 (41.1%) |
| Parent depth 2 | 158 | 152/158 (96.2%) | 91/158 (57.6%) |

Action references cover all 55 fitting accounts; context references cover 49.
Comparable validation accounts are 49 for actions, 43 for context. Context
exclusions are 28 no-resource days and two insufficient-history days. They are
not normal/Low predictions.

For action mix, 30 days are farther from their own reference than the median
other account and none ties the median. For depth 1 the split is 144 closer,
zero tied, 14 farther. Depth 2 is 152 closer, six tied, zero farther.
Own-reference nearest ties occur on 7, 4 and 6 days respectively; these are not
included in the uniquely-closest column. An account can resemble a group of
other accounts: closeness to its own profile does not imply reliable identity
classification, and neither metric is attack recall.

Equal-account averages of each account's own-closer fraction are 82.1%, 91.6%
and 95.3%, respectively. These differ from day-weighted fractions because some
accounts have fewer active validation days. No confidence interval or claim
of independent samples is made.

Median own distances are approximately 0.0473, 0.2325 and 0.5050. The larger
depth-2 own distance matters: **six comparable normal days have no category
overlap with their own reference and reach maximum JS divergence 1**. Any
strict threshold below 1 would flag at least those six validation days (3.8%).
This is a development warning about possible saturation; no alert threshold
has been calibrated or selected. Actions and depth 1 have no distance-1 days
in this validation window, but that is not a future false-alert guarantee.

## Identity/namespace caveat

An aggregate exact native-uid check finds matches in the first two literal
parent components on 3 of 292,477 fitting account-day path observations, across
three account-days. Validation has zero matches among 111,518 such
observations. The denominator sums distinct paths within account-days and can
repeat a path across days; it is not a count of globally unique resources.

This narrow check does not exclude encoded user identifiers, personal folder
names or other namespace signatures. Coarse context can still reflect a
dataset's directory layout rather than portable behaviour. Literal equality
also does not prove physical resource identity, ownership, permissions or that
a projected recipient could perform a donor's operations. Do not translate the
table into live AWS/Cloudflare/GitHub effectiveness or a deployed peer baseline.

## Decision and reproducibility

The views show enough normal-account structure to justify a separately fixed
scoring comparison. Keep all outcomes, including lower unique-nearest rates and
depth-2 saturation warnings. Before any next calibration or switch comparison,
fix its score, combination, eligibility, budget and gates. Do not select the
deepest context solely because its own-closer percentage is largest. No model
winner, production detector, new attack result or fresh validation is selected
from this exploratory comparison.

```powershell
$env:DATABASE_URL = 'sqlite-local'
python -m pytest scripts/tests/test_context_feature_diagnostic.py -q
python scripts/run_context_feature_diagnostic.py --original-directory EXISTING_W6_OUTPUT --prefix EXISTING_PREFIX --manifest FROZEN_MANIFEST --out data/processed/NEW_PRIVATE_DIRECTORY
```

The CLI verifies original input/source hashes, native fitting counts and both
partition sizes, persists the reference and checks its digest remains unchanged.
All invariant checks passed. No original artifacts, models, normalizers or live
data were changed. No provider calls, downloads or source transfers to Claude.
The user prefers manual review requests; independent review is not claimed.

Private artifacts: `data/processed/clue-context-feature-diagnostic-v1/reference.json`
and `diagnostic_report.json`. Report SHA256:
`3b5806c902c8c51802c352e4426426c84b5f451cda47785890b969c2cb3714ca`.

Regression: **361 passed, one optional PostgreSQL skip**, with
`DATABASE_URL=sqlite-local`. Tests cover JS mathematics, unseen categories,
filename invariance, daily weighting, immutable state, later-only comparison,
ties/coverage, native projection and input-binding rejection.
