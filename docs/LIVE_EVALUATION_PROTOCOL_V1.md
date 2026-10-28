# Live pilot evaluation protocol v1.1

Registered study design: 28 October 2026, before the reserved evaluation period.
Timezone: Asia/Kuala_Lumpur (UTC+8). This document fixes collection scope,
chronological splits, exclusions, scenarios, coverage gates and reporting.
**The detector specification is not yet frozen or implemented.** The method
annex described below must be committed before validation; without it, scoring
and effectiveness claims are a no-go. This is a controlled case study, not an
enterprise effectiveness trial or a preregistered successful result.

Prospective revision on 28 October: v1.1 adds operational checkpoints, explicit
late-start/idle-coverage rules and calibration-review restrictions following an
offline review. The initial v1 remains in commit `353082c`. No data window,
generator, scenario, detector choice or eligibility threshold changed in v1.1.

## 1. Questions and limits

1. Does restricted synthetic activity produce native provider evidence that
   survives collection, normalisation, deduplication and account attribution?
2. Given sufficient history, does an account-conditioned score respond to a
   predeclared resource-pattern change, compared with a population-only score?
3. How many ordinary and explicitly legitimate-change account-days also alert,
   and how much of the intended activity was actually observed?

Three-source integration is an engineering question. A six-role AWS experiment
does not establish multi-cloud compromise detection. Cloudflare and GitHub
provide separate genuine activity/coverage observations; this protocol does
not generate bot accounts there or invent cross-provider identity links.

## 2. Frozen scope and provenance

- Controlled actors: existing `persona-01` through `persona-06`, all machine
  roles, in the existing Argus AWS toy lab. Seven synthetic buckets, fixed
  fixture, existing read-only permissions and CloudTrail selectors. No new
  accounts, permissions, external targets, writes, IP spoofing or fabricated
  login/geo events. Existing runner request ceilings continue to apply.
- Generator: shipped `scripts/persona_profiles_v1.json`, SHA-256
  `98bf9d641823d7764e510f3ff944c365f109ca9941349bf3f51788f92a74566b`.
  Its timing, idle-day, resource and volume variation is illustrative. It does
  not yet model realistic sessions or independent human behaviour. Keep this
  version fixed; do not tune generation to improve detection. Any replacement
  requires a prospectively versioned protocol, with results kept separate and
  ledger budgets/claims preserved.
- Genuine activity: the owner's AWS activity, real Cloudflare Access
  authentication and GitHub repository Events API activity. Keep it separate
  from lab traffic. Do not treat it as verified normal/attack-labelled data or
  claim complete app activity from authentication/repository feeds.
- Setup, collection, readiness and commissioning traffic is excluded from
  normal model datasets. The commissioning probe verified on 28 October is
  explicitly excluded by ledger/request-ID correlation, not by rewriting logs.
- Native events retain UTC timestamps. Derive Malaysia calendar-day buckets
  in this new live contract; do not change frozen CLUE UTC/date contracts.
- Account unit: `(source, source_account_id, verified principal/role)`.
  Verify AWS role attribution using native identity metadata and the lab
  registry/receipts; don't merge by display name or infer a person. No approved
  cross-provider person mapping exists under this protocol.

Existing events through registration and all commissioning diagnostics are
development/engineering observations. They cannot become an untouched test by
renaming a split. Keep plans, attempts, API receipts and native observations as
distinct records. Generator labels, persona narratives, scenario flags and
analyst approvals never enter detector features.

## 3. Chronological windows and freeze gates

All intervals below are local dates, inclusive; store exact UTC boundaries in
the dataset manifest. Late arrivals are attributed by provider event time.

| Dates in 2026 | Purpose | Permitted use |
|---|---|---|
| 28 October | Commissioning, coverage, development | Inspect freely; exclude from fit/calibration/test |
| 29 October–8 November | Normal-design fitting/development | Fit preprocessing, pooled/per-account statistics or candidate weights; document unreviewed/contaminated days |
| 9–11 November | Normal validation | Apply the registered method/selection rule; no scenario-based tuning |
| 12–16 November | Separate normal calibration | Choose thresholds by the predeclared normal-only rule |
| 17 November | Arrival/reconciliation buffer and freeze | Close calibration by 23:59; hash inputs, method, weights, preprocessing, thresholds and eligibility |
| 18–21 November | Reserved normal + controlled-change evaluation | No tuning, model updates or threshold changes; collect all six roles, including quiet/missed cases |
| 22 November | Final arrival/reconciliation buffer | Close test observations by 23:59; later arrivals reported as late/missing |
| 23–24 November | Reporting and demonstration | Publish all registered outcomes and limits; rehearse competition demo |

Do not inspect reserved test scores or use future native records to revise the
method before freeze. Reviewing delivery health/counts for coverage is allowed;
record such access. Any exposure that shapes a decision makes the affected
window development data; it must not silently remain 'untouched'. Scheduled
plans are known by construction: freezing does not remove generator circularity.

**15 November, 18:00:** provisional go/no-go review of fitting/validation
coverage, method implementation and calibration progress. It is not the final
calibration decision. **18 November, 00:00:** final gate, using only earlier
data. If requirements fail, keep live scoring Unknown and report pipeline
evidence plus whatever frozen offline evaluations actually exist. Do not slide
dates, lower eligibility, or promise a positive CLUE personal-baseline result.

## 4. Coverage, exclusions and minimum operational eligibility

These are minimum operational gates, not proof of statistical sufficiency.
Always publish exclusions and denominators; report the frozen six-role
population even when some roles are ineligible.

- A lab active day is usable only if all successful API receipts match unique
  native events, no attempt is unresolved, and at least 90% of that day's
  planned actions were executed and provider-verified. Report both execution
  coverage (`verified/planned`) and receipt coverage (`verified/successful API
  receipts`). Missing or ambiguous receipts fail the day; do not count them as
  normal inactivity. A partial commissioning day is never usable normal data.
- Fitting eligibility: at least five usable **active** fitting dates per role,
  spanning at least seven calendar dates. An earlier first active day may serve
  as warm-up only if the method annex requires it; it does not count toward the
  five fitting days in that case. At least two usable validation dates per role.
- Calibration eligibility: at least two usable active calibration dates per
  eligible role and at least 12 account-days across at least four eligible
  roles and at least three of the five calibration dates. If the actual detector needs more
  data, its method annex must impose the stricter requirement. These small
  counts do not validate a 1% false-positive-rate claim or neural-model quality.
- A planned idle day needs complete runner/invoker coverage and an explicit
  absence-of-actions record before being called confirmed lab idle. Absent logs
  alone mean unknown coverage. Idle/zero-event days are not silently inserted as
  feature rows or counted as true negatives.
- Preserve invoker timestamps, failures, queue age/backlog, collector run
  outcomes, feed truncation and late arrivals. Bounded Events/Access queries
  cannot establish complete coverage by themselves. Genuine human streams are
  descriptive until source-specific completeness and baseline gates exist.
- Fit, validation and calibration contain only provider-verified ordinary lab
  actions. Exclude commissioning, readiness, setup, collector operations,
  unresolved attempts and registered test substitutions. Keep the excluded
  native records for audit; exclusion is dataset selection, not log deletion.

## 5. Required method annex: deadline 8 November, 23:59

Commit a versioned annex and its implementation hash before normal validation.
It must fix all of the following; there is no permission to choose these after
seeing reserved scores:

1. Exact live feature names, units, domains, timezone, extraction code, missing
   value handling, history lengths, warm-up and per-source compatibility.
2. The account-conditioned method, population-only comparator, any volume-only
   comparator and whether the existing AE is included. CLUE weights/scalers/
   thresholds are not compatible by default. No per-role neural model on five
   days; justify any neural fitting sample requirement separately.
3. Fitting and validation selection rules, seeds, hyperparameters and any
   shrinkage/fallback for sparse accounts. Prefer selecting these on already
   inspected CLUE development data; preserve the domain-mismatch limitation.
   Primary evaluation uses frozen fitting reference statistics/vocabularies;
   disable online baseline/model updates through validation, calibration and
   test, so an earlier test substitution cannot teach the later control.
4. Threshold computation, quantile interpolation, equality convention and
   sparse-calibration behaviour. Predeclare a normal-only calibration alert
   budget of at most 5% per active account-day for an experimental review flag;
   this is an empirical target, not a probability guarantee. A stricter 1%
   target must use an explicit finite-sample rule and disclose tail resolution.
   Do not reuse CLUE's 0.764853 threshold or create risk tiers to colour a demo.
5. Whether scores combine: if so, freeze the rule before test and report the
   OR-union **normal-only** alert fraction as well as component results. Never
   pool scenario/ordinary days into an advertised false-alert rate.
6. Eligibility, failure handling, the primary outcome and scoring-release
   criteria. No automatic enforcement/response; alerts are review suggestions.

The study design is registered now; **the detector is not preregistered merely
because this checklist exists**. A missing/late annex or incompatible model is
a no-go for the planned scoring evaluation. Version any amendment before its
affected future data, state the reason, and retain the original protocol.

## 6. Predeclared controlled resource-change cases

Primary targets are `persona-01` and `persona-02`; other roles retain their ordinary profiles.
For each target in each slot below, replace only its first planned `GetObject` of the
day with a read of the same `fixture.txt` in toy bucket `p06`. Keep role,
operation, planned time, event count and all other actions unchanged. Never add
an extra event, advance a timestamp, force activity onto an idle day, or touch
anything outside the current read allowlist. The scenario executor is not yet
implemented; it must be separately tested, frozen and receipt-audited before use.

| Local date | Context label kept outside detector inputs |
|---|---|
| 18 November | Unannounced lab behaviour change |
| 19 November | Analyst-approved legitimate-change control |

20–21 November are ordinary-profile test days for all roles. Both selected
targets have a planned eligible read on 18 and 19 November under the frozen
generator. This was checked before any corresponding native activity/results,
not selected by anomaly scores. A delivery failure can still make a slot unavailable.

If a slot has no planned eligible read, the role is ineligible, the schedule is
missed or the receipt is missing, report the slot unavailable. Do not substitute
another role/day after seeing results. Private approval/context records are
created prospectively; they do not grant additional cloud permissions.

Bucket p06 is outside both targets' v1 generation distributions. Consequently
this is deliberately a simple controlled sensitivity probe and can reveal
script learning; it is not human-behaviour or real compromise evidence. The
matched legitimate change presents the same kind of novelty. A detector cannot
infer malicious intent from observationally identical actions. Report its
legitimate-change alerts as investigation burden, not expect magic separation.
The existing persona-03 ordinary archive reads and persona-05 higher ordinary
volume remain visible controls. No sensitive-data exfiltration is simulated.

The primary unit is the target account-day. Also report event/receipt counts,
but don't inflate the number of independent scenarios by counting each API call.
At most two changed account-days and two matched-control account-days, occurring
on two calendar dates, support a small case study;
report exact n and every miss/unavailable slot. More pairs/scenarios require a
prospective new protocol, not a post-hoc expansion of successful cases.

## 7. Required report and claim boundaries

Publish: all six roles and eligibility; counts and exclusions by source/date/
purpose; intended, attempted, successful and provider-verified actions; ordinary
test alert numerator/denominator; every change/control slot's score, threshold,
alert/miss/unavailable status; population/account-conditioned comparisons; and
combined normal-only alerts if used. Report ordinary test days separately from
calibration, target-change days and legitimate-change controls.

No random row splits, attack-labelled threshold tuning, hidden scenario retries,
missing-day true negatives, claims of independent users, or conversion of High
into 'compromised'. Correlated roles/days make simple binomial intervals
descriptive only. Keep live scores Unknown until the separately registered
release gates pass. An honest fallback is the working live collection pipeline,
coverage/provenance history and the existing frozen CLUE normal-holdout/replay
results, including known negative findings where relevant. A new personal-
baseline result is a deliverable to evaluate, not a result already achieved.

No scheduler, infrastructure, credentials, detector or model activation is
created by committing this protocol. The noon AWS billing reminder and its
unfinished alarm remain a separate task.

## 8. Reservation feasibility before scheduling

The daily SDK-call reservation ceiling is 128; the existing 48/run and 1,792
pilot-wide ceilings remain. This corrects an operational limit before ordinary
history starts, without changing the frozen generator, available S3 operations,
resources or per-role/day action cap. The old 64/day limit would exhaust on
15 of the 28 generated days in a five-minute-invocation dry run.

For 28 October–24 November the fixed profile/seed generates 326 planned actions,
at most 21/day. The conservative bound with every action in its own five-call
invocation, plus the five-call commissioning probe, is 1,635/pilot and 110/day,
below the retained total and new daily ceilings. This is feasibility arithmetic,
not evidence of completed execution, coverage or provider cost. Failures,
redirects and extra readiness checks can consume headroom and must be recorded;
no limit is silently bypassed. Scheduler design must preserve the canonical
ledger and stop at the protocol's collection end, with no automatic retries of
unknown attempts. Cloud-hosted credentials/state remain implementation work.

The corrected chronological windows also pass an offline schedule-availability
check: five roles have at least five planned fitting dates, two validation
dates and two calibration dates. Persona-03 has sparse validation/calibration
and may remain ineligible; do not force extra actions or lower its thresholds.
Planned availability is not execution, native coverage or statistical power.

## 9. Operational checkpoints and slip rules

- Before ordinary collection starts: Codex must verify the hosted invoker's
  temporary role identity, durable canonical claims/budget store, neutral
  session names and preserved receipt attribution. The current IAM-user/local
  SQLite implementation is not a drop-in keyless hosted runner. No new secrets
  or permissions are authorised merely by this protocol. The owning user
  reviews any concrete deployment/approval items under the existing workflow.
- By 1 November, 12:00: check collection health and missed intended fitting
  dates. Do not move, compress or backfill windows automatically. Calculate
  whether each role can still reach the registered minimum using remaining
  planned active dates; report ineligibility if it cannot. Continue safe
  collection for engineering evidence, but a changed study requires a
  prospectively versioned protocol and still-uninspected future test data.
- By 3 November, 18:00: Codex records the candidate feature contract, planned
  comparator, implementation status and outstanding method decisions. By
  6 November, 18:00: complete an offline development smoke test on the available
  CLUE development data (or explicitly report the incompatible/missing inputs).
  These checkpoints do not promise a positive result. The actual implemented,
  hashed method annex is still due 8 November, 23:59; lateness is a v1.1 no-go.
- The 15 November review observes eligibility, delivery and implementation
  readiness only. It cannot revise the frozen method, score definitions,
  thresholds rule or selection criteria. A defect requiring method changes
  invalidates v1.1 scoring; register a new prospective method/calibration/test
  design or use the pipeline/offline-evidence fallback. Do not reuse inspected
  calibration results as proof of a newly selected method.
- The invoker must record coverage heartbeats on planned-idle days too. Missing
  heartbeats or unresolved attempts leave coverage unknown; a planned idle flag
  alone never confirms inactivity. Normal/model jobs remain inactive if their
  data gates fail, even when the invoker itself is running successfully.
- All buckets contain an object named `fixture.txt`; identical filenames in
  different buckets are different objects. Attribution uses native account/
  principal identity, never a filename or resource as the identity key. The
  target p06 fixture is also ordinarily accessible to persona-06; contextual
  account familiarity, not a globally malicious filename, is the probe.

One commissioned event and the offline reservation bound do not demonstrate
sustained throughput at the daily ceiling, complete feeds or future coverage.
Those remain operational observations to report as the pilot runs. No
scheduled reminders or cloud resources are created by these written checkpoints.
