# Shared-core reserved evaluation protocol

Status: method definitions fixed for the first isolated training preregistration,
30 October 2026. Separate reserved-evaluator release pending. No reserved test
inspection or live activation. Archive checksum verified; no extraction.
Companion: specs/W23-shared-core-contract.md.

## Prospective reservation and download

Fixed reserved test: 11–24 August 2017 inclusive, UTC, after the inspected partial
10 August data. No moving dates for better performance, eligibility or volume.
Incomplete days or insufficient samples become limitations/no-go.
No reserved records, aggregates, scores or eligibility inspection until the
extractor, model, thresholds and generators are frozen. Download checks may
verify size, checksum and archive member names without examining test records.

Download approved by handover v2; transfer initiated separately after the development audit:
- Filename: clue.zip.
- URL: https://zenodo.org/records/7119953/files/clue.zip?download=1
- Published size: 635.1 MB compressed, approximately 14.5 GB expanded.
- Dedicated private directory: data/live/public/clue-shared-core-v1/.
- Record actual bytes/SHA256 and verify official archive checksum.
- New versioned bounded streaming reader; do not modify frozen prefix limits.
- Stream the archive; do not unpack the 14.5 GB member. Keep private files outside OneDrive.

Existing fitting-selected cohort: 55 named pseudonyms; no test-based selection.
Warm-up 7–12 July; fitting 13–26 July; validation 27–31 July; normal calibration
1–4 August. Inspected 5–9 August remains development only. All inclusive UTC.
Re-extract native events; do not reuse CLUE10 aggregate columns as new inputs.
Prequential history updates from original prior days, including 10 August and
earlier test days, under the companion contract. The reserved evaluator alone
processes that later history after release; no pre-release aggregate inspection.

## Fixed native-event injections

Use eligible observed target-days. Select days and donors deterministically with
SHA256 ranks using seed 42, account, date and scenario, never model scores.
Keep originals and modifications paired. Offline copies only, no cloud actions.

1. Mass-access: append four copies of each file_accessed event, yielding five
   times those reads. Distinct synthetic IDs, same-day times. Access-volume test,
   not observed exfiltration.
2. Off-hours: remap events deterministically, preserving order, into 00:00–05:59
   UTC on the same date. Already entirely off-hours days are reported as zero
   change/ineligible, not successful injections.
   The shared-core timing feature uses time of day only, on weekdays and weekends
   alike (option A, selected 30 October 2026). This tests night-time displacement,
   not weekend activity. It may still overlap genuine normal night-time activity;
   that overlap is a legitimate detection limitation, not a reason to retune.
3. Unfamiliar action: add five copied resource-bearing events with action
   permission_changed, only if absent from target prior-day history. Same-day times,
   synthetic IDs. Tests novelty plus volume, not actual privilege escalation.
4. Account switch: sort fitting-selected identities by SHA256 of seed 42, scenario
   and pseudonym using canonical JSON encoding; adjacent identities form disjoint
   pairs. Fixed hash order determines target and donor. Replace a target day with
   the donor's same-date events, reassigned to target, using target history.
   No identity in multiple pairs. Separate generator, not claimed equivalent to
   the previous 0/25 experiment. Hash selection is reproducible, not evidence of
   representative real-world takeover. No similar-donor secondary experiment is
   added; keep the primary comparison small and fixed.

Exact ranking implementation, synthetic IDs, target fields and safety caps are fixed in
SHARED_CORE_RESOURCE_RULES.md and shared_core_scenarios.py. No intensity tuning
after evaluation. Report generated, ineligible, zero-change, unscorable and scored
counts per scenario. Injected events never enter history or calibration.
Five-times reads and five added actions are fixed scenario strengths chosen
before results, not established 'moderate' attacks. No later sensitivity sweep.

## Simple comparator

Same rows, five inputs, transformations and splits as AE. Using the fitting-only
standardized inputs from the companion contract, baseline score = maximum of 0
and the five standardized feature values. For zero fitting variance use scale 1,
matching StandardScaler. No additional novelty weight, hyperparameter selection
or scenario-specific logic. This one-sided max-deviation baseline can see timing,
resources, actions, volume and novelty; it does not model feature interactions.
Its own normal-calibration thresholds. A simpler detector matching AE is valid.

## Thresholds and metrics

Primary nominal normal alert budget 1%; secondary 5%. For each detector use the
higher empirical normal-calibration quantile at 1-budget. Alert strictly above
threshold. Report ties and achieved calibration alert rate; future rates are not
guaranteed. Require at least 100 eligible normal calibration account-days for
primary threshold reporting; otherwise insufficient threshold evidence.
Never flag a top percentage selected from the mixed test population.

Per scenario compare injected cases with all untouched eligible normal test days:
Headline AUROC and average precision (explicit AUPRC convention); secondary recall at frozen thresholds,
normal alert fraction, prevalence and denominators. Primary table is per scenario;
pooled metrics are secondary and depend on injection prevalence. Exclusions are
not true negatives. Report paired score changes and account-level summaries.
Rows and variants are dependent: no independent-binomial confidence claims.
With roughly 150 calibration days, a 1% tail depends on only a few extreme
observations. Report sample size and resolution; do not imply a precise 1% rate.

Label: semi-synthetic, real recorded normal behaviour with injected deviations.
Not real attack accuracy or numerical superiority over CERT on a different task.

## Live and delivery

Per provider: valid/invalid days, eligibility, missingness, constant features,
transformed values outside fitting ranges, raw score distribution and coverage.
Compatibility diagnostics are not live transfer accuracy. Distinguish extractor
compatibility, model-input compatibility and readiness for review priorities.
A valid score alone does not establish defensible priorities.
Insufficient live calibration means experimental raw score with coverage or
Unknown, not fabricated High/Medium/Low. Shadow activation requires explicit
user release; never feeds the frozen AWS study.

Minimum timeline/scoring screen before 15 November; reported results frozen by
15 November. Preserve fixed AWS dates. No new dataset/persona/service expansion.

## Remaining release gates

Training data, method/source hashes and fixed hyperparameters are recorded before
one candidate fit. Data-producing source changes require re-extraction. A training
preregistration does not authorise reserved data access. The later evaluator must
implement the fixed scenarios and metrics, verify all candidate/protocol hashes,
pass isolation/parity tests, and record its immutable release before opening the
11–24 August window. User commits reviewed source; no automatic push or deployment.

Native resource/action tables, history boundaries, fixed scenario ranking, caps,
transform precision and exact AE settings: SHARED_CORE_RESOURCE_RULES.md. The
18 core tests and five training guard/parity tests establish engineering behavior,
not detection performance. No architecture or injection tuning after candidate
results. No claim of full test release or live transfer validation at this stage.
