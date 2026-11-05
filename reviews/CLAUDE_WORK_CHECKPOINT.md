# Claude work checkpoint

**Timestamp:** 31 Oct 2026, about 21:55 MYT.
**Owner:** Claude.
**Source root:** `C:/Users/yyzhe/.codex/worktrees/clue-benchmark-replay/fyp-ueba`, branch
`six-role-commissioning`. Nothing has been committed; the user commits.

## Completed milestones

- **C2-fix** (`C2_LIVE_COVERAGE_CODEX_REVIEW_2026-10-31.md`):
  - coverage policy v2;
  - case-date rows partitioned before validation;
  - aware ingestion cut-off (`not_yet_ingested`);
  - account keys must match `acct_[0-9a-f]{64}`;
  - mapping diagnostics.
- **C1a/C1b:** schema `clue_v2_live_diagnostic_receipt_v1` and its generator.
  - Scores and explanations come from the same start-of-day state, via `explain` before
    `commit_original`.
  - Each cell carries `verified_native_event_ids` and `observed_events`.
- **C6:** `docs/CLUE_AE_V2_LIVE_RECEIPTS.md` has a dated "C2 v2 corrections" section.

## Changed files (SHA256)

| File | SHA256 |
|---|---|
| `scripts/live_coverage_policy.py` | `6f9d5e125401bd88814276976b3a066401c90df5ea9f27e3d50abffb58ee5e7a` |
| `scripts/live_receipts_clue_v2.py` | `cdfdd1dc88f63e200e9fa74256b8316af6cb4875a169b11083034c11b44abd9a` |
| `scripts/tests/test_live_coverage_policy.py` | `4b6a6975768f3f6ce024792890c7627d974cb86b980261489d0a2fc558023d3e` |
| `scripts/tests/test_live_receipts_clue_v2.py` | `29fbdfae7b286ef6b5eaf0907f97b0ca0b9195095fc823f5ac2f7967c9c93863` |

Coverage policy v2 SHA256: `89e5bdb35523a68c6c31b2aae0abe14c9c0160a03bed9041a37babb49f97c357`

## Verification

- The policy and receipt tests pass: 21 tests.
- Full `scripts/tests` suite: **636 passed, 1 skipped**, run with `DATABASE_URL=sqlite-local` and
  basetemp under `data/live/test-runs/`.
- Real read-only run → `data/processed/clue-ae-v2/live-receipts-20261031-215118/`:
  - manifest SHA256 `6c92c2aa7e64ff750c0d1b546425475035a2ac19df41ee9ab24e9f865ce52e37`;
  - receipts SHA256 `538eef3ec58da3bd6917ae10c743cdc41ae26a0d8852ac711b1fca2bfe4c0835`;
  - 53 receipts, 0 scored;
  - all six personas mapped; no invalid or late rows;
  - 30 Oct: 2 usable, 4 incomplete.
- Live store and ledger SHA256 were identical before and after the run.

## Live services and source pins touched

None. `readiness.native_matches` is unchanged.

## Single-use claims

- **W33 B/C training:** consumed under `training-prereg-v2`.
- **W33 release:** `reserved-release-v1.json` (SHA256 `a84e67af…bee01`).
- **Still sealed:** the W33 reserved evaluation, C4. It runs once, on 16 or 17 Nov MYT only.

## Reviews

- **Outgoing:** C1 + C2 v2 to Codex (X8b).
- **Incoming:** none open.

## C3 done (31 Oct, about 22:05 MYT)

**New files:**

| File | SHA256 |
|---|---|
| `scripts/package_clue_v2_results.py` | `d234b8f87799c19057d0ec6490fd8e451ae7be6a1aae08faf0e81e6a8b25d925` |
| `scripts/tests/test_clue_v2_result_package.py` (9 tests) | `7232fe06fba07e7ee2582c5eca6c23882949896faa5e1f311a16a42adaf5549d` |

**What it does:**
- Reads one evaluation output directory.
- Refuses to package unless the output is `reserved_evaluation_completed`, unactivated and bound to
  the given release SHA256.
- Recomputes the full summary with the evaluator's own `ev.summarise` from the scored rows, and
  requires an exact match with `evaluation.json` plus per-family generation counts.
- Writes `report.md`, `metrics.csv` and `roc-pr-<family>.png` (common evaluation), plus a manifest
  with input and output SHA256 values.
- Outputs are aggregate only, with no account keys. Unavailable cells are written as
  `unavailable`, and exclusions are shown as exclusions, not as negatives.

**Verification:**
- The module is not in `EVALUATOR_SOURCES`; the release source hashes still match
  (`reserved-release-v1.json` SHA256 unchanged).
- Tested on synthetic evaluator-shaped output only. Full suite: **645 passed, 1 skipped**.

**C4 follow-on command (16 or 17 Nov, after `evaluate`):**

```bash
python scripts/package_clue_v2_results.py --evaluation data/processed/clue-ae-v2/reserved-evaluation-v1 --release-sha a84e67afe73bbb960080904943e81d8185e89541beb31dd5d57c0053c4bcee01 --out data/processed/clue-ae-v2/reserved-evaluation-v1-package
```

## Post-V3 refresh (1 Nov, 00:53 MYT)

**Changes:**
- receipt provenance now hashes the V3-shared policy dependencies;
- zero-event persona gap days now get an unscored receipt.

**Files:**

| File | SHA256 |
|---|---|
| `scripts/live_receipts_clue_v2.py` | `2e186bfd105e067347a56d1da11e5d468d9b6d50ab2335566e000bca752593ff` |
| `scripts/tests/test_live_receipts_clue_v2.py` (6 tests) | `a2a5df5fd1e276e801fee17ca416617acff78d8ae933b645aef1484feca2daa2` |

**Fresh run:** `data/processed/clue-ae-v2/live-receipts-20261101-005313`
- manifest SHA256 `df5a033c46a3f91fdd5d48da59354457f182031bda4932fa1ad4c66ccd62193c`;
- receipts SHA256 `43c892e5bd8dd99f48c1fdee816ac768479a6a1df6024714b8a5d9207bfd7abc`;
- live store and ledger unchanged.

**Tests:** 663 passed, 1 skipped.

## C8 done (1 Nov 2026)

Read-only review of the installed AWS V3 code: `reviews/C8_AWS_V3_REVIEW_CLAUDE_2026-11-01.md`.

**Verdict:** no blockers.

**Findings:**
- **F1:** gate fragility. 1, 7, 8 and 9 Nov are mandatory for all six roles, with every planned
  action verified.
- **F2:** duplicated case dates in `local_pilot.py:200`.
- **F3:** label the expected no-go failures on 14–15 Nov.
- **F4:** the `%ct` commit-time check is a documented limitation.
- **F5:** question for Codex about the tick interval versus the 15-minute grace.

**New test file:** `scripts/tests/test_aws_v3_independent_review.py`, 7 tests, SHA256 `5f690b47ae9f9ab979e5df4151ff966340135c6b035d16fce0f20dc9fd5dbdfb`.

## C9 + C10 done (1 Nov 2026, 02:23 MYT)

**C9:** receipt schema v2, with `expanding_history_days`, `rolling_window_days` and
`feature_history_scope`. The change is additive and checked against the history state.

| File | SHA256 |
|---|---|
| `scripts/live_receipts_clue_v2.py` | `b2da70b00c6f3b4f9ebe888b4378cc24f5b569cc086c140633aa0557d5b40f40` |
| `scripts/tests/test_live_receipts_clue_v2.py` (7 tests) | `3c623ab2a9560b25dfb54337175660d0b23b84479e88a24429ed4b40a2791ab9` |

**C10:** fresh run `data/processed/clue-ae-v2/live-receipts-20261101-022339`.
- Manifest SHA256 `6b48c76713163f5c613cd3e2c079a71b863aef9e4a337d3b0d961060aca864f6`.
- Receipts SHA256 `6c204b32910fbda9346c4987dfee3634f15e27cb6423ab0d49a478dfce44ebd0`.
- 63 receipts, 0 scored. Store and ledger unchanged.

**Tests:** 696 passed, 1 skipped.

**Remaining ready work:** none.

## C11 done (1 Nov 2026)

Producer→consumer round-trip tests: `scripts/tests/test_c11_receipt_consumer_roundtrip.py`, 28 tests,
SHA256 `bb30ff69e191428fc865a7871dd8c82e9ba6775bf93e494fa53c921877335f85`.
- The real v2 artifact loads in live mode.
- Review: `reviews/C11_RECEIPT_CONSUMER_REVIEW_CLAUDE_2026-11-01.md`. No consumer defects.
- **F1:** the raw AWS account ID in `key.scope` must be masked in the UI.
- **F2:** a scheduled receipt job is needed for live display (48 h freshness limit).
- C7 waits for persona eligibility (5 accepted V3 days; earliest about 6 Nov if every day is
  complete).
- C4, C3-final and C5 run on 16–17 Nov. The reminder tasks are scheduled.

## Next ready task

There is no further ready Claude item before the date gates. C7 waits for eligible persona days,
and C4 waits for 16–17 Nov.

Optional overflow: new test files for a Codex-declared V3 or adapter interface, once Codex
publishes one.

## Blocked or deferred

- **C7:** waits for 5 accepted V3 fitting days per persona; earliest about 6–8 Nov.
- **C4:** 16–17 Nov.
- **C5:** after C4.
- **User actions:**
  - laptop plugged in, awake and online 08:00–20:00 MYT, 1–15 Nov;
  - commit bound sources before 10 Nov 00:00 MYT.

## 4 Nov 2026, about 00:20 MYT: status and evaluation plan

**Evaluation plan:** `specs/EVALUATION_PLAN.md` was written and agreed with the user.
- A1 is W33; A2 is the AWS V3 case study; A3 is the live diagnostics.
- B1 contains 12 acceptance tests. B2 covers pipeline quality, B3 SME practicality, B4 engineering
  evidence and B5 an optional expert walkthrough.
- Section C is the report evidence table.

**Read-only status checks:**
- **AWS V3:** 1–3 Nov, all 18 persona role-days are usable (100% verified), including mandatory
  day 1 Nov.
- **Wi-Fi:** the KSPJ profile is now "Connect automatically" (fix applied by the user).
- **GitHub and Cloudflare are flowing again,** with newest events on 3 Nov.
- **Collecting backend:** 8013 is up and the newest ingest is current. The
  `Argus-Diagnostic-Refresh` daily task now exists, which addresses C11 F2 (Codex).

**Blocked: judge-style walkthrough.**
- Both dashboard frontends, 3000 (main) and 3011/8015 (preview), were not responding.
- Claude did not start them, because they are Codex-owned and carry a case-writer conflict risk.
- Also for Codex X3: `Argus-Cloudflare-Machine-Pilot` last result was 1 (failure) at
  11-04 00:14.

## 4–5 Nov 2026

**Collection, 4 Nov:** all planned actions verified.
- AWS 17/17.
- GitHub 3/3.
- Cloudflare 6/6.

**Notes for Codex:**
- `reviews/CF_PILOT_STICKY_ATTENTION_CLAUDE_2026-11-04.md`: the Cloudflare task's result of 1 is
  permanent, caused by 5 old `claimed_unknown` rows.
- `reviews/DASHBOARD_WALKTHROUGH_CLAUDE_2026-11-04.md`: judge-style walkthrough with an addendum.
  - D1: the dashboard showed a stale copy.
  - D2: privacy leaks.

**B1 script:**
- `scripts/b1_acceptance_check.py` automates B1.1, B1.9, B1.10 and B1.11; the rest are listed as
  manual steps.
- Tests: `scripts/tests/test_b1_acceptance_check.py`, 8 tests.
- Full suite: 741 passed, 1 skipped.
- Current result on 8015: B1.9 fails with 18 display leaks (Codex D2).

**Reminder tasks:**
- `argus-collection-evening-check-2026-11-04`;
- `argus-mandatory-day-reminder-2026-11-07`, at 07:30 MYT.

**Next:**
- C7, once personas have 5 accepted days.
- Rerun B1 after the Codex fixes.
- C4 on 16–17 Nov.

**5 Nov correction:**
- D2 was withdrawn: Presentation mode masks everything; Claude's walkthrough had it off.
- D4 was already fixed.
- B1.9 now uses the frontend `maskText` through node and passes. Tests: 10. Suite: 743 passed,
  1 skipped.
- No `workspace_next` code was changed.

## 5 Nov 2026: panel-readiness work (user approved taking over Codex UI items for now)

**Pack:** `docs/PANEL_READINESS_2026-11-05.md` covers:
- the demo script;
- the glossary;
- prepared answers to 9 panel attacks;
- the headline slide template;
- item status.

**Display-only triage and MYT context (items #3 and #4):**
- Changed: `workspace_next/finding_context.py`, `queries.py`, `case_api.py`,
  `frontend/pages/workspace.js`.
- `app.py`: the CORS origin can now be overridden with `ARGUS_WORKSPACE_UI_ORIGIN`. The default
  is unchanged.
- `backend/` is untouched.
- Result: 52 recorded-High alerts → 5 review first, 31 on automation accounts, 16 inside office
  hours.

**Verification:**
- Side preview: API 8016 and UI 3012, on a private DB copy at
  `data/live/claude-side-preview-20261105`.
- The main preview (3011/8015) is not redeployed; that needs user approval and should happen
  outside collection hours.
- Tests: `scripts/tests/test_finding_triage.py`. Full suite: 745 passed, 1 skipped.

**Latency caveat:** the quick latency query gave an AWS median of 0.1 min, which is implausible.
The events `timestamp` is probably not the provider event time. Measure properly in B2.

**Still to do:**
- #2: verify model scores appear in the UI after personas reach 5 days (about 7–8 Nov).
- #6: fill the slide after C4.

## 5 Nov 2026, late morning: B2 latency and more B1 automation

**Latency, measured** (provider event → stored, verified test actions 1–5 Nov):

| Source | Median | p95 | Max | n |
|---|---|---|---|---|
| AWS | 4.8 min | 4.9 min | 9.9 min | 74 |
| Cloudflare | 5.0 min | 5.1 min | — | 25 |
| GitHub | 0.1 min | — | 15 min | 16 |

- GitHub is near zero because its pilot collects straight after acting.
- The earlier 0.1-min AWS figure came from the collector's own `GetCallerIdentity`/`AssumeRole`
  calls, about 70% of AWS events.

**B1 script:**
- New `--copy-writes` mode for B1.6 and B1.7. It refuses port 8015 and any non-isolated API.
- Both PASS on the 8016 copy.
- Tests: 12 in the file. Full suite: 747 passed, 1 skipped.

**B1.3:** 0 duplicates; a unique index on (source, `source_account_id`, `event_id`).
