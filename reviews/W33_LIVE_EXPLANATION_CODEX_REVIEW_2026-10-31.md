# Codex review: W33 live compatibility and explanations

31 October 2026. Review of `docs/CLUE_AE_V2_LIVE_COMPATIBILITY.md`,
`scripts/audit_clue_v2_live.py`, `scripts/explain_clue_v2.py`, their nine tests,
the frozen v2 history/transform, and native GitHub activity projection.

## Verdict

The direction is correct and useful: a CLUE-trained model can be exercised on
compatible native live account-days without activating alerts. The **nine new
tests passed independently**. Codex has not independently rerun the claimed full
612-test suite. No trained model was fitted, released or run on additional real
data during this review, and no reserved window was accessed.

Fix the three reproduced issues below before wiring generated explanations into
the evidence drawer. Preserve the frozen W33 model/extractor/evaluator and study
results; fixes belong in these new diagnostic/explanation modules and their tests.

## 1. Cutoff comparison must use UTC instants, not unnormalized SQL text

Location: `audit_clue_v2_live.py:151–158`.

`audit(at=...)` accepts any aware datetime, but passes `at.isoformat()` directly
to `WHERE ingested_at<=?`. With a MYT cutoff of 31 Oct 12:00 (+08), the intended
UTC cutoff is 04:00. A synthetic row ingested at 05:00 UTC is nevertheless included
because `05:00+00` sorts before `12:00+08` as text.

Reproduced result: expected zero snapshot rows; actual one. The default UTC CLI
run is not proven wrong by this probe, but the supported function input is unsafe.

Required: reject naive cutoffs immediately, normalize aware cutoffs to UTC, and
compare/validate ingestion timestamps as instants (or enforce a canonical UTC
storage representation explicitly). Add regression cases for offset/Z timestamps,
future ingestion and malformed ingestion times. Keep exclusions visible. Do not
load a future-ingested row merely because its event day is closed.

## 2. Enforce one start-of-day snapshot for both score and explanation

Location: `explain_clue_v2.py:108` and `behaviour_facts`.

`explain(snapshot,state,day,bundle)` accepts a state already advanced with today's
events. Synthetic reproduction: the snapshot reports one new action, but after
an accidental `commit_original(day)` the explainer accepts the state, omits the
new-action fact and says zero of one resources are new. It also describes seven
prior days where the score used six. No error is raised.

Required: validate identity, chronology and equality with the supplied frozen
snapshot before generating facts. An isolated History instance referencing the
given start-of-day state can recompute `snapshot(day)` without mutation; reject
different features/status/prior counts or a committed/future state. An immutable
explanation-context object is another option. Include an explicit post-commit
regression test. Call explanation **before** committing the original day.

For future per-day UI receipts, retain the complete source/scope/account/day key;
`snapshots()` currently drops scope from its output, which is insufficient as an
explicit dashboard evidence binding even though History itself uses scoped keys.

## 3. The 5% hour convention can produce a misleading narrative

Location: `explain_clue_v2.py:80`.

Synthetic account history: one event every hour on each of six prior days.
Today is identical. Frozen hour-profile JS distance is **0.0**, but every prior
hour has 4.17% share, so the >=5% set is empty. Current output says:

> 24 of 24 events fell outside this account's usual hours (none established UTC).

This is not a detector error; it is an explanation convention that sounds like
an unusual-time finding even for identical distributions.

Required: preserve detector features; when no hours meet the convention, state
that a concentrated usual-hours set cannot be established and do not imply all
activity is anomalous. Expose the 5% convention explicitly and distinguish it
from the frozen reference-hours feature and the separate rarity-rule UTC window.
Add a uniform-history test.

## Other required wording/data-quality corrections

- Change “never seen for this account before” to “not observed in the available
  prior usable history.” History excludes invalid days and begins at collection/
  warm-up; it does not establish lifetime novelty.
- `Counter.most_common(1)` need not be a majority. Use “largest action share,”
  handle ties deterministically and avoid “mostly” for e.g. 20% plurality.
- `|z| > 4` is **large standardized magnitude**, not necessarily outside the
  observed CLUE fitting range. Rename the report/decision wording or compute the
  actual fitting min/max. It remains descriptive, not a tuning/gating statistic.
- Explicitly distinguish **projection-valid observed days** from complete normal
  days. A semantically usable v2 day may have missed scheduled activity. It does
  not repair the AWS study's 90%-coverage/seven-day gates. Five such days permit
  mechanical input construction; they do not prove a reliable baseline.
- Infrastructure, service roles and bots remain legitimate security entities.
  Say “unsupported by this feature contract,” not “not behaviour subjects.”
- 3–4 Nov is a conditional earliest forecast, not a commitment. Need five usable
  *prior active* days plus the next closed day, subject to retained history,
  source compatibility and collection gaps. Report exclusions per account.
- Contributions are squared residuals in transformed/scaled feature space.
  Their **mean** is raw MSE; an additive term is residual/dimension. Shares are
  shares of reconstruction error, not compromise probabilities or causal SHAP
  effects. Consider exposing additive terms explicitly to avoid UI ambiguity.

## GitHub compatibility

Confirmed: W34 repository-activity records use native metadata
`evidence_format=github_repository_activity_v1` and `activity_type=push`; their
display action is “Repository push”. W23 `github_kind()` rejects this label.
This is an expected unsupported live projection, not failed collection.

Do not edit the frozen W23 map or rename stored events to PushEvent. Codex's
integration path should use a separately versioned live adapter that checks the
explicit evidence format and native activity type, documents the chosen action
semantics, preserves native references and tests parity where justified. Unknown
activity types must remain unsupported. No retroactive W33 benchmark change,
double ingestion, or silent transfer-validation claim is allowed.

## Dashboard contract and next step

The current audit report is provider-level aggregates, not an evidence-bound
per-account/day explanation feed. A safe UI integration needs a versioned receipt
including full scoped account/day key, model/scaler/profile/source hashes,
start-of-day history provenance, transformed-feature definitions, raw score,
per-feature additive/share values, facts, input/coverage status and generation
cutoff. Attach it to the matching account-day diagnostic, not as the asserted
cause of a legacy rule finding merely sharing the account.

Display: **experimental model diagnostic — not validated for this live source**.
Do not translate CLUE cutoffs into live High/Medium/Low or trigger alerts. Live
activation still requires the user's explicit go-ahead and the agreed validation
checks. Research replay outputs remain separate and use reserved results only
after the single allowed evaluation.

Claude owns fixes to the two offline diagnostic/explanation modules and W33 result
packaging. Codex owns the subsequent reviewed live adapter/UI integration.

Synthetic reproduction receipts (private, ignored):
`data/live/w33-live-review-20261031/explanation-probes.json` and
`cutoff-probe.json`. They contain no real dataset/test-window access or additional
real-model inference. Frozen modules, artifacts and live records were unchanged.
