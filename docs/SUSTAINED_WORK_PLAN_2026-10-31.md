# Sustained work plan: Codex + Claude

**Queue/status superseded on 1 November:** use
`docs/ARGUS_SHARED_CONTINUOUS_WORK_PLAN_2026-11-01.md` for current allocation and
dates. This older document remains as planning history; frozen protocols retain
their authority.

31 October 2026. User requests sustained parallel progress using available session
capacity. Work toward completed deliverables, not token consumption for its own
sake. Token/context/usage limits are different; neither agent should claim to know
the other's exact remaining allowance or promise execution after its session ends.

## Outcome

A working Argus investigation POC on real connected cloud evidence, defensible
offline W33 evaluation, and a separately reported prospective AWS V3 case study.
Every unavailable result and collection gap remains visible. No additional
dataset/model experiment is introduced by this plan.

## Operating loop for both agents

1. Read this queue, the latest owner checkpoint and incoming review once.
2. Take the highest-priority **ready** item. Write its intended files and expected
   acceptance before editing. Do not edit the other owner's implementation.
3. Implement a bounded milestone; test behavior relevant to that change.
4. Record changed files, commands/results, limitations, artifact hashes and next
   ready item. Hand over a concrete review package, not a request to re-explore.
5. Continue to the next independent item while waiting for the other owner.
6. Stop only for completed ready work, a hard date/access gate, required human
   action, an external blocker with no useful independent work, or usage/context
   limits. Do not repeat passing tests, poll idle agents, invent experiments or
   busy-wait to spend tokens.

Before a context/usage limit, write a checkpoint. A later session resumes from
that checkpoint rather than redoing fits/tests or reopening a sealed test.
Do not rely on reaching the final available token before saving state.

## Codex queue (priority order)

| Order | Deliverable | Acceptance / boundary |
|---|---|---|
| X1a | Preserve failed V2 source/config provenance and prepare the V3 amendment | V2 reproducible; V3 dates explicit before affected future data; no claim/ledger reset |
| X1b | Implement V3 date guards, versioned export/bundle/release identity and unavailable slots on a staged copy | Pure tests cover phase boundaries, source-commit cutoff, no early release/evaluation, and missing p01 control not aborting other roles |
| X1c | Controlled runtime transition | Backups, exact reviewed pin changes, health identity and rollback; same generator/seeds/budgets; V3 actor/service dates installed without extending CF/GH work |
| X3 | Verify fresh source round trips and operational health | Native receipts, not just HTTP success; no uncertain action replay; daily report timestamp distinguished from current task health |
| X9 | Versioned GitHub live projection | Native repository-activity format verified; frozen W23 map untouched; unsupported kinds unavailable; source provenance preserved; no double ingestion |
| X8a | Define dashboard receipt consumer with fixtures | Invalid hashes/key/day/profile rejected; why-unscored rendered; raw MSE/share facts distinguished from risk; no activation |
| X8b | Review C1/C2 and integrate approved receipts | Same cutoff/event provenance; incomplete-day policy respected; account-day diagnostic distinct from legacy rule explanation |
| X7 | Restore Research / CLUE replay navigation | Real read-only replay endpoint; separated from live state; no early W33 reserved results |
| X6 | Final case migration/writer-switch rehearsal | Existing notes/owner/history retained, legacy links deterministic, rollback and conflict handling verified |
| X10 | Prepare competition app runtime and deployment plan | Independent of actor expiry; measured/scoped costs and access; no stale or contradictory public deployment silently advertised |
| X11 | Measurements and demo validation | Actual setup/analyst steps and measured cost versus estimates distinguished; privacy-reviewed captures; complete investigation journey |

Do not start new ML/data work to avoid difficult integration tasks. If C1/C2 are
under review, use the independent adapter/runtime/migration tasks rather than
rewriting Claude's modules.

## Claude queue (priority order)

| Order | Deliverable | Acceptance / boundary |
|---|---|---|
| C2-fix | Address `C2_LIVE_COVERAGE_CODEX_REVIEW_2026-10-31.md` | Actual substituted case rows excluded before ordinary-plan validation; aware ingestion cutoff; valid native account keys; synthetic regressions |
| C1a | Freeze a versioned explanation receipt schema with synthetic fixtures | Full scoped key, cutoff, hashes, accepted prior-day provenance, coverage, unavailable reasons, raw score, additive/share terms and factual context |
| C1b | Implement receipt generator on approved C2/explainer APIs | Same start-of-day state and cutoff throughout; no direct use of internal fact helper after commit; no source-agnostic fake coverage |
| C3 | Result packaging on synthetic evaluator output | Markdown/CSV/ROC/AP and exclusions reconcile; unavailable arms preserved; no real reserved execution |
| C6 | Keep handoff documentation current | Main interface is final; dated correction record retained |
| C7 | Eligible live diagnostics in fresh output paths | Only after quality and history requirements; diagnostic labels; no activation or live tiers from CLUE thresholds |
| C4 | Single W33 reserved evaluation | Only on 16–17 Nov MYT with exact verified release; owner Claude; preserve attempt/claim even on failure |
| C5 | W33 explanation/replay artifacts | Only after C4; provenance-bound and separated from live outputs |

Optional overflow for Claude: independent **new test files** for a Codex-declared
V3 or adapter interface. Do not monkeypatch away production gates, edit Codex's
implementation or run an AWS provider action to test it.

## File ownership and dependency handshake

- Claude: `live_coverage_policy.py`, `audit_clue_v2_live.py`, `explain_clue_v2.py`,
  new receipt/packaging modules and their tests. Frozen W33 sources/artifacts are
  governed by their own release and may not be edited opportunistically.
- Codex: AWS study/runtime/collector integration, `workspace_next/`, live adapter,
  UI and migration/deployment work. Existing live source changes require a
  reviewed runtime release; edit/test staged copies first.
- Shared boundary: `live_history_readiness.native_matches`. Codex may change V3
  partition dates in the owning module, but preserve matcher semantics/signature.
  Claude owns its live-only coverage wrapper, not the frozen helper. Publish the
  final source hashes after V3 changes; regenerate/version affected diagnostic
  receipts rather than pretending old hashes still match.
- No concurrent edits to the same file, global branch switches, index resets,
  bulk reformatting or automatic commits. Preserve LF bytes and source pins.
- Each agent writes its own checkpoint. A shared plan change must be dated and
  communicated; do not silently move another owner's acceptance criteria.

## Dated steps (Asia/Kuala_Lumpur)

| Date | Work |
|---|---|
| Now / before 1 Nov affected data | V3 amendment and staged implementation priority; C2 fixes/C1 fixtures in parallel |
| 1–7 Nov | Real V3 fitting collection; laptop availability matters; no backfill |
| 8 Nov | Full V3 engineering rehearsal on fitting-data copies only; synthetic later partitions; real validation collection continues |
| By 9 Nov | Review/fix and user commit; **all bound source committed before 10 Nov 00:00** |
| 8–9 Nov | V3 validation |
| 10–12 Nov | V3 normal calibration; no changes to bound method/scenario sources |
| 13 Nov | Codex-owned V3 release/freeze after actual gates pass |
| 14–15 Nov | V3 reserved actions; p01 control on 15 Nov unavailable by declared generator |
| 15 Nov 20:00 | AWS native receipt cutoff |
| 16 Nov, from 00:00 | Codex-owned AWS V3 final evaluation, if release/gates permit |
| 16–17 Nov | Claude-owned single W33 evaluation; independent of AWS outcomes |
| 17 Nov 00:00 | Installed AWS service expiry; not a permission for more actor days |
| 18–22 Nov | Reviewed results, replay integration and presentation/deployment checks |
| 25–26 Nov | Competition |

AWS cases have three available target slots and only one complete pair, persona-02.
Missing slots remain unavailable. New dates restore opportunity, not a guarantee
of valid history or good detection performance. W33 freeze stays 15 Nov 23:59.

## What neither agent may do automatically

- Forge/backdate/impute native evidence as successful actions, replay unknown
  claims, relax gates, retune on reserved results or retrain B/C.
- Run the other owner's single-use fit/release/evaluation, or execute future
  calendar steps early to keep busy.
- Activate live risk/alerts or publish experimental diagnostics as validated
  detection. User decision is still required for experimental live demo display.
- Commit/push for the user, change global sleep/update policy, or retire a public
  deployment without the concrete reviewed action and applicable authorization.

Power and Git actions remain with the human under existing decisions. Lack of
power, network or a human commit is a real blocker; agents cannot manufacture
progress around it.

## Sessions, notifications and background execution

This plan does not launch or keep an external Claude session alive. Give Claude
the companion continuation prompt in its own authenticated session. Codex and
Claude have separate usage limits. Handover files coordinate work; they are not
a running scheduler or proof that the other agent read a message.

Existing collectors/daily checks continue under their installed tasks. Immediate
notification delivery and an independent offline-laptop monitor are pending;
do not promise alerts while the only host sleeps. Future calendar work needs
an active/scheduled owner session at that time. No new automation is installed
by this planning document.

## Checkpoint format

Each owner maintains its own document (`reviews/CODEX_WORK_CHECKPOINT.md` or
`reviews/CLAUDE_WORK_CHECKPOINT.md`):

```text
Timestamp / owner / current branch and source root
Completed milestone and exact changed files
Verification commands, outcomes, artifact/report paths and hashes
Live services/source pins touched (or none)
Single-use claims already consumed; future gates still sealed
Incoming/outgoing review and unresolved findings
Next ready task and its acceptance
Blocked/deferred tasks and required user action
```

Keep credentials, raw native account data and private copied databases out of
handoff documents. Existing private artifacts remain ignored. When capacity is
nearly exhausted, save this checkpoint and give a concise final status; resume
later from it without repeating completed work.
