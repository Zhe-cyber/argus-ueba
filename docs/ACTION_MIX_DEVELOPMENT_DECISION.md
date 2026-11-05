# Action-mix follow-up: no-go

30 October 2026. The one-round decision in
[W29](../specs/W29-action-mix-development-decision.md) is complete, ahead of the
3 November deadline. **Do not advance this candidate to a fresh test or live
scoring.** The declared recall and AUROC gates failed. No alternative method,
threshold, combination or scenario was tried after seeing these scores.

The candidate reuses the unchanged W8 action-distribution reference and W10
strict calibration threshold **0.8723298381957394**. This is base-2 JS divergence
from an account's own fitting reference, not a new AE or a probability. Unseen
action categories remain in the distance calculation. No fitting, calibration,
source normalization, live scoring or historical model artifact was changed.

## Inspected development result

Use only the already inspected 5–9 August 2017 days and the original three
reciprocal switch pairs. All 191 normal and 25 switched account-days were
scorable. The comparison is to the cached original **ten-feature CLUE AE** on
these exact days, not the later five-feature reserved evaluation.

| Observation | Action-mix control | Original ten-feature AE |
|---|---:|---:|
| Normal days alerted | 4/191 (2.09%) | 2/191 (1.05%) |
| Switched days alerted | 2/25 (8.0%) | 0/25 (0%) |
| AUROC | 0.564 | 0.458 |
| Average precision | 0.155 | 0.118 |

The two action alerts occur in different pairs: switch-01 0/8, switch-02 1/9,
switch-03 1/8. Positive prevalence for AP is 25/216 (11.57%). Observations and
paired counterfactuals are dependent; no significance or independent-test
accuracy claim is made. The modest improvement over a weak comparator does
not satisfy the predeclared screening requirements of at least 5/25 switch
alerts and AUROC >=0.65. Coverage, normal <=5% and two-pair gates passed.

Earlier numeric-centre, raw novelty and context-primary failures remain
failures. W7 already tested equal-five-day resource novelty including globally
unseen resources; its normal-calibration saturation must not be rediscovered
as a new proposed fix. Action composition also cannot detect a pure volume
increase or time shift. These findings do not establish why every AE scenario
performed poorly; population conditioning and feature semantics are hypotheses,
not isolated causal conclusions.

## Provenance and limits

- Plan SHA256: `77b7feec5c5483b3620a3e78cad20993b9444e43a1a0dc0640f05f9147713f7c`.
- Private output: `data/processed/action-mix-development-decision-v1/`, with
  source/input bindings, individual pseudonymous scores and completed attempt.
- One input invocation was rejected before native access because the supplied
  export was not the frozen Colab file. The correct file matched the existing
  expected hash; no binding, method, threshold or score was changed. The
  subsequent source-bound development computation completed once.
- **33 focused tests passed**, including unchanged context/calibration tests.
  An initial run had two temporary-directory setup errors; rerunning with a
  workspace test directory resolved those environmental errors.
- Full archive and September data were not opened. The already consumed
  11–24 August reserved experiment was not rerun. No fresh evaluation claimed.

## Dashboard verification

Read-only API and headless-browser checks passed against the running local
dashboard on 30 October. The existing `/clue` replay displays real saved
**clue_behavior_v1 ten-feature AE** scores for 191 normal account-days:
185 Low, 4 Medium and 2 High review priorities. Calibration diagnostics,
filtering and reconstruction-evidence details work. Those are offline
benchmark outputs, not current AWS/Cloudflare/GitHub scores.

The live API reports **15 observed accounts, 15 unscored, zero non-null AE
scores**, model status `missing_artifacts`, and zero active model alerts.
Existing active rule/observation alerts have separate origins. The five-feature
candidate is not configured as the live model. Offline score reception and
rendering work; a validated live scoring path has not been completed. Do not
describe these checks as live model validation or enable a failed candidate to
fill the score column. Browser checks did not change live statistics or data.

## Stop decision

Close this development round. Keep collection, approved identity mappings,
cross-provider timeline and the frozen AWS study intact. The next deliverable
is provider applicability and project-scope sign-off with these limitations,
not another automatically selected model or a September test. One effective
detector across all three services remains unachieved; it must be reported
plainly rather than implied by common JSON fields or working ingestion.
