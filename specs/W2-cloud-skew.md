# Spec: W2-cloud-skew — Fix cloud AE train/serve skew (window + dead feature)

**Branch:** `w2-cloud-skew` · **Executor:** heavy (opus) — scoring-path code · **Written:** 2026-07-03

## Goal
`_CloudAEScorer.score_user` scores users with the SAME window semantics the model was
trained on, and `new_action_count` is live in production. Then the live-path evaluation
is re-run so we know the AUROC impact.

## Non-goals
- No model retraining. No changes to cloud_feature_extractor.py feature definitions
  (frozen 12-dim contract). No CERT-AE changes. No threshold changes (that's W4).

## Files in scope
- backend/ae_scorer.py (`_CloudAEScorer.score_user` only)
- backend/tests/ (add unit tests for the new window split)
- results/ (re-run artifacts)

## Approach (planner-decided)
Training ground truth (scripts/build_cloud_dataset.py:209-233): for each user, events are
grouped by UTC calendar day; each day is scored as `aggregate_window(day_events,
history=all_events_before_that_day)`. Serving must mirror this:
1. In `score_user`: after fetching + filtering cloud events, sort by timestamp; let
   `window` = events on the LATEST UTC calendar day present; `history` = all cloud
   events strictly before that day.
2. Call `aggregate_window(window, history=history)`.
3. Remove the stale "Known train/serve gap" note from the docstring; describe the
   day-window semantics instead (cite build_cloud_dataset.py as the contract).
4. Unit tests (no model files needed — test the split logic; extract it as a small
   pure helper `_split_latest_day(events) -> (window, history)` so it's testable):
   events across 3 days → window = day-3 events only, history = days 1-2;
   single-day user → history empty; malformed timestamps skipped, not crashing.
5. Re-run, in this order, with the venv python:
   `scripts/replay_eval.py` and `scripts/cloud_kfold_inductive_eval.py`.
   Copy updated metrics into results/ (same filenames as existing). Record BOTH
   before/after numbers in the PR body.

## Acceptance checks (all must pass, runnable as written)
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q` → all pass (57 + new)
- [ ] New unit tests cover: multi-day split, single-day user, empty events
- [ ] `git diff master --stat` touches only in-scope files
- [ ] PR body contains before/after replay AUROC and the k-fold numbers
- [ ] Evaluator verdict line (IMPROVED / NO-CHANGE / REGRESSED) in PR body

## Risk notes
- LESSONS.md rules 3, 5, 8 apply (this task IS rule 3's fix; commit as soon as green).
- ml/models/cloud_ae_v1.pt + scaler must exist locally for the eval re-runs; if absent,
  run the unit-test portion, mark eval checks "blocked: model files missing" and report —
  do NOT fake numbers.
- Scores will shift for cloud users (window semantics corrected). Do not "compensate"
  by touching thresholds or the scaler — report the shift.
- replay_eval.py may take a while; state expected runtime, don't kill it midway.

## Escalation triggers
- aggregate_window's signature/behaviour differs from the training call in any way
  not covered here → stop, report (planner must re-check).
- Live AUROC drops >0.02 after the fix → stop, report with numbers (do not merge a
  regression silently; the planner arbitrates).
