# Codex review of prospective AWS study V3 decision

31 October 2026, about 20:06 MYT. Reviewed the worktree decision file; the supplied
OneDrive path was unavailable. This review changes no runner, schedule, source
pin, model, protocol gate, ledger or cloud resource.

## Verdict

V3 is a coherent **new prospective run**, preserving V2 as a failed-coverage
attempt. The fresh seven-day fitting interval restores the possibility of the
unchanged count/span gate. At inspection there were **zero AWS ledger entries
dated 1 November or later**. No future observed outcome was inspected.

One substantial planned limitation is already determinable: the proposed dates
provide **three of four target slots and only one complete case/control pair**.
Record that now; do not discover it after collecting and select an easier date.

## Frozen-generator availability, no provider calls

Recomputed `make_plan` from the unchanged v2 profile/seed:

| Case date, MYT | Target | Planned actions | GetObject actions | First eligible read |
|---|---|---:|---:|---|
| 14 Nov, Saturday | persona-01 | 2 | 1 | 11:23 |
| 14 Nov, Saturday | persona-02 | 5 | 4 | 11:21 |
| 15 Nov, Sunday | persona-01 | 2 | **0** | **Unavailable by design** |
| 15 Nov, Sunday | persona-02 | 5 | 3 | 11:56 |

Keep the missing persona-01 control slot unavailable, as the decision allows.
Do not change its operation, replace a target, strengthen the scenario or add an
extra action. Report both attack-like target slots, the one available approved
control, and the missing planned comparison explicitly. Paired results are only
available for persona-02. No denominator may count the absent slot as a negative.

**Implementation consequence:** current `reserved_study.transform` raises when
either target has no GetObject, aborting the entire day. A date-only replacement
would therefore block 15 November, including persona-02 and ordinary roles.
V3 needs explicit per-slot availability metadata: skip only the unavailable
substitution, retain the original ordinary actions, and preserve release-first
execution guards. The evaluator must distinguish an unavailable scenario from
missing native receipts and ordinary-role controls. This is necessary handling
for the already-approved design, not an invented replacement scenario.

## Date and provenance requirements

- Fitting 1–7 Nov; validation 8–9; calibration 10–12; release 13; cases 14–15.
- Make the receipt cutoff exact: **15 Nov 20:00:00 MYT**. Earliest final evaluation
  should be **16 Nov 00:00 MYT**, checking both the calendar gate and receipt cutoff.
  “16 Nov, after 20:00 on 15 Nov” otherwise leaves a 15-Nov evaluation ambiguity.
- Make runtime expiry exact rather than “about”: e.g. services through 16 Nov,
  expire **17 Nov 00:00 MYT**; actor writes end after 15 Nov. 16 Nov is receipt
  reconciliation/read-only collection, not another actor day.
- All bound method/executor/evaluator source must be committed unchanged **before
  10 Nov 00:00 MYT**. “Implementation/tests before 13 Nov” is too late for source
  changes. Target fit-copy engineering rehearsal on 8 Nov and review/commit by
  9 Nov. Release on 13 Nov may not repair bound code after calibration starts.
- Preserve V2 protocol/annex and failure report. The annex embeds V2 dates, so
  add a V3 date-binding amendment/annex rather than claiming its literal date text
  remains applicable unchanged. Mathematical method and gates stay unchanged.
- Snapshot V2 source bytes/hashes before modifying uncommitted source, plus
  relevant configuration/receipt provenance privately. Do not reset the existing
  ledger or erase V2 claims. V3 exports/bundles/releases/reports need explicit
  protocol identity, partition dates and fresh output paths; reject V2/V3 mixing.

## Operational implementation inventory

Date guards also occur outside the reserved executor:

- `live_history_readiness`: partition windows and span gate (gate unchanged).
- Export/trainer/method bundle bindings and compatibility checks.
- `reserved_study`, ordinary-runner reserved-date refusal, wrapper, evaluator,
  calibration-start commit guard and release-only date.
- `local_pilot`: date validation, reserved routing, actor end, service timer and
  configuration identity. Do not rerun initialization/reset the live state.
- Task expiry XML/update paths, daily checker END and its task/config source pins.
- Rehearsal synthetic dates/freeze and development-check pre-calibration deadline.
- Daily reports and documentation must identify V3, without silently reclassifying
  V2's failed dates as usable evidence.

Changes to `local_pilot.py` also affect GitHub/Cloudflare machine source bindings.
Perform a reviewed dependency release for only expected changed hashes; preserve
their own original action/credential expiry dates unless separately instructed.
Changing the AWS pilot expiry does not itself authorize extra Cloudflare/GitHub
workload days. Preserve the W33 split/release/evaluation sources and dates.

Do staged implementation/tests against copies before the controlled runtime
release. Verify all relevant task/config/health pins together, never broadly
disable validation or blindly overwrite source hashes. Do not create a false
1-Nov complete day if deployment or laptop availability misses real activity.

## SDK budget check

Existing reservation total at review: **125**. Frozen plan for 1–15 Nov has
**277 actions**. Conservative separate-run reservation upper bound is five SDK
calls per action (three preflight + one role + one action), giving a cumulative
upper bound of **1,510**, below the existing **1,792** pilot cap. No day exceeds
the existing 128/day cap under this bound. Keep caps unchanged and retain spent
reservations in the existing ledger. These are reservation bounds, not a promise
of provider billing cost or successful delivery.

## Still essential

Laptop awake/online/lid open and plugged in during activity windows. Moving dates
does not fix standby. Losing an endpoint fitting day again breaks the seven-day
span; no collection or scoring guarantee is implied by prospective V3 approval.
User controls global power/update settings, as the decision explicitly states.

This review supports proceeding with V3 under these explicit implementation
conditions. It does not claim the V3 implementation/runtime release is complete.
