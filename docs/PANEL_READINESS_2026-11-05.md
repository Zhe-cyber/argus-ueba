# Argus panel-readiness pack (5 Nov 2026)

**For:** competition (25–26 Nov), report (1 Dec), defence.
**Written by:** Claude, from a "hostile panel" review of the running preview.

Every number below is marked **measured** (with date and source) or **pending** (with the date it
arrives). Do not present a pending number as a result.

---

## 1. Argus in 30 seconds (plain language)

> Small companies use AWS, GitHub and Cloudflare but have no security team to watch them.
> Argus collects those logs into one place, links each person's accounts, and tells a
> non-expert **which few events deserve a look first, and why**, in plain facts rather than a
> black-box score. A person always makes the decision; Argus never blocks or punishes anyone
> automatically.

**What is new.** Commercial UEBA (Microsoft Sentinel UEBA, Exabeam, Splunk UBA) is closed and
priced for SOC teams. Open tools (Wazuh, OpenUBA, HELK) lack behavioural models with faithful
explanations. Argus combines:
1. a cross-provider timeline with **approved** identity links;
2. a behavioural model whose score splits **exactly** into per-feature parts (glass box);
3. an honest "not enough evidence yet" state instead of a fake "Low".

---

## 2. Two-minute demo script (item #1)

Run it in **Presentation mode** (the link under the page title) so account IDs and emails are
masked. Presentation mode is read-only. For step 5, either switch it off on a persona record or
play the pre-recorded clip (see §6, decision).

| # | Screen | Say | Show |
|---|---|---|---|
| 1 | Connections | "Three real providers, collected continuously. Every planned test action is checked against the provider's own log." | The three source cards; "verified" counts |
| 2 | Work queue | "52 rule alerts, all recorded High. A small team can't read 52." | The summary line |
| 3 | Work queue, **Triage = Review first** | "Argus puts 5 first: activity on the AWS **root** account outside Malaysian office hours. 31 are automation accounts and 15 are inside office hours; they are context, not alarms." | The 5 rows |
| 4 | Finding #32 | "Root account, 07:09 Malaysian time, a cost query. Here is exactly what fired and when." | Drawer: triage, event time in Malaysia, action, resource |
| 5 | Case | "The analyst opens a case, adds the person's other accounts, writes a decision. Everything is audited and versioned." | Create case → note → decision → closed (or the recorded clip) |
| 6 | Entities → People | "One person, three providers. Linked only after recorded approval, which is evidence of ownership, not proof of who acted." | Person with approved links; cross-provider timeline |
| 7 | Account-day model panel | "The behavioural model explains each score feature by feature, or says precisely why it can't score yet." | A scored day with per-feature terms (from about 7 Nov), or "0 of 5 usable days" |
| 8 | Headline slide | "Benchmark result, collection completeness, cost." | §5 table |

**Backup scenario (14 Nov):** persona-01 and persona-02 make an unannounced substitution to
bucket p06. If the A2 case study produces a finding, step 4 uses that finding instead.

---

## 3. Glossary: screen word → what to say (item #5)

| On screen / in docs | Say instead |
|---|---|
| Finding (security) | An alert from a fixed rule, for example first-time action at an unusual hour |
| Observation | Low-priority context, for example a new account appeared |
| Triage: Review first | Look at these first |
| Triage: Context | Recorded, but probably normal: automation, or inside office hours |
| Recorded severity | The severity the rule assigned; Argus does not change it |
| UTC rule window | The rule's fixed "working hours" in UTC. The panel shows the Malaysian time next to it |
| Receipt / diagnostic receipt | A sealed record of one account-day's model result, so the score shown can be re-checked |
| Cold start / insufficient history | The model needs 5 normal days of an account before it scores; until then it says so |
| Coverage / usable day | A day where every planned test action was confirmed by the provider's own log |
| Isolated data copy | The dashboard works on a copy, so demos and tests can never damage live records |
| Persona | One of 6 scripted test employees with fixed AWS roles and routines |
| Approved identity link | "These accounts belong to the same person", confirmed and recorded by a human |
| Unverified origin | An alert whose source we cannot trace, kept separate on purpose |

**Rule for slides:** never use "receipt", "coverage policy", "history scope" or "projection" on a
slide. Use the right-hand column.

---

## 4. Panel attacks and prepared answers (item #7)

Answer first in one sentence, then give evidence. Never defend more than the evidence.

**A1. "Where is the AI? The screen says model scoring is not enabled."**
- The rules triage; the model explains behaviour.
- The model is deliberately **not** allowed to raise alerts or risk tiers on live data until its
  frozen evaluation is done. That is a safety choice, not a gap.
- Show the account-day panel: the per-feature score, or the precise "why not yet".
- Benchmark result: §5 (pending 16–17 Nov).

**A2. "All 52 alerts are High. That's alert fatigue."**
- Correct, and we measured it.
- The triage view reduces the 52 to **5 to review first** (measured on the 4 Nov copy) without
  changing what was recorded, so nothing is hidden.
- The 5 are mostly AWS root-account use, which is exactly what should come first.

**A3. "Your after-hours rule uses UTC. Malaysian mornings count as after hours."**
- True. The rule window comes from the benchmark data's time zone and is frozen while evaluation
  runs, so results stay comparable.
- The screen now shows the Malaysian time and whether it was inside office hours (Mon–Fri
  08:00–18:00).
- A per-company time zone for the rule is implemented after collection closes (spec W4-B,
  16–17 Nov), so from then on alerts say "outside office hours (MYT)".
- The model's own frozen UTC feature is unaffected.

**A4. "You scripted both the normal behaviour and the attack. Isn't that circular?"**
- For the live case study, yes, partly. That is why we claim only a *descriptive* outcome on 3
  target slots, never a detection rate.
- The detection-quality claim comes from the **CLUE benchmark**: realistic behaviour, a sealed
  time window evaluated once, and injected scenarios in four families.
- The live part proves the pipeline works on real provider logs.

**A5. "Does deep learning beat a simple rule?"**
- We test exactly that. Baseline **BL** (largest positive z-score) is evaluated on the same rows
  as the autoencoders.
- The result is reported per scenario family, whichever wins. See §5.
- If BL wins a family, say so: "Then the autoencoder's value is the exact per-feature
  explanation, not raw accuracy, for that family."

**A6. "Can an SME actually run this? It's on a laptop and Wi-Fi drops broke it."**
- The laptop is the student testbed, not the deployment model.
- The Wi-Fi gap is documented: actions were recorded as unknown or missed, **never silently
  filled**, which is the honesty property you want in a security log.
- Cost: §5 (measured from the bills).

**A7. "How is this different from Microsoft Sentinel UEBA?"**
- Sentinel is Azure-centric and licensed per GB ingested; its explanations are insight tags, not a score that adds up.
- Argus is open, provider-neutral, and its model score adds up exactly from per-feature parts.
- We do **not** claim better detection than commercial tools; we could not run them on the same
  data.

**A8. "How do you know the explanation is faithful?"**
- The score *is* the sum of the per-feature reconstruction errors, so the explanation is the
  score broken down, not an approximation.
- This is enforced in code: receipts whose terms don't add up are rejected (C11 test
  `invalid_terms`).

**A9. "Your FYP1 said AUROC 0.976 with SHAP. Why is FYP2 different?"**
- FYP1 was CERT with an Isolation Forest SHAP layer.
- The claims audit (25 Oct) found the explanation and the detector didn't match, so FYP2 rebuilt
  it with exact per-feature terms on the detector actually scored, and a stricter one-shot
  evaluation.
- Lower but honest numbers beat high ones that can't be defended.

> ⚠️ **`QNA_PREP.md` (FYP1) is outdated.** Do not reuse its Q3, Q4, Q6, Q9, Q15 or Q17 answers
> without checking them against `research/competition-claims-audit-2026-10-25.md`.

---

## 5. Headline slide (item #6): fill on 16–22 Nov

| Claim | Number | Status |
|---|---|---|
| Collection completeness, AWS controlled actions, 1–4 Nov | **69 / 69 actions; 24 / 24 role-days usable** | measured 5 Nov, coverage policy v2 |
| Providers live | AWS CloudTrail, GitHub, Cloudflare Access | measured |
| Alert triage | 52 recorded-High rule alerts → **5 review first** | measured on the 4 Nov copy |
| Benchmark detection (CLUE, sealed 15–28 Jan 2018), per family: AUROC / AP vs BL | — | **pending 16–17 Nov (C4)** |
| AWS controlled case study (3 target slots) | — | pending 16 Nov, if the 13 Nov release passes |
| Live model diagnostics: share of account-days scored | — | pending (C7, from about 7 Nov) |
| Delay from provider event to stored in Argus (median / p95), verified test actions 1–5 Nov | AWS **4.8 / 4.9 min** (n=74, max 9.9); Cloudflare **5.0 / 5.1 min** (n=25); GitHub 0.1 / 0.1 min (n=16, max 15.0) | measured 5 Nov. The delay is set by the 5-minute collector cycle. GitHub is near zero because its pilot collects straight after acting, so don't present it as typical GitHub delay. All-events medians are misleading: the collector's own AWS calls (`GetCallerIdentity`, `AssumeRole`) are about 70% of AWS events and are stored almost instantly |
| Monthly cost (AWS + Cloudflare + GitHub) | — | to measure from bills (B3) |
| Deduplication (B1.3) | **0 duplicate events** in the live store; enforced by a unique index on (source, provider account, native event ID) | measured 5 Nov, read-only |
| Case workflow and stale-edit safety (B1.6/B1.7) | Finding → case → note → closed with a 5-entry versioned audit; a retried request does not create a second case; a stale edit is rejected (409) and the first edit is kept | measured 5 Nov on a disposable copy (`b1_acceptance_check.py --copy-writes`) |
| Automated tests | 747 passed, 1 skipped (`scripts/tests`, 5 Nov) | measured; one run, counts not added across runs |

---

## 6. Item status and remaining decisions

| Item | Status |
|---|---|
| #1 Demo story | This document §2. Rehearse with a timer; record a clip of step 5 as backup |
| #2 Model in the UI | No UI work needed: the panel already shows scores and terms when a receipt is scored. Scores appear once personas reach 5 accepted days (about 7 Nov) and the daily `Argus-Diagnostic-Refresh` runs. Claude verifies on about 7–8 Nov (C7) |
| #3 Alert triage | **Done (display only).** `workspace_next/finding_context.py` (`triage`, `local_time`), `queries.py` (filter and counts), `case_api.py` (param), `frontend/pages/workspace.js`. Verified on the side preview 3012/8016. Tests: `scripts/tests/test_finding_triage.py` |
| #4 Malaysian time context | **Done (display only)** in the same change: event time in MYT, inside or outside office hours. Rule logic in `backend/` is untouched (pinned during collection) |
| #5 Plain language | §3. Apply it to the slides; the UI labels stay as they are for now |
| #6 Headline slide | §5 template |
| #7 Q&A | §4 |

**Deploying #3/#4 to the main preview (3011/8015)** requires restarting the preview API and
rebuilding its frontend. The 3011 frontend copy is
`data/live/workspace-case-preview-20261030-v1/frontend`; copy in `pages/workspace.js`, run
`next build`, then restart. Do this outside 08:00–19:30 (collection hours) and after the user
approves.

**Decided 5 Nov (user):**
- Demo step 5 uses a **pre-recorded clip** of the case workflow.
- 3011/8015 are redeployed with the triage view on 5 Nov after 19:30 (scheduled task
  `argus-deploy-triage-to-3011-2026-11-05`).
- The UTC rule-window fix itself is spec `specs/W4-B-tenant-office-hours-rule.md`, implemented
  16–17 Nov after collection ends.
