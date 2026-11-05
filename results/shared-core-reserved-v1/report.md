# Shared-core reserved evaluation — 30 October 2026

**Decision: do not promote this candidate to general live compromise alerting.**
The five-feature population AE has weak ranking on account switches and mass access, and low recall at the frozen thresholds. The simple baseline ranks three scenario families better. No retraining or threshold/injection tuning was performed after the reserved results.
At the frozen 1% calibration budget the AE has higher recall than the baseline in all four scenarios, and at the 5% budget in three of four; the baseline's higher AUROC in three scenarios does not imply higher recall at those fixed cutoffs, and the contribution of tied score blocks to that difference has not been established.

Window: 11–24 August 2017 UTC. One fixed candidate, 55 fitting-selected pseudonymous accounts; 472 eligible normal account-days and 12 input-quality exclusions. All 55 have some test activity; unobserved idle days are not negatives.

Semi-synthetic evidence: publisher-described normal storage activity plus preregistered one-day native-event injections. Not real attack accuracy or live multi-cloud performance.

## Ranking metrics

| Scenario | Cases | AE AUROC | Baseline AUROC | AE AP | Baseline AP | Positive prevalence |
|---|---:|---:|---:|---:|---:|---:|
| 5× file-read injection | 373 | 0.554 | 0.605 | 0.489 | 0.514 | 44.1% |
| Night-time shift | 410 | 0.697 | 0.852 | 0.675 | 0.761 | 46.5% |
| Unfamiliar-action injection | 301 | 0.808 | 0.956 | 0.770 | 0.909 | 38.9% |
| Account-switch injection | 144 | 0.534 | 0.521 | 0.277 | 0.300 | 23.4% |

AP is average precision, not trapezoidal PR-AUC; it depends on the displayed class prevalence. Per-scenario figures use the same 472 normal days. No pooled accuracy headline is used.

## Frozen operating points

| Scenario | AE recall: 1% budget | Baseline: 1% | AE recall: 5% budget | Baseline: 5% |
|---|---:|---:|---:|---:|
| 5× file-read injection | 1/373 (0.3%) | 0/373 (0.0%) | 19/373 (5.1%) | 12/373 (3.2%) |
| Night-time shift | 6/410 (1.5%) | 0/410 (0.0%) | 65/410 (15.9%) | 12/410 (2.9%) |
| Unfamiliar-action injection | 49/301 (16.3%) | 0/301 (0.0%) | 115/301 (38.2%) | 15/301 (5.0%) |
| Account-switch injection | 2/144 (1.4%) | 0/144 (0.0%) | 5/144 (3.5%) | 9/144 (6.2%) |

At the nominal 1% normal-calibration budget both methods alert on **0/472 normal test days**. That is an observed count, not proof of zero future false alarms; it accompanies very low case recall.
At the nominal 5% calibration budget the AE alerts on **16/472 normal days (3.39%)**, baseline **13/472 (2.75%)**. These are achieved test rates, not thresholds chosen from the mixed test set.
Higher AUROC/AP need not imply higher recall at a particular fixed cutoff. Report both ranking and operating-point results. CSV includes exact thresholds and case tie counts.

## Coverage and controls

- Twelve observed normal account-days are unscorable due to required input quality; excluded cases are not true negatives.
- Switch design: 27 disjoint directed pairs, 27 targets, 27 donor-only accounts and one unpaired account. There are 144 scorable switches; 81 target-days lack an active/scorable donor and nine target-days have an unscorable original. Donor-only days and the unpaired account remain in normal-day accounting.
- One switch has identical five-feature values and is retained as a positive case. Normal originals alone update later-day history.
- Other exclusions: mass access 99 days without reads plus 12 unscorable originals; off-hours 62 already-night days plus 12 unscorable; unfamiliar action 122 already-known permission-kind days, 49 without a resource template and 12 unscorable.
- Account-days and paired counterfactuals are dependent. No independent-binomial confidence claim or broad deployment generalisation is made.

## Validation and provenance

37 pre-release tests passed; the full reader/history/generator/scoring/metrics rehearsal on inspected 5–9 August passed with exact prefix/full-ZIP feature parity. Source-only Claude Code reviews were completed; code binding concerns were checked against actual guards and tamper tests.
A pre-test numerical supplement aligned calibration with canonical CPU float32 single-row inference: same 167 normal rows, same higher quantiles and strict-greater rule. AE 1% cutoff changed by one float32 step (1.1920928955078125e-07); original weights, scaler, manifest and thresholds remain preserved. This was completed before test access, not fitted to attacks.

Frozen evaluator release SHA256: f3ee424db261d07428ddf5153ec9682ae3c1b54f535232d4a32d949d95165d0c.
Reduced evaluation artifact SHA256: f62ffa1c470e6b150d0865ad5b49b1888bfa613626badbc34a709633c16716b3.
Completed native-access receipt is stored privately beside evaluation.json. The test window is now consumed and cannot be reused as an untouched test for later model tuning. A first 25-August boundary row was decoded for closure; do not call that date wholly uninspected.

Candidate: shared_behavior_core_v1, AE 5-16-8-3-8-16-5, 532 fitting / 183 validation / 167 normal-calibration days. Exact source/data/model bindings remain in the private training preregistration and evaluator release. No live activation or cloud-resource change.

## Next planned step

Complete provider-level applicability/sign-off with this negative benchmark finding retained. Current live inputs remain cold-start and broad AWS resource semantics are incomplete; this experiment does not justify enabling live High/Medium/Low from this candidate. Keep the working collection, source-scoped identities, approved cross-provider timeline and existing AWS study intact. Any changed detector needs an explicit new protocol and a genuinely fresh test, not retuning on these outcomes.

Source: [CLUE-LDS, Landauer et al.](https://zenodo.org/records/7119953), CC BY 4.0. This is cloud-storage activity, not a real linked AWS/GitHub/Cloudflare attack dataset.
