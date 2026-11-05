# Task allocation: Claude's summary for Codex, 31 October 2026

Written by Claude at the user's request, so Codex and Claude can allocate work fairly. The agreed
ownership rule stays: **Claude owns offline model work; Codex owns the live system, the AWS study
implementation and the dashboard/UI, and reviews Claude's work.** Each reviews the other's
deliverables, and neither runs the other's single-use steps (fits, releases, evaluations).

## 1. Claude: done (all reviewed by Codex)

| Item | Status |
|---|---|
| W33 reader, features, export, validation report | Done; export gates pass (74 accounts; 3,468/275/510 rows) |
| W33 training code (B/C, C-norm, BL, thresholds) | Done; the single fit (run by Codex) verified and adopted |
| W33 evaluator + rehearsal v2 + **release** | Done; release `a84e67af…`; January test still sealed |
| Live v2 compatibility diagnostics (`audit_clue_v2_live.py`) | Done; final review passed; no nine-feature live input yet |
| Explanation module (`explain_clue_v2.py`: error terms, behaviour facts, why-unscored) | Done; final review passed |
| Dashboard plan addendum §7 (explainability layers, timing) | Done; Codex's corrections merged |
| Read-only reviews: dashboard build, collection incident follow-up, V3 decision record | Done |

## 2. Claude: pending (proposed owner: Claude)

| # | Task | Due | Notes |
|---|---|---|---|
| C1 | **Live explanation receipt:** a versioned per-account/day record (full key, cut-off, model/scaler/extractor/explainer hashes, history provenance, timezone, transformed feature names, eligibility, why-unscored, completeness-unknown, raw score, additive/share terms, facts, limitations, "diagnostic only / not validated" labels). Synthetic tests now; populated from live data once persona days are eligible. | ~4 Nov | Requested in Codex's final review. Codex consumes it in the UI. |
| C2 | **Diagnostic history rule:** for live v2 diagnostics only, a persona day counts as history only if ≥90% of its planned actions are verified (same ledger as the study). Declared before any persona day is scored. | with C1 | Doesn't touch the AWS study or W33 |
| C3 | **W33 result packaging:** report markdown, `metrics.csv`, per-scenario ROC figures, dominance and coverage tables; synthetic tests now. | before 16 Nov | Runs on real output only after the single evaluation |
| C4 | **W33 evaluation run:** `evaluate` once, with release SHA `a84e67af…` | **16 or 17 Nov MYT** | Claude's single-use step |
| C5 | **W33 explanations of reserved results** for the Research / CLUE replay page | 18–20 Nov | Only after C4 |
| C6 | **Tidy the live-compatibility handoff document** (final API and wording in the main section; correction record kept as history) | now | Minor |
| C7 | **Live v2 diagnostics reruns** (new output paths) once persona days have nine-feature input | from ~5–7 Nov | Diagnostics only, no activation |

## 3. Codex: tasks as Claude understands them (Codex to confirm)

| # | Task | Due |
|---|---|---|
| X1 | **AWS study V3:** amendment record, updated date guards in the AWS study code, tests, commit and controlled runtime release; extend actors and pilot services to ~16 Nov; recheck case-slot eligibility for 14/15 Nov | **before 13 Nov** (bound sources before 10 Nov 00:00 MYT) |
| X2 | AWS V3 rehearsal, freeze (13 Nov), cases (14–15 Nov), evaluation (16 Nov) | per V3 |
| X3 | Daily operational monitoring, 1–15 Nov; alert the user immediately on any missed slot | daily |
| X4 | Dashboard P0 fixes: truthful score states, finding categories, "Confirmed Insider" storage check with legacy preserved | now |
| X5 | Dashboard review fixes: timezone in "outside business hours" text (rarity-scorer notes first), service/workload accounts and first-time noise, readable names plus presentation masking, readable event details, Connections states with ages | before demo |
| X6 | Case store, queue, evidence drawer, edit protection, tested backup/import/rollback; built on a copy, cutover after the AWS study | per plan |
| X7 | **Restore the Research / CLUE replay link** in the new navigation | before demo |
| X8 | UI integration of C1 receipts: "experimental model diagnostic — not validated for this live source" | after C1 |
| X9 | **Versioned GitHub live adapter** for `github_repository_activity_v1` / `activity_type=push` (frozen W23 map untouched) | before demo |
| X10 | **Competition runtime:** always-on app service independent of the laptop pilot | decision ~10 Nov; ready by 22 Nov |
| X11 | Cost and setup measurements (read-only Billing, setup steps per source, analyst steps) | before demo |

## 4. Needs a decision or owner

| # | Item | Proposal |
|---|---|---|
| U1 | **Showing experimental live persona scores in the demo** (no alerts or thresholds) | User decides. Claude supplies receipts (C1); Codex displays them (X8). |
| U2 | **Public inconsistencies:** the paper's SHAP statement (TreeExplainer on the Isolation Forest, not KernelExplainer); the stale HF Space and Vercel deployments | Paper: user. Deployments: Codex (update or take down before judges see them). |
| U3 | **Commit/backup of the worktree** (everything since `e5c57d9` is local only) | User, using the checklist; remove the personal email from `docs/IDENTITY_MAPPINGS.md` first |
| U4 | Final report (due 1 Dec) | User, after 16–17 Nov results; deferred by the user |

## 5. Fairness and conflict rules

- Single-use steps belong to their owner: the W33 evaluation is Claude's (C4); the AWS V3 freeze,
  cases and evaluation are Codex's (X2). Neither runs the other's.
- Reviews stay cross-checked: Codex reviews C1–C3; Claude reviews X1 (date-guard changes) and X9
  (adapter) on request.
- New files, separate modules: no edits to the other's owned files without a handover.
- Load balance: Codex's list is longer and has hard dates (X1, X3). Claude can take overflow
  offline/testing work on request, e.g. synthetic tests for X1's date guards or X9's adapter,
  delivered as new test files for Codex to review.
