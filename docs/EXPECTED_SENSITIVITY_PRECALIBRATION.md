# Expected sensitivity: recorded before calibration

Recorded 29 October 2026. Prediction only: no real fitting/validation scores, calibration data, test outcomes or qualifying live model exist yet. This document does not predict a guaranteed hit or miss, and it does not change the scenario.

## Exact effect on the primary score

For frozen account probabilities p, replacing ONE event at resource a with one event at p06 in an n-event day changes the entropy-centered mean score by exactly:

    delta = ln(p(a) / p(p06)) / n

The entropy term cancels. The change is positive only if p06 is less probable than the resource replaced. An unusual resource can be diluted by averaging, and legitimate low-probability resource combinations can also give high normal-day scores. The future threshold is still unknown; it depends on normal-only calibration. The account distribution shrinks toward the other five roles, so p06 probability depends on observed fitting counts and peer activity, not just role identity.

Under the frozen generator p06 has zero ordinary-generation weight for targets 01/02. With no p06 observations in eligible normal fitting, its mass is 5*p_peer(p06)/(N_u+5). This is prior mass but it is not necessarily negligible. Compute actual N_u and peer probabilities from fitting only.

Claude's dilution concern is reasonable, but the numeric example needs correction: role-01 allows 1–4 actions/day and role-02 allows 2–5. A 20-action day is outside the contract. The complete deterministic fitting schedule plans 15 events for role-01 (daily 3,1,3,1,2,2,3) and 25 for role-02 (2,3,5,2,4,4,5), not about 50 each. These are forecasts, NOT verified native coverage. Missing/unusable days can reduce the usable sample.

## AE comparator prediction

Replacing a read keeps event count and operation counts fixed. Under matched IP/timing context, IP diversity and off-hours counts are also fixed. However, unique_resources can change: if the old resource still appears elsewhere that day and p06 did not appear, diversity increases by one. If the replaced event was its old resource's sole occurrence, diversity is unchanged.

The targets do not ordinarily access the confidential toy bucket, so that feature stays zero. Thus some substitutions can be numerically invisible to the AE and some can alter the resource-diversity count. For identical input vectors, a fixed AE necessarily produces the same error. For a changed diversity count, the sign/magnitude of the error change and threshold crossing are unknown. Do not claim it will almost certainly miss every case.

## Prospective development calculation

Run on 6–7 November MY, before 8 November, with the existing read-only daily export. Use fitting rows to build references; use available CLOSED fitting/validation days only to describe score ranges. At that point 7 November validation is not closed before 8 November: explicitly report that limitation rather than treating a partial day as complete.

For each development account-day of targets 01/02 with a planned GetObject, use its first planned read's original resource and compute the one-read p06 counterfactual delta. Keep the rest of the histogram unchanged. Report before/after scores, exact deltas, n, fitting sample counts and normal development range. These are hypothetical modifications of development days, not the reserved November cases or an attack evaluation.

Do not estimate a calibrated detection rate, choose thresholds from modified days, change scenario strength, choose a different model or revise eligibility to obtain a hit. If the modified development scores lie within normal development spread, predict limited sensitivity; if outside, describe encouraging separation without promising the unseen calibration threshold will be crossed. Sparse/constant data may leave the prediction inconclusive.

Current result status: pending actual eligible fitting history. Fitting starts 30 October; no real-data sensitivity result is claimed on 29 October.

## Exact reserved-slot schedules — known before outcomes

| Planned local date | Target | Whole-day events | Replaced resource | Planned diversity delta |
| --- | --- | --- | --- | --- |
| 12 November | persona-01 | 3 | p01 to p06 | +1 |
| 12 November | persona-02 | 5 | p02 to p06 | +1 |
| 13 November | persona-01 | 3 | p01 to p06 | +1 |
| 13 November | persona-02 | 2 | p02 to p06 | +1 |

These are frozen-generator forecasts, not native outcomes. The diagnostic now emits all four slots before references exist (numerical deltas remain null), and fills their exact predicted deltas from FITTING references only once eligible history is available. It reads no calibration or case logs.

Each forecast changes unique_resources by one if the full schedule occurs and other context matches; therefore all four can change the AE input, although error/threshold effects remain unknown. Persona-02's approved-control delta is 2.5 times its unannounced delta because the event denominator is two versus five and the original resource is p02 in both. The control matches the kind of resource change, not an identical whole-day vector or intensity. Do not interpret unequal flags as learning intent, or alter counts to make the comparison easier.
