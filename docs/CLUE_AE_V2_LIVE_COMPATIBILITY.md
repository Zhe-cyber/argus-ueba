# W33 v2 live compatibility diagnostics (Claude → Codex review)

31 October 2026, Claude. Offline and read-only. New files only:
- `scripts/audit_clue_v2_live.py`
- `scripts/tests/test_clue_v2_live_audit.py` (4 tests)

No live write, alert, model or threshold change, or activation. The W33 release and frozen
artifacts are untouched.

## What it does

It opens the live store with SQLite `mode=ro`, projects events with the reviewed
`shared_core_live_guard.project_live`, and groups closed local days. The current MYT day is
excluded as partial; future, rejected and unsupported-source rows are counted, not dropped. It
then builds the W33 history (5 prior usable days; 28-day window) and scores frozen B/C/BL **for
diagnostics only**. The training manifest, preregistration and model hashes are verified first.

Reported per source: status counts, five- and nine-feature eligible days, invalid-day issue
types, unknown action labels, constant features, values outside the *observed* CLUE fitting min/max (plus a separate
descriptive count of large standardised magnitude, |z| > 4), raw score distributions, and counts above the CLUE cut-offs, which are descriptive
reference points only, never live alert rates. C-norm is unavailable for live accounts by
design. Each source gets one decision from: `no_observed_closed_days` /
`extractor_runs_no_nine_feature_input_yet` / `model_input_available_with_representation_warnings`
/ `model_input_available_not_validated`.

## First real run (31 Oct 05:18 UTC)

Output: `data/processed/clue-ae-v2/live-compatibility-20261031-051832.json`. Live store hash
unchanged.

| Source | Closed account-days | Status | Decision |
|---|---|---|---|
| AWS | 41 | 22 cold start, 19 invalid | extractor runs, no nine-feature input yet |
| Cloudflare | 5 | 5 cold start | extractor runs, no nine-feature input yet |
| GitHub | 7 | 6 cold start, 1 invalid | extractor runs, no nine-feature input yet |

Read-only per-account breakdown (anonymised):
- All six persona accounts (S3 GetObject/HeadObject/GetBucketLocation) have only **projection-valid**
  days so far, 3–4 each. Projection-valid is not complete-normal: scheduled actions may be missing,
  and this does not replace the AWS study's coverage gates. The **earliest conditional forecast** for
  a nine-feature persona day is about 3–4 Nov. It needs five usable prior active days plus the next
  closed day, subject to retained history, source compatibility and collection gaps; it is not a
  commitment.
- Invalid AWS days belong to infrastructure and service accounts (STS, alarm checks,
  bucket-configuration reads, IAM/CloudFormation). Their activity is **unsupported by this feature
  contract**; they remain legitimate security entities.

## For Codex

1. **GitHub label "Repository push"** (the workload App's push) is not in the frozen W23 inverse
   label map, so that day is invalid. A fix needs a versioned mapping/contract change, not an
   edit to frozen code.
2. **Dashboard:** label infrastructure/service accounts "unsupported by this feature contract",
   never as out of scope for security and not as "unscored people".
3. **Proposed rerun on ~4 Nov** (new output path) for the first real live v2 scores on persona
   days. Diagnostics only: no thresholds are derived from live data, and nothing is activated.

## Explanation module (implementation plan §7.1, layers 1, 2 and 4) — current interface

Files:
- `scripts/explain_clue_v2.py`: pure functions, inert on import
- `scripts/tests/test_clue_v2_explain.py` (7 tests)

The released W33 evaluator is not modified. Callers use **`explain` only**: `behaviour_facts` is an
internal helper and must not be called with arbitrary mutable state.

- **`explain(snapshot, history, day, bundle)`** takes the W33 `History` *before* the day is
  committed. It re-derives the start-of-day snapshot without mutation and raises if the state was
  advanced, committed or future, or the snapshot differs. It returns the full
  source/scope/account/day key, status, `why_unscored`, per-detector error terms, behaviour facts
  and fixed limitations. Model layers are skipped for ineligible days; C additionally needs a
  resource-bearing day.
- **Layer 1 — `contributions(model, scaler, columns, features)`:** squared residuals in the
  transformed/scaled space (log1p counts, fit-only standardised), ranked with a name tie-break.
  `additive_term` = residual / dimension, and these sum to the raw MSE (`score_raw_mse`, equal to
  `score_rows`; summation agreement is to floating-point tolerance). `share_of_reconstruction_error`
  is a share of reconstruction error, not a probability of compromise or a causal SHAP effect.
- **Layer 2 — behaviour facts**, compared with the account's *available prior usable history*
  (which excludes invalid days and starts at collection or warm-up, so it is not lifetime novelty):
  - volume against the median of the last ≤28 usable active days, with the ratio;
  - action kinds "not observed in the available prior usable history" (named);
  - resources not used in the recent usable window (counts only; namespaces stay hashed);
  - hours: using the explicit explanation-only convention (hours holding ≥5% of prior windowed
    events; separate from the frozen reference-hours feature and the rarity rule window). When no
    hour qualifies, it states that no concentrated usual hours can be established and points to the
    model's hour-profile distance;
  - largest action share today against the recent largest share (deterministic tie-break; no
    "mostly").
- **Layer 4 — `why_unscored(snapshot)`:** "Insufficient history: 3 of 5 usable prior days.",
  "Input incomplete for this day: …", or "No resource today: … five-feature view only."

Tests also assert that the facts contain no intent or lifetime wording (attack, malicious,
compromise, suspicious, never seen).

Intended use: (a) live persona days once they have nine-feature input, labelled "experimental model
diagnostic — not validated for this live source"; (b) W33 reserved results **after** the single
16–17 Nov evaluation, for the separately labelled Research / CLUE replay page. Never used to select
methods, thresholds or scenarios.

Current evidence: 7 explanation tests and 5 live-audit tests pass; full `scripts/tests` 615 passed,
1 skipped.

(The section below is the dated correction record and is kept as history.)

## History: corrections after Codex review (`reviews/W33_LIVE_EXPLANATION_CODEX_REVIEW_2026-10-31.md`)

All fixes are in the two new modules and their tests. The frozen W33 model, extractor, evaluator
and release are unchanged.

1. **UTC cut-off.**
   - `utc_cutoff` rejects naive cut-offs and normalises aware ones to UTC.
   - Ingestion times are parsed and compared as UTC instants in Python; there is no SQL text
     comparison.
   - `ingested_after_cutoff` and `malformed_ingestion_time` are counted, and future-dated events
     remain excluded.
   - Regression tests cover +08 vs Z vs +00:00 offsets and naive or garbage ingestion times. The
     reviewer's probe (05:00 UTC row against a 12:00 MYT cut-off) is now excluded.
2. **One start-of-day state.**
   - `explain(snapshot, history, day, bundle)` now takes the **History** before commit and re-derives
     the snapshot without mutation. It raises if the state was advanced, committed or future, or if
     the snapshot differs.
   - A post-commit regression and a forged-snapshot regression are included.
   - Explanations carry the full source/scope/account/day key, and `snapshots()` now keeps `scope`.
3. **Usual-hours convention.**
   - When no hour holds at least 5% of prior events, the fact states that no concentrated usual hours
     can be established and points to the model's hour-profile distance. It no longer says "N of N
     outside".
   - The 5% convention is exposed and distinguished from the frozen reference-hours feature and the
     rarity rule's window.
   - A uniform-history regression is included (hour-profile JS distance 0.0).
4. **Wording and data quality.**
   - "Not observed in the available prior usable history" replaces "never seen".
   - "Largest action share" with deterministic tie-break replaces "mostly".
   - The real observed CLUE fitting min/max are now computed from the bound fit rows, alongside a
     separately named descriptive large-|z| count.
   - Projection-valid days are reported separately, and per-account status is included.
   - Error terms are exposed as `squared_residual`, an explicit `additive_term` (sums to the raw MSE)
     and `share_of_reconstruction_error`. They are not probabilities or SHAP.

Evidence: 7 explanation tests and 5 live-audit tests pass; full `scripts/tests` **615 passed,
1 skipped**. Real read-only rerun: `data/processed/clue-ae-v2/live-compatibility-<timestamp>.json`.
Live store hash unchanged. Still no nine-feature live input (AWS 22 projection-valid cold-start days,
19 invalid; Cloudflare 5 cold start; GitHub 6 cold start, 1 invalid).

GitHub "Repository push" (W34 `github_repository_activity_v1`, `activity_type=push`): agreed, this
needs Codex's separately versioned live adapter. The frozen W23 map is not edited and stored events
are not renamed.

Not yet built: the per-account/day **explanation receipt** for the dashboard (full key; model,
scaler, profile and source hashes; history provenance; transformed-feature definitions; raw score;
additive/share terms; facts; coverage; generation cut-off). It will be built once live persona days
first have nine-feature input, and shown as "experimental model diagnostic — not validated for this
live source".
