# Spec: EVAL — How Argus is evaluated (model performance + system function)

**Owners:** Claude (part A1, A3 and the A/B packaging), Codex (A2, B1 runtime and UI evidence),
user (B5 and the final report).
**Written:** 4 Nov 2026.
**Status:** plan agreed with the user on 4 Nov.

## Goal

One agreed checklist that turns the collection period (1–16 Nov) into report-ready evidence for
two separate questions:
- **A. Model performance:** does the behavioural model detect unusual behaviour?
- **B. System function:** does Argus do what an SME needs, end to end?

Every FYP objective maps to at least one row in the final evidence table (section C).

## Non-goals

- No new dataset, model, retraining, threshold change or experiment.
- No user study. It stays dropped; B5 is optional expert feedback only.
- No change to the frozen W33 or AWS V3 protocols. This plan only *reports* them.
- A bad model result is reported as it is. B never depends on A being good.

## A. Model performance: three levels, three different claims

| Level | When | Data | Claim it supports | Claim it does NOT support |
|---|---|---|---|---|
| A1 W33 benchmark | Once, 16 or 17 Nov | CLUE, sealed window 15–28 Jan 2018, with injected scenarios | Detection quality on realistic behaviour with injected deviations | Real attacker detection |
| A2 AWS V3 case study | 16 Nov, if the 13 Nov release passes | Controlled AWS personas: 3 target slots plus same-day controls | Descriptive real-cloud outcome | Population recall or false-positive rate |
| A3 Live diagnostics | From about 6 Nov, plus a final run | Real AWS, GitHub and Cloudflare account-days | The pipeline runs on real normalised logs | Any accuracy on live data |

### A1. W33 benchmark (main accuracy result)

- **Command:** `evaluate_clue_v2.py evaluate` with the frozen release
  (`reserved-release-v1.json`, SHA `a84e67af…bee01`), then `package_clue_v2_results.py`.
- **Scenario families:**
  - `mass_access`;
  - `off_hours`;
  - `new_action`;
  - `account_switch`.
- **Detectors:**
  - A (frozen v1);
  - B (5 features);
  - C (9 features);
  - C_norm (C divided by each account's fit median);
  - BL (max positive z-score baseline).
- **Primary view:** the common subset, meaning days and cases that every detector can score.
  "All supported rows" is secondary.
- **Metrics, per family and detector:**
  - AUROC;
  - average precision, always next to the injected prevalence;
  - recall and normal-alert fraction at the 1% and 5% calibration budgets (strict `>`);
  - paired score change (median, and the fraction of cases that rose);
  - descriptive dominance (never a "winner" rule);
  - per-feature additive explanation terms.
- **Exclusions and unavailable cells are shown explicitly.** Exclusions are never counted as
  negatives.
- **Outputs:** `report.md`, `metrics.csv`, `roc-pr-<family>.png` and a hashed manifest. The
  packager reconciles every number with the scored rows before writing anything.
- **Failure rule:** a failed attempt stays claimed and is reported. There is no second attempt.

### A2. AWS V3 controlled case study

- **Gates:** the 13 Nov release happens only if every unchanged history, calibration and source
  gate passes.
  - Mandatory days: 1, 7, 8 and 9 Nov, for all 6 roles.
  - Status on 4 Nov: 1–3 Nov all 18 role-days complete.
- **Cases:**
  - 14 Nov: persona-01 and persona-02 make an unannounced substitution to bucket p06.
  - 15 Nov: persona-02 makes an approved change.
  - The persona-01 slot on 15 Nov is unavailable, never negative.
- **Report:** for each target slot, whether the primary and combined gates flagged it, compared
  with the ordinary same-day controls, plus coverage. Late receipts (after 15 Nov 20:00) are
  unscored.
- **If no-go:** report which gate failed, with the coverage evidence. No V4.

### A3. Live diagnostics (transfer and compatibility)

From the receipt runs:
- the share of closed account-days per source that are scored, cold start, invalid or not
  scored by policy;
- the "why unscored" breakdown;
- which of the 9 features each provider can supply;
- raw score distributions on normal live days, descriptively, with no thresholds and no CLUE
  cut-offs;
- 3–5 explanation spot checks per source, read for plausibility.

No accuracy claim is made, and no live risk tiers are produced.

## B. System function: the POC works for an SME

### B1. Requirement acceptance tests (core)

Scripted and repeatable. Each test gets pass/fail plus evidence (a masked screenshot, a log line
or an API response). They run on 18–22 Nov on the main dashboard, plus once on the preview
before the case-writer switch.

| ID | Requirement | Test (pass condition) |
|---|---|---|
| B1.1 | Collect from 3 providers | A fresh event from each of AWS, GitHub and Cloudflare appears, with the right source and account, within the expected delay |
| B1.2 | Normalise | The three sources show the same canonical fields in one view; unsupported events carry a reason |
| B1.3 | Deduplicate | A re-delivered event is not stored twice |
| B1.4 | Identity linking | An analyst approves a link, and the person's cross-provider timeline shows events from 2 or more providers. The link is presented as ownership evidence, not proof of who used the credentials |
| B1.5 | Findings | A rule finding opens with its evidence; observations are distinguished from findings |
| B1.6 | Case workflow | Finding → evidence → case → note → decision → closed, with a complete audit trail |
| B1.7 | Concurrency safety | A stale edit is rejected and reloaded, never silently overwritten |
| B1.8 | Model explanation | An account-day shows either a raw score with per-feature terms and facts, or a precise "why unscored". Never a fake Low |
| B1.9 | Privacy | The real AWS account ID, emails and IPs are masked on screen |
| B1.10 | Safety labels | Experimental labels are shown; no live risk tiers or alerts from the model |
| B1.11 | Live freshness | A receipt or data older than its limit shows as stale or recorded, never as current |
| B1.12 | Research page | The benchmark replay opens read-only, separate from live data |

### B2. Pipeline quality (measured over 1–16 Nov)

- **Completeness:** planned controlled actions versus native-verified actions, per role-day, from
  the coverage policy.
- **Latency:** event time to ingestion, median and p95 per source. AWS baseline on 1 Nov: about
  12 min median, 21 min p95.
- **Collector availability:** gaps with their causes, such as the Wi-Fi auto-connect fix on
  1 Nov.
- **Volume:** events per source, duplicates rejected, unsupported events and their reasons.

### B3. Practicality for an SME

- Actual AWS, Cloudflare and GitHub cost from the bills (measured, not estimated).
- Setup steps and time for a new tenant.
- Dashboard and API response times at the real data volume.

### B4. Engineering evidence

- Automated test counts per suite. Counts from different runs are not added together.
- Independent cross-implementation checks: C8 (AWS V3) and C11 (receipt round trip).
- Frozen-protocol and hash records.

### B5. Expert walkthrough (optional)

One walkthrough with Dr. Firdaus, reported as qualitative expert feedback, not a user study.

## C. Report evidence table (to fill in by 1 Dec)

| FYP objective | Evidence |
|---|---|
| Ingest and normalise multi-provider logs | B1.1–B1.3, B2 |
| Cross-provider identity investigation | B1.4–B1.7 |
| Behavioural model with explanations | A1, A3, B1.8 |
| Real-world applicability | A2, A3, B3 |
| Responsible design (privacy, honest labels) | B1.9–B1.11 |

## Timeline (MYT)

| Date | Work |
|---|---|
| 4–15 Nov | Collection continues. Claude: the B1 test script and a judge-style walkthrough of the current UI. Codex: UI and runtime fixes |
| 16–17 Nov | A1 (Claude), A2 (Codex), automatic packaging |
| 18–22 Nov | B1 run, B2 and B3 measurements, A3 final run, masked screenshots |
| 25–26 Nov | Competition |
| By 1 Dec | Report built from section C |

## Risk notes

- **A2 depends on mandatory days:** 7, 8 and 9 Nov still need 100% completion for all 6 roles.
  The laptop must stay plugged in and online, with Wi-Fi auto-connect on.
- **Live freshness:** B1.8 and B1.11 need a scheduled daily receipt job (C11 F2, Codex runtime)
  and masking (C11 F1).
- **No retuning:** never tune features, thresholds or the method after seeing A1 or A2 results.
