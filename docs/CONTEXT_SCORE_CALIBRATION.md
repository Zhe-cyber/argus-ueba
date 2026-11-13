# Context-score calibration: primary rejected

28 October 2026. Spec fixed in `be0ba6f`, implementation saved in `1819d79`
before new calibration scores. This is normal-only development calibration,
not a switch test, fresh evaluation, AE retraining or live activation.

## Fixed method

Load the unchanged W8 fitting reference: equal-day mean category distributions
from 13-26 July, at least five usable dates per account/view. Per-view score is
base2 Jensen-Shannon divergence from the account's own reference, including
unseen categories. No-resource, unknown-history and unresolved-coverage states
remain unscored, never zero/Low. No reference updates after fitting.

The primary candidate is **max(action mix, parent depth1)**, requiring both.
Depth 1 was chosen before calibration because deeper context already had normal
maxima in the exploratory validation. All three individual views are retained
as controls; a passing control never silently replaces a failed primary.
The max is a fixed heuristic over JS units, not a compromise probability.

Calibrate on 1-4 August normal data at linear q99 with strict `score > threshold`.
Minimum six scorable days across three accounts. Thresholds at or within 1e-12
of the upper bound 1 fail the near-ceiling operational gate. This gate does not
alter the strict decision rule or lower a threshold. Any other passing result
only permits a subsequent development comparison, never live activation.

## Actual normal-calibration result

| Candidate | Scored / 169 original days | Threshold | Strict alerts | Maximum-distance days | Gate |
|---|---:|---:|---:|---:|---|
| Action mix control | 169 | 0.8723298382 | 2 | 1 | Development comparison permitted |
| Parent depth1 control | 154 | 1.0 | 0 | 4 | No-go |
| Parent depth2 control | 154 | 1.0 | 0 | 10 | No-go |
| **Joint primary** | **154** | **1.0** | **0** | **4** | **No-go** |

Action scores cover 49 active accounts; context/primary scores cover 45. The 15
unavailable primary days comprise 10 no-resource and 5 insufficient-history days
in the component views. They are not normal predictions. The frozen fitting
population remains 55; eligible fitting references are 55 action and 49 context.

The action control's 2/169 alerts are 1.18% of scorable calibration days, not a
future false-positive guarantee. All three failed candidates have exact ties
at their ceiling: four for depth1/primary, ten for depth2. Their zero strict
alerts do not establish useful detection: a bounded score cannot exceed 1.
Any threshold below 1 would flag at least 4/154 (2.6%) for depth 1/primary and
10/154 (6.5%) for depth 2 on this calibration data. No threshold was changed.

**Primary rejected. Switch evaluation NOT RUN.** Do not report measured 0/25,
attack recall, held-out normal effectiveness or a newly validated detector.
The action control passes the mathematical calibration gate only; it has not
been substituted as primary, evaluated on attacks or activated live.

## What we learned and next decision

Normal-profile separation and a usable rare-alert tail are different properties.
The W8 context views often resembled their own account more than other accounts,
yet enough normal days have disjoint context to saturate q99. Do not select a
feature merely because its closed-set profile-separation percentage is large.
An increasing/unbounded transformation alone would not separate tied maxima.

Keep this failed primary and all controls. A separately fixed next experiment
could evaluate the action component's actual development sensitivity and
investigate the legitimate context shifts behind maxima; neither is already
demonstrated here. Source-specific live contexts need their own feature
semantics/history and evidence. A CLUE path-parent convention is not directly
an AWS bucket/object, GitHub repository or Cloudflare application model.

The laptop collection job is now independently accumulating raw source records
and begins controlled ordinary activity 29 October. It remains unverified for
live model scoring. Those records need coverage/receipt reconciliation and
the prospective fitting/validation/calibration/evaluation gates; a normal-only
offline calibration cannot replace that process.

## Provenance and reproduction

Verified original W8 report/reference/source, native prefix, manifest and frozen
feature-export hashes. A separate period projector preserves the frozen W8
exporter; synthetic parity tests and actual calibration counts, distinct paths,
actions and coverage match all 169 frozen rows. Immutable JSON reference reload
is exact; reference and original input hashes remain unchanged. All checks passed.

```powershell
$env:DATABASE_URL = 'sqlite-local'
python -m pytest scripts/tests/test_context_score_calibration.py -q
python scripts/calibrate_context_score.py --reference-directory EXISTING_W8_OUTPUT --dataset FROZEN_FEATURE_EXPORT --manifest FROZEN_MANIFEST --prefix EXISTING_PREFIX --out data/processed/NEW_PRIVATE_DIRECTORY
```

Private output: `data/processed/clue-context-score-calibration-v1`, containing
`normal_calibration.json` and `calibration_gate_report.json`. Original W8
reference is reused read-only, not overwritten. Report SHA256:
`19eb77cb68deb4f702e25823a7d8ef323f506a265282dcae859629f411882aa9`.

Local regression: **389 passed, one optional PostgreSQL skip**, forced
DATABASE_URL=sqlite-local. Tests cover strict JSON/probability/eligibility
contracts, immutable reload, unseen categories, fixed primary combination,
missing views, near-ceiling gates, no control fallback, chronological minima,
projector parity and input binding. No raw data/dictionaries committed, cloud
calls from this experiment, pilot-runtime changes, fresh data or AE/CERT/core
changes. The separately scheduled collection job continues with its own guard.
Independent review is not claimed; the user prefers manual review transfer.
