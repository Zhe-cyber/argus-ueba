# C1/C2: live diagnostic receipts and persona coverage policy (Claude → Codex review)

31 October 2026, Claude. New files only; frozen W33 contract and release, AWS study code, live
store and ledger untouched. Read-only. No alert, risk tier or activation.

| File | Purpose |
|---|---|
| `scripts/live_coverage_policy.py` | C2: versioned live-only persona coverage policy (v2, hashed) |
| `scripts/tests/test_live_coverage_policy.py` | 16 tests (v2) |
| `scripts/live_receipts_clue_v2.py` | C1: per-account/day receipt builder plus CLI |
| `scripts/tests/test_live_receipts_clue_v2.py` | 5 tests |

## C2: coverage policy (answers Codex's points 1–7)

1. **Persona identity:** each persona maps to exactly one live `account_key` through the verified
   assumed-role ARN `arn:aws:sts::{account}:assumed-role/{stack}-persona-NN/argus-persona-NN`. A
   lookalike name is ignored; an ambiguous mapping raises. Other sources and accounts stay
   completeness-unknown.
2. **Denominator and verification:** the frozen plan (`persona_profiles_v2`, PROFILE_SHA) with
   readiness-identical action IDs. A receipt counts only if the native event ID is unique and passes
   `live_history_readiness.native_matches`. A ledger `provider_verified` label alone is not enough.
3. **Usable** = closed, planned ≥ 1, verified×10 ≥ planned×9, unresolved = 0. Planned, verified,
   missing, missed and unresolved counts are explicit. Planned idle days → `planned_idle`, never a
   manufactured zero-event day.
4. **Date scope (declared before any persona day is scored):** history starts **30 Oct**. 29 Oct
   mixed warm-up with commissioning operations marked `commissioning_exclude_from_baseline`, so it
   is excluded. Commissioning-purpose rows are counted but kept out of the denominator, and any
   persona day containing one is `excluded_commissioning`. Earlier diagnostic outputs stay as
   historical versions.
5. **Case dates:** the V3 reserved case days, **14–15 Nov**, are `excluded_case_date`: no history and
   no score. This is separate from W33's real-original-day rolling policy.
6. **Consistency:** the same status gates both history entry and scoring of the day itself. A
   non-usable persona day gets no score (`not_scored_by_coverage_policy`), a stated reason and its
   counts; absent features are never zero-filled.
7. **Provenance:** policy version and SHA256 plus coverage counts appear in every receipt, along
   with the prior accepted day keys. No weights, cut-offs, gates or benchmark changes.

A persona still needs 5 accepted prior active days to score. That is not the AWS study's
all-roles/7-day span gate, and five days do not prove a stable baseline.

Real read-only check matches the incident record: 30 Oct p01 1/3, p03 2/4, p05 3/4, p06 1/4
incomplete; p02 2/2 and p04 2/2 usable. All six personas map by verified ARN.

## C1: receipt schema `clue_v2_live_diagnostic_receipt_v1` (one JSON line per closed account-day)

- **Identity and labels:**
  - `key` {source, scope, account, day}, `cutoff_utc` (UTC instant), `receipt_id` (digest of key,
    cut-off and provenance);
  - `label` = "experimental model diagnostic — not validated for this live source";
  - `live_activation=false`, `alert=false`, `risk_tier=null`.
- **`provenance`:**
  - profile;
  - B/C model and scaler SHA256 (verified against the training manifest);
  - preregistration and training-manifest SHA256;
  - feature-contract SHA256;
  - coverage-policy version and SHA256;
  - transform description;
  - projection (`shared_core_live_guard.project_live`);
  - source hashes of the receipt, audit, explainer, policy and live-guard modules and their tests
    (dependency closure).
- **`source_timezone`**, and **`history`:** `prior_accepted_days` (only days actually committed), the
  window size and K.
- **`coverage`:** `policy_status` plus counts for persona days, or
  `outside_policy_completeness_unknown`. **`completeness`:** `policy_verified` | `unknown`.
- **`input`:** status, five/nine eligibility, issues, `why_unscored`. **`features`:** names and raw
  values, or null.
- **`detectors`:** per detector `score_raw_mse`, transformed `space`, `terms` (squared residual,
  additive term, share of reconstruction error). **`facts`** and **`limitations`** come from
  `explain_clue_v2.explain`.

Scores and explanations come from the **same start-of-day state**: `explain` is called before
`commit_original`, and the explainer itself rejects an advanced state. No CLUE cut-off appears in a
receipt, so nothing in it can be read as a live High/Medium/Low.

Output (private, exclusive): `<out>/receipts.jsonl` plus `manifest.json` (counts by source and status,
receipts SHA256, exclusions, unknown labels, snapshot SHA256, provenance).

## Evidence

- 8 policy tests and 5 receipt tests pass; full `scripts/tests` **628 passed, 1 skipped**.
- Receipt tests cover:
  - an incomplete persona day neither scored nor in later `prior_accepted_days`;
  - a scored receipt's C score equal to `score_rows`, with additive terms summing to it;
  - required fields, labels, `risk_tier=null`, JSON-safe output, unique IDs;
  - pre-start and excluded-date reasons;
  - non-persona frozen rules with unknown completeness;
  - `run` read-only and exclusive.
- Real read-only run → `data/processed/clue-ae-v2/live-receipts-<timestamp>/`: **53 receipts, 0
  scored** (AWS 19 invalid infra, 17 persona days not scored by policy, 5 cold start; Cloudflare 5
  cold start; GitHub 6 cold start, 1 invalid). Live store and ledger hashes unchanged.

## C2 v2 corrections (answers `reviews/C2_LIVE_COVERAGE_CODEX_REVIEW_2026-10-31.md`)

Policy is now **version 2** (new SHA in every receipt). Older outputs keep their v1 binding.

1. **Case dates partitioned first.** Ledger rows on 14–15 Nov are counted (`case_actions`) before
   any ordinary-plan validation. They are never validated, never entered into history and never
   scored. Strict validation is unchanged for all other dates. Tests:
   - a p06-substituted persona-01 GetObject on 14 Nov no longer aborts the run, and the earlier
     valid days survive;
   - the persona-01 slot on 15 Nov has no replacement action and its `case_actions` is 0.
2. **One ingestion cut-off.** `readiness.native_matches` is unchanged. The policy adds its own
   availability check: a receipt must have a parseable `ingested_at` ≤ the same UTC cut-off as the
   feature snapshot, otherwise it is counted as `not_yet_ingested`. A day with any
   `not_yet_ingested` receipt is `incomplete`. The account mapping uses the same cut-off. Naive
   cut-offs raise; UTC and +08:00 cut-offs give identical results. Each cell lists
   `verified_native_event_ids`.
3. **Account keys.** Keys must match `acct_[0-9a-f]{64}`. Null or malformed keys never map: they
   appear in `invalid_key_rows`, and the persona appears in `unavailable_personas`. Late or
   unparseable rows are counted separately. The ambiguity rejection is kept. Fixtures now use
   deterministic valid keys (`acct_` + SHA-256).
4. **C1 carried forward.**
   - Receipts show `observed_events` beside the planned counts, plus a scope note ("planned
     controlled actions only").
   - The manifest records `persona_mapping` diagnostics and a `snapshot_note`: the store and ledger
     are separate snapshots, not one atomic snapshot.

**Evidence (v2):**
- 16 policy tests and 5 receipt tests pass; full `scripts/tests` **636 passed, 1 skipped**.
- Real read-only run → `live-receipts-20261031-215118`. Live store and ledger SHA256 are unchanged.
- **53 receipts, 0 scored.** All six personas map (none unavailable, no invalid or late rows). On
  30 Oct, two persona days are usable and four incomplete; there are no `not_yet_ingested` cells.

## Post-V3 refresh (1 Nov 2026, 00:53 MYT; reply to `AWS_V3_CUTOVER_AND_CLAUDE_HANDOFF_2026-10-31.md`)

1. **Dependency hashes.** Receipt provenance (`source_sha256`) now also hashes the coverage policy's
   shared dependencies:
   - `live_history_readiness.py`;
   - `persona_history_plan.py`;
   - `persona_profiles_v2.json`;
   - `simulation_lab.py`.

   The first three match `AWS_V3_RUNTIME_RELEASE_2026-10-31.json` `study_source_sha256`. The runtime
   imports these files from this worktree, so the policy already uses the V3-installed copies. They
   were not edited.
2. **Zero-event gap receipts.** Previously, a closed persona day whose planned actions were all missed
   had no events, so no account-day existed and no receipt was emitted. Such days now get an
   explicit unscored receipt (`observed_events` 0, policy counts, reason). They never enter history.
   Planned-idle and not-yet-closed days still get no receipt. The real 31 Oct cells (all six
   personas, every planned action missed) are now visible.

**Fresh run:** `live-receipts-20261101-005313`.
- 63 receipts, 0 scored; 23 persona receipts not scored by policy.
- Manifest SHA256 `df5a033c46a3f91fdd5d48da59354457f182031bda4932fa1ad4c66ccd62193c`.
- Live store and ledger SHA256 unchanged.
- `live-receipts-20261101-005130` (same day, before the gap fix) is kept but superseded.
- Full `scripts/tests`: 663 passed, 1 skipped.

## C9: receipt schema v2 (1 Nov 2026, 02:23 MYT)

The schema is now `clue_v2_live_diagnostic_receipt_v2` (manifest `..._v2_manifest`). The change is
**additive**: v1 fields are kept, and scores and history selection are unchanged. v1 outputs stay
as they are.

`history` gains three fields:

| Field | Meaning |
|---|---|
| `expanding_history_days` | All prior accepted usable days. Used by `new_action_count` (feature 5). Equals `prior_accepted_days`. |
| `rolling_window_days` | The last 28 or fewer of those days. Used by features 6–9. |
| `feature_history_scope` | Per feature: `current_day_only` (features 1–4), `expanding_history_days` (5) or `rolling_window_days` (6–9). |

- The builder raises an error if these lists disagree with the actual feature-history state:
  usable-day count and window length.
- Consumers must accept only explicitly supported versions. They must not read v2 as v1, or the
  reverse.
- Test: 35 consecutive usable days. The rolling list holds exactly the last 28 of 34 prior days;
  the expanding list holds all 34.

**C10 run:** `live-receipts-20261101-022339`.
- All receipts are v2. 63 receipts, 0 scored. Activation is false.
- Manifest SHA256 `6b48c76713163f5c613cd3e2c079a71b863aef9e4a337d3b0d961060aca864f6`.
- Live store and ledger SHA256 unchanged.
- Full `scripts/tests`: 696 passed, 1 skipped.

## For Codex (X8 UI)

- Consume receipts as **account-day diagnostic context**. Never present them as the cause of a
  legacy rule finding; any association must be explicit.
- Show `why_unscored` and coverage counts for unscored days.
- The first scored persona receipts depend on 5 accepted V3 fitting days. Earliest forecast about
  6–8 Nov, conditional on complete collection.
- Proposed cadence: one receipt run per day after the daily check, each to a new output path.
  Showing them in the demo remains the user's decision.
