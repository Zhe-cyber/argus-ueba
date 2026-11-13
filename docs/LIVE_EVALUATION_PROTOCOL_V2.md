# Prospective daily workload pilot: final sign-off 15 November

Approved 28 October 2026 before ordinary workload collection. This supersedes
the dates and sparse cadence in V1, which remains available as history.
All dates/times are Asia/Kuala_Lumpur. Competition: 25-26 November.

## Purpose and scope

Six restricted AWS machine roles execute controlled toy-resource reads. These
are daily machine workloads, not six independent human users. Genuine owner
activity from AWS, Cloudflare Access and GitHub remains a separate provenance
stream. GitHub collection is public Events API activity, not organisation audit.
Cloudflare Access records authentication, not in-application behaviour.
This pilot cannot by itself establish real-human or multi-cloud detection accuracy.

## Frozen generator revision

`persona_profiles_v2.json` changes each role's weekday/weekend activity probability
to 1.0. Timing windows, operation/resource weights, action ranges, random seed,
toy fixtures, permissions and call limits remain unchanged from V1. This choice
supports coverage before the deadline; it was not selected using future scores.
Actions still vary deterministically by role/date and occur at actual provider
timestamps. No backfill or fabricated native logs. No generator changes after
ordinary collection starts without a separately labelled study revision.

The offline forecast is 292 reads over 29 October-13 November. Reserving five
SDK calls per read as separate invocations gives at most 1,465 calls including
the existing commissioning run; largest day 115. Limits remain 48/run, 128/day,
1,792/pilot. These are planned budgets, not observed coverage or cloud charges.
The original verified commissioning claim and its five-call reservation remain
in the same ledger; an audited scope migration changes only the profile binding.

## Calendar and locked decisions

| Dates | Purpose |
| --- | --- |
| 29 October | Warm-up; excluded from fitting/evaluation |
| 30 October-5 November | Fitting only; seven calendar dates |
| 6-7 November | Normal validation; no online model updates |
| 8-10 November | Normal-only calibration |
| 11 November | Reconcile and freeze artifacts, thresholds and scenario executor by 23:59; ordinary activity excluded from all study partitions |
| 12 November | Reserved unannounced controlled resource-change case |
| 13 November | Reserved matched analyst-approved legitimate-change control |
| 14 November | Arrival reconciliation only; no new scheduled actor actions |
| 15 November | Final sign-off; report go/no-go and limitations |

Collection and the local backend expire at 00:00 on 15 November (UTC 14 November
16:00). Laptop availability is expected 08:00-20:00 daily through 14 November;
the final receipt cutoff is 14 November 20:00 MY. Anything arriving later is
reported separately and cannot silently revise the frozen result. The task
expiry is an upper bound, not a promise that the laptop collects while asleep.

The method annex must be written by 5 November 23:59, before validation. It must
identify the feature contract, aggregation timezone, normal eligibility policy,
model/scorer, hyperparameters and artifact hashes, threshold rule, context fields,
coverage gates and reporting unit. Do not select among methods on held-out cases.
Review collection health on 1 and 3 November; preserve omissions rather than
replaying missed actions. Ordinary windowed actions finish before 19:00 MY.

## Eligibility and reporting

Retain V1 minimums: at least five active fitting days spanning seven calendar
dates, two active validation dates, at least two calibration dates per eligible
role, and at least 12 calibration account-days across four roles and three dates.
Each eligible day requires at least 90% of planned actions with distinct native
provider receipts, no unresolved attempted claims and reconciled collection.
Stricter model-specific history requirements take precedence. Calibration must
respect the predeclared experimental review-alert budget of at most 5%; a 99th
percentile estimate from so few correlated days does not establish a 1% false
positive rate. Do not reduce gates or reinterpret missing days as normal scores.

Freeze scenario targets persona-01/persona-02 and replace each target's first
planned GetObject on 12 and 13 November with the existing p06 fixture, retaining
time, operation and count. The offline schedule contains such reads on both
dates. The scenario executor still needs implementation, tests and a frozen
release before 11 November; this protocol does not claim those cases have run.
The approved-change label is analyst context, never a detector feature. The
matched cases may be behaviourally indistinguishable, which must be reported.

Report eligible/ineligible roles and days, planned/executed/native-verified
coverage, normal validation/calibration review rates, scenario review flags,
missing/late receipts, model compatibility and all negative results. No claim
of detecting malicious intent from these controlled cases alone. No automatic
response decisions. A usable pilot does not guarantee a useful detector.

If gates or freeze deadlines fail, sign off a working collection pipeline plus
frozen offline evidence. Live scores remain Unknown until a compatible model
passes its predeclared evaluation and an explicit activation decision is made.
CLUE experiments and frozen V1 generators/models/thresholds remain unchanged.
