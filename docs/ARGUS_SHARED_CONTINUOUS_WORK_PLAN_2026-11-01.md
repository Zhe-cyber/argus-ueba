# Argus — shared continuous work plan for Codex and Claude

**Issued:** 1 November 2026. All operational dates/times are Malaysia time (MYT, UTC+08:00).
**Purpose:** one coordination document to give to both agents. This is a work allocation,
not proof that either agent is currently running or that future work has been scheduled.

This document supersedes the queue/status portions of
`docs/SUSTAINED_WORK_PLAN_2026-10-31.md`. It does **not** amend the frozen W33 protocol,
AWS V3 protocol, method, evaluation dates, source bindings or owner permissions.
If this plan conflicts with a frozen protocol, stop the dependent action and resolve
the discrepancy explicitly; do not silently change the experiment.

## 1. Shared objective and scope

**User priority update, 1 November:** defer the Research replay page. Concentrate
on the POC scoring-readiness → evidence → case → decision path. Retain evaluation
artifacts for the report; an optional replay page is not required for POC success.
Latest implemented workflow and remaining gates:
`docs/POC_PROGRESS_AND_RUNBOOK_2026-11-01.md`.

Deliver a working Argus investigation POC for the **25–26 November competition**:

1. Receive authentic AWS, Cloudflare and GitHub activity with source provenance.
2. Normalise supported activity, identify provider accounts and use analyst-approved
   identity links to investigate related activity across providers.
3. Complete the workflow: **finding → evidence → case → decision**, with the linked
   cross-provider timeline inside the case and a clear distinction between observations
   and security findings.
4. Present real AE results where the feature/history requirements are met, with honest
   explanations, coverage and experimental status. Missing/unsupported data stays unscored.
5. Present the independently frozen W33 benchmark and the separate, small AWS V3 study,
   including negative and unavailable results.

The priority is one usable end-to-end POC, not another dataset or another model experiment.
No new dataset, persona population, provider or retraining programme is introduced here.
Provider-account scoring and cross-provider identity correlation remain distinct capabilities.
An analyst-approved account link is evidence for ownership, not proof of who used credentials.

## 2. Confirmed starting point

These are checkpoint/review facts, mostly verified on **31 October**. They are not a fresh
1 November service-health measurement.

| Area | Finished / recorded | Remaining |
|---|---|---|
| AWS V3 runtime | Installed 31 Oct 22:16; exact backend health and successful post-cutover collection checked; 152 staged tests passed | Daily collection quality, rehearsal, human commit, actual model release/cases/evaluation |
| Old AWS V2 | Failed coverage preserved; original sources/config/database snapshots retained | Report its operational failure honestly; never repair its history |
| AWS ordinary schedule | All seven 1–7 Nov plans equal preserved V2 plans; no schedule contamination from cutover | Actual receipts still need to satisfy the gates |
| W33 B/C | Training already consumed; frozen release exists; January reserved evaluation remains sealed | Owner Claude evaluates once on 16 or 17 Nov |
| C1/C2 | Earlier implementation reviewed; 21 tests passed against V3 dependencies. Post-V3 receipt refresh completed 1 Nov 00:53: 63 receipts, 0 scored; content hash checked by Codex | Review the latest generator delta, clarify history scopes in C9, then dashboard consumption |
| C3 packaging | Implemented by Claude; nine synthetic packaging tests passed in Codex's check | Package actual W33 results only after the permitted evaluation |
| Dashboard workflow | Isolated preview, case API/store, evidence/timeline and migration/rollback work implemented | Final integration, user journey verification and controlled production cutover |
| GitHub / Cloudflare machines | Existing controlled workloads and collectors installed | Quality/receipt checks; GitHub live feature projection gap; no claim that workloads are humans |
| Live scoring | Post-V3 artifact `live-receipts-20261101-005313` has 63 receipts, 0 scored, and explicit missing-day receipts | Recheck accepted history; do not promise a score on a calendar date |

Evidence references:

- `reviews/CODEX_WORK_CHECKPOINT.md`
- `reviews/CLAUDE_WORK_CHECKPOINT.md`
- `reviews/AWS_V3_CUTOVER_AND_CLAUDE_HANDOFF_2026-10-31.md`
- `reviews/AWS_V3_RUNTIME_RELEASE_2026-10-31.json`
- `reviews/C1_C2_POST_V3_REVIEW_2026-10-31.md`

Post-V3 refresh manifest SHA256:
`df5a033c46a3f91fdd5d48da59354457f182031bda4932fa1ad4c66ccd62193c`.
This verifies the saved artifact, not fresh service health or new model performance.

## 3. Working locations and ownership

Active shared source checkout:

```text
C:/Users/yyzhe/.codex/worktrees/clue-benchmark-replay/fyp-ueba
```

Observed branch: `six-role-commissioning`. Do not switch/reset it or overwrite the other
owner's uncommitted work. The user handles commits and pushes.

The actual pilot data remains under the older checkout:

```text
C:/Users/yyzhe/.codex/worktrees/argus-cloud-live/fyp-ueba/data/live/
  pilot-local-v1/config.json
  connected/events.db
  persona-history-v1/ledger.db
```

The isolated dashboard preview uses **3011/8015** and a private copied database under
`data/live/workspace-case-preview-20261030-v1/`. The original pilot uses **3000/8013**.
Neither agent should mistake a preview copy for the live store.

| Owner | Owns | Must not do without a handover |
|---|---|---|
| Codex | AWS V3/runtime, collector and live projection integration, `workspace_next/`, dashboard/API, migration and competition runtime | Edit Claude's receipt/coverage/explanation/W33 implementations or execute W33's reserved test |
| Claude | W33 offline pipeline/evaluation, live diagnostics, coverage policy, explanation/receipt modules, result packaging and their tests | Edit Codex's AWS/runtime/UI implementations or execute AWS reserved steps |
| User | Manual commits/pushes, laptop power/network, required account sign-ins and final live-display approval | No need to keep answering routine implementation questions already settled here |

Both agents can perform read-only cross-review. Independent regression tests go in new,
clearly owned files. Test fixture/output data must never enter a real event store.

## 4. Codex queue — execute in this order when ready

### X3 — operational checks, alongside other work

- Check source pins, owned backend identity, task state, tick/poll timestamps and native
  receipts when beginning/resuming operational work or investigating a failure.
- Inspect per-role closed-day planned/verified/missed/missing/unresolved counts.
- Distinguish outside-window inactivity from a failed/stale collector.
- Preserve unknown claims and missed actions; never replay uncertain operations or backfill.
- Record findings once in the checkpoint/incident report. Existing daily checks are useful,
  but neither agent promises immediate monitoring while its session is inactive.

**Acceptance:** a timestamped operational assessment; failures and affected gates are clear.
Do not rerun the V3 installer or initialise/reset the ledger.

### X9 — fix the GitHub live projection

**Completed 1 November:** live-only native projection implemented; 70/70 stored
GitHub records supported in a read-only check. See `reviews/X9_X8_CODEX_HANDOFF_2026-11-01.md`.

- Verify the actual repository-activity record and its native kind/provenance. The reviewed
  gap was the bot's `Repository push` label not matching the frozen feature label map.
- Implement a **separate, versioned live projection**. Preserve frozen benchmark/W23/W33
  mappings; do not add a permissive fallback that invents supported actions.
- Preserve source scope/account/event identity; prevent duplicate ingestion.
- Test a supported native push plus unsupported/malformed kinds and account separation.
- Stage any source-pinned runtime changes, review the exact dependency delta and release
  them through the controlled pin/health/rollback process.

**Acceptance:** supported real GitHub activity produces the intended canonical input;
unsupported activity has a reason; no benchmark artifact is invalidated.

### X8a/X8b — consume Claude's receipts and connect the evidence drawer

**1 November milestone:** consumer, contract, opt-in API and Entities diagnostic
panel implemented/tested on the isolated preview. Actual display remains disabled.
C11 is ready now; finding/case context and final integration remain pending.

- Publish the intended consumer contract/fixture examples before requesting parallel tests.
- Review Claude's post-V3 generator delta (dependency provenance and zero-event gap
  receipts), plus the subsequent C9 schema update, before integrating them. Approval of
  the earlier version does not automatically approve newer code.
- Validate schema, source/scope/account/day, cutoff, manifest/content hash and expected
  model/scaler/feature/policy/projection/source bindings.
- Refuse stale, malformed or mismatched output. An absent receipt is unscored, never Low.
- Render raw reconstruction error, additive feature terms and factual context separately
  from rule-based findings and investigator decisions.
- Show a concise unavailable reason and coverage summary; keep detail in the drawer.
- Display **expanding history for feature 5** separately from the **last ≤28 usable days
  for features 6–9**. Do not label the last 28 as the entire input history.
- Build/test the UI using synthetic receipts before eligible live scores exist.

**Acceptance:** one account-day opens to correct evidence/explanation or a precise unscored
reason; no fake risk tier, AI verdict or implicit live activation.

### X7 — restore research / benchmark replay access

**Deferred by the user.** Do not take this ahead of collection, real AE readiness,
case workflow, live writer switch or competition runtime. Existing benchmark data
and reports stay preserved; this deferral changes no evaluation protocol.

- Provide a working read-only replay endpoint/navigation path using existing released
  artifacts, with benchmark/replay provenance visibly separate from live observations.
- Before W33 evaluation, only existing permitted results may be displayed.
- After Claude's permitted evaluation/package, add the reviewed result artifacts without
  triggering any new evaluation from a page load.

**Acceptance:** research pages work independently of live scoring and cannot open sealed data.

### X6 — complete case workflow and final writer-switch rehearsal

**1 November:** finding/event diagnostic context and immutable case retention now
pass the end-to-end preview test. Real readiness is visible; actual scores remain
gated. Daily source-pinned receipt refresh is installed at 08:25 MYT, expiring
17 November. Controlled live writer switch is still pending.

- Recheck queue noise, account naming/masking, machine-principal kinds and timezone wording.
- Preserve existing case IDs, owners, notes, decisions and audit history. Keep legacy
  statuses explicit rather than silently translating them.
- Verify stale edits are rejected, and investigate → evidence → case → decision works.
- Rehearse backup → import → verification → rollback on a copy before the real switch.
- Do not allow the preview and original app to become conflicting case writers.

**Acceptance:** one complete analyst journey, a tested migration/rollback report and a
controlled switch with preserved records. The V3 backend restart was not this dashboard cutover.

### X10/X11 — competition runtime and demo checks

- Prepare an app runtime independent of the temporary pilot task expiry.
- Review deployment access, configured endpoints, source/receipt update paths and actual
  operating costs; distinguish measured costs from estimates.
- Test the full journey, masking and failure/unavailable states; capture real screenshots.
- Resolve stale public deployments through a concrete reviewed action; do not advertise
  an old deployment as the current system.

**Acceptance:** a documented competition runbook, repeatable demo and reviewed result labels.
Deployment or enabling experimental live display follows its separate approval boundary.

## 5. Claude queue — ready work now, then date-gated work

Claude's C1/C2/C3 implementations are complete. Do not restart them or invent another
experiment to stay busy. The following are useful next coordination tasks.

| Order | Task | Ready condition | Output / acceptance |
|---|---|---|---|
| C8 | Read-only review of installed AWS V3 | **First; ready now** | Review date/deadline guards, release failure paths, unavailable p01 slot and receipt cutoff semantics; new independent synthetic tests only if useful. Report blockers without editing Codex-owned code |
| C9 | Clarify receipt history provenance | **Second; after C8** | Receipt schema v2, retaining the old field and adding explicit expanding-history and rolling-history lists; synthetic >28-day regression. Scores/history selection unchanged; frozen W33/AWS sources untouched |
| C10 | Refresh post-V3 receipt artifact | **Initial refresh done** 1 Nov 00:53; repeat only after C9 or another relevant dependency change | Fresh v2 output following C9, current hashes and unchanged activation=false. Preserve old outputs; no rerun just to repeat the same zero-score count |
| C11 | Independent receipt-consumer fixtures/review | After Codex publishes the exact consumer contract | New fixture/test files for corrupt hashes, wrong scope/day, stale output, no receipt, incomplete history and valid additive terms. No competing consumer implementation |
| C7 | Eligible live diagnostic rerun | Actual coverage/history gates met | Fresh receipts with honest raw scores/explanations; no guaranteed first-score date and no live tiers |
| C4 | Single W33 reserved evaluation | 16 or 17 Nov only; exact release verified | One permitted attempt, preserved claim/failure record, actual evaluation output; do not retry by deleting claims |
| C3-final | Package actual W33 output | C4 completed successfully | Existing packager produces reconciled Markdown, CSV, ROC/PR figures and hash manifest; exclusions/unavailable cells remain explicit |
| C5 | Explain results for Research/demo | Actual package reviewed | Accurate per-scenario findings, method comparison, limitations and source-bound artifacts for Codex's replay UI |

For C8, prioritise the deadline/guard/receipt semantics and missing persona-01 slot; do not
retrain, release, inspect reserved outcomes or run provider operations during review.
Review early enough for Codex fixes and a human commit before 10 November 00:00;
8 November is not the target start date for finding basic code defects.

C9's schema v2 is a live diagnostic receipt version, not a new model/feature contract.
Keep existing v1 artifacts intact. Codex's consumer should accept only explicitly supported
versions with their correct validation rules, not silently interpret v2 as v1.

For C10/C7, ensure the generator uses read-only source connections. Concurrent legitimate
collector writes can change database hashes during a run: do not misreport such a change as
proof the receipt generator wrote to the database. Record snapshot/cutoff provenance and the
existing separate-snapshot limitation accurately.

If these ready items finish and only date-gated tasks remain, Claude should checkpoint and
stop its session. Continuous work does not mean opening the reserved test early or burning tokens.

## 6. Shared dependency handshake

1. Owner publishes intended changed paths and acceptance before editing.
2. Build/test against copies where runtime pins or stores are involved.
3. Send a review package: changed paths, relevant tests, artifacts/hashes and unresolved risks.
4. Reviewer reads/reviews; implementation owner fixes findings.
5. Re-review only changed behavior or unresolved issues, not an endless repeat of passing checks.
6. Runtime owner publishes installed hashes after a controlled release.
7. Diagnostic owner creates **new** outputs bound to those hashes; old outputs are retained.
8. Each owner updates its own checkpoint. The user passes handoffs between sessions unless
   explicitly asking an agent to send them.

AWS's shared boundary is `live_history_readiness.native_matches`. Its interface/semantics
were unchanged by V3; the containing source file hash changed. C1/C2 are **not** AWS-bound
study sources. Their edits cannot by themselves violate the AWS source-commit deadline.
See the exact 18-file list in `reviews/AWS_V3_CUTOVER_AND_CLAUDE_HANDOFF_2026-10-31.md`.

Do not blindly recompute/accept all runtime pins. Confirm that the changed hash set is
exactly the reviewed delta and check the actual backend identity after restart.

## 7. Calendar and hard gates

| Date / boundary | Owner | Work / gate |
|---|---|---|
| 1–7 Nov | Installed AWS tasks; Codex checks | V3 fitting collection, unchanged daily plan, no backfill |
| 1–5 Nov target | Codex + Claude | GitHub projection, receipt interface/fixtures, fresh post-V3 handoffs and AWS source review |
| 2–15 Nov, optional writing slot | Claude if user opts in; Codex supplies architecture evidence | Draft design/method sections from implemented code and frozen protocols; system work first, no invented results |
| 6–8 Nov indicative | Claude | First eligible diagnostic scores only if ≥5 accepted prior active days and current-day quality hold; otherwise report pending |
| 8 Nov | Codex | Full engineering rehearsal on fitting-data copies; synthetic later partitions; real validation continues |
| 8–9 Nov | AWS tasks | Actual V3 validation collection |
| By 9 Nov | User, with reviewed checklist | Commit AWS bound files; preserve LF/pins and verify clean relevant paths |
| **10 Nov 00:00** | AWS release guard | All AWS bound sources' latest commit must be strictly earlier; no late code repair during calibration |
| 10–12 Nov | AWS tasks | Normal calibration collection; fixed method/scenario/gates |
| By 12 Nov | User + Codex | Decide recorded-only competition evidence versus separately scoped live-demo continuation; no automatic workload extension |
| 13 Nov only | Codex | Actual AWS release if all history/calibration/source gates pass |
| 14 Nov | AWS tasks under valid release | Unannounced substitution slots, p01/p02 |
| 15 Nov | AWS tasks under valid release | Approved control: p02 available; p01 unavailable by frozen generator |
| 15 Nov target | Codex | Integrated dashboard journey ready for final result ingestion; no claim all research results already exist |
| **15 Nov 20:00** | AWS evaluator | Native receipt-arrival cutoff |
| **15 Nov 23:59** | Claude / W33 guard | W33 freeze deadline; existing release stays protected |
| **16 Nov 00:00 onward** | Codex | AWS final evaluation, if gates/release permit |
| **16–17 Nov only** | Claude | Single W33 reserved evaluation, independently of AWS outcomes |
| Before 16 Nov | User | Choose 16 or 17 Nov for Claude, open an active session and provide checkpoint; separately resume Codex for AWS evaluation |
| **17 Nov 00:00** | Installed AWS pilot tasks | Service expiry; competition app runtime must not depend on this expiring task |
| By 17 Nov | Claude | W33 report/package, subject to a permitted successful evaluation |
| 18–22 Nov | Both; user checks | Review results, integrate replay, finish demo and presentation evidence |
| 25–26 Nov | User | Competition |
| 27–30 Nov | User, agents supporting | Complete actual-results/discussion chapters, reconcile figures/references and final report checks |
| 1 Dec target | User, agents supporting | Final report using actual results and recorded limitations |

GitHub/Cloudflare machine workloads still end **13 November**, with reconciliation through
**14 November**. V3 did not extend their workload/token schedules. Extending them would be
a separate decision, not an implicit consequence of this plan.

### Competition freshness decision

Without a separate continuation runtime, the competition uses recorded collection evidence:
GitHub/Cloudflare controlled workloads end 13 Nov, their reconciliation runs through 14 Nov,
and AWS pilot services expire 17 Nov 00:00. By 25–26 Nov, saved data is several days old.
Do not call it current live monitoring. Show its actual capture window, last-event/poll times
and provenance (for example, "recorded pilot activity, 1–16 November", only if the saved
artifact actually covers those dates).

The user decides by **12 November** between:

- **Recorded evidence:** valid default while no extension is approved; use accurate dates
  and a working investigation/replay workflow.
- **Live demo continuation:** Codex prepares a separate runtime/collection scope with
  reviewed cost/access/expiry and rollback. Preserve the frozen study snapshots and labels;
  later activity is outside the AWS/W33 evaluation and cannot repair missing study history.
  Extending provider workloads or credentials requires the separate decision before expiry.

Preparing that concrete runtime proposal is within X10. This document does not approve an
extension or promise that credentials, machines or endpoints remain active on competition day.

### Report-writing allocation

The 1 December target was already listed; writing effort was not allocated early enough.
Protect 27–30 November for finalisation. An optional 2–15 November slot can produce the
system design/method chapters and evidence index before results exist. Full chapter drafting
is pending the user's choice; it must not displace system integration or time-critical reviews.
Result sections use explicit placeholders until the permitted evaluations are complete.

### Sessions for the gated evaluations

No wake-up automation is installed. The user must open/resume **Claude on 16 or 17 November**
and point it to its current checkpoint and verified W33 release. Codex owns a separate AWS
evaluation session from 16 November 00:00, if its gates pass. Opening one session does not
activate the other. Existing one-attempt claim guards remain authoritative, including after
a crash; agents cannot bypass them to recover a missing result.

## 8. Go / no-go and fallback rules

| Situation | Required response |
|---|---|
| Missing/unknown action or a sleep/network gap | Preserve it, assess role-day gates; no invented receipt or uncertain retry |
| AWS V3 history/calibration/source gate fails | No model release or reserved substitution; report no-go and keep the pipeline/offline evidence. Do not automatically create V4 |
| Persona has insufficient accepted history | Unscored with counts/reason; do not borrow CLUE identities as that account's history |
| Provider input lacks meaningful supported features | Publish compatibility/unavailability result; no zero filling or forced portability claim |
| W33 attempt fails | Keep the claim/failure record and stop; no silent second attempt |
| Weak or negative detection result | Report it, including comparison and limitations; no post-test feature/threshold tuning |
| Analyst edit conflicts | Refuse stale edit and reload; never overwrite another decision silently |
| Runtime release fails | Restore verified source/config/tasks; preserve live event/claim data; document the failure |

The minimum finished deliverable remains the connected investigation POC plus defensible
offline evaluation. A small controlled AWS case study is additional evidence, not a
requirement to manufacture a successful detection result.

## 9. Human actions and existing approval boundaries

- Keep the laptop plugged in, awake, lid open and online **08:00–20:00, 1–15 November** for
  the planned AWS activity. Global power/update settings remain the user's responsibility.
- Commit/push manually with Codex's reviewed file list. Aim earlier than 9 November so
  rehearsal findings can still be fixed and reviewed before the strict cutoff.
- Complete required account sign-ins locally; never send credentials/codes through chat.
- Decide on **experimental live diagnostic display** only after the integrated screen and
  labels are reviewable. Backend fixture integration is not permission to activate live tiers.
- Review the final competition journey and privacy-masked captures.

No repeated permission request is needed for already-authorised routine code fixes,
read-only reviews or staged tests. Publishing/deployment and live activation retain their
applicable concrete approval boundary.

## 10. Continuous session loop and checkpoint

While an owner session is active:

1. Read this plan, its own checkpoint and the newest incoming handoff.
2. Take the highest-priority ready item; state intended paths and acceptance.
3. Implement one bounded milestone and run relevant tests.
4. Record evidence and update the checkpoint **before** context/usage becomes tight.
5. Continue to independent ready work while awaiting review.
6. Stop for completed ready work, a genuine blocker, required human input or a calendar gate.

The installed collectors and checks run as background tasks while the laptop permits.
The coding agents do not automatically keep each other alive, wake on future dates or
send notifications merely because a Markdown plan exists. No new recurring automation
is created by this document. Future gated steps require an active/scheduled owner session.

Each owner maintains its own checkpoint:

```text
Timestamp / owner / source root / branch
Completed task IDs and exact changed files
Tests and outputs, with actual hashes where needed
Runtime/source pins touched, or none
Single-use steps consumed; future test gates still sealed
Incoming/outgoing review and unresolved findings
Next ready task + acceptance
Blocker / date gate / required human action
```

Keep raw account IDs, emails, credentials, event dumps and private databases out of
shared handoffs. Test counts from different runs/scopes are not added into a fictional
whole-suite total.

## 11. Message to paste into each agent session

> Read `docs/ARGUS_SHARED_CONTINUOUS_WORK_PLAN_2026-11-01.md`, your own work checkpoint
> and the latest incoming review. Confirm the next ready task and its owned files,
> then continue the queue autonomously. Do not repeat completed fits/releases, touch
> sealed data, edit the other owner's implementation, commit/push, or activate live
> scores. Publish a concrete review handoff at each milestone and checkpoint before
> session limits. If only date-gated tasks remain, record that and stop rather than
> inventing work. The other agent's checkpoint is evidence of recorded progress,
> not proof its session is currently running.
