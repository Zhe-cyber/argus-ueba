# Frozen CLUE candidate review and account-switch protocol

27 October 2026. This protocol is committed before executing any account-switch
scenario. The user's Colab bundle was verified against model/scaler hashes,
manifest/report/dataset bindings, feature code and the pinned training source.
The supplied Downloads directory is unchanged; a verified copy and private
diagnostics are stored under ignored data/processed/clue-v1.

Local CPU inference reproduces the supplied normal holdout classifications.
One alert is dominated by permission/sharing reconstruction residuals; the other
is close to the threshold with varied login/action activity. They retain the
publisher-declared normal labels. Residual components are numerical diagnostics,
not faithful SHAP attributions or proven causes of compromise. The model and
threshold are unchanged; viewing this normal holdout cannot justify tuning it
and later claiming the same holdout remained untouched.

## Frozen inputs

Profile: clue_behavior_v1, ten inputs. Dataset SHA256:
`c151ccd687f09175ee06f827168525c31a28cd000df0a67a8cda9a1ed187c4f3`.
Model SHA256:
`08fd72f988e1f30aaf49969dce9577d17276bd54e0cc06cc402ad21599d2cf44`.
Threshold: raw reconstruction MSE strictly greater than 0.7648530006408691.
The normal-only calibration threshold, scaler, transform and weights stay frozen.

The private account_switch_plan.json SHA256 is:
`dd6835887e05356971a5985d962fd1c7d44fd619a1e596b475759d32aabe1892`.
Its actual pseudonymous pair IDs remain private. This public digest binds the
plan before execution; it does not authenticate the source as independently
benign or turn local files into tamper-proof evidence.

## Predetermined scenario selection

Use the existing fitting-selected population. Compute each identity's median
fitting-period vector after log1p and the already train-fitted StandardScaler.
Order all unordered identity pairs by Euclidean distance. Keep the middle
20%-80% rank interval, shuffle with Python Random(42), and greedily select three
disjoint pairs. Fitting profiles, not held-out scores, novelty, alert identities
or future activity, determine the pairs. Moderate-distance selection is a
specific scenario design, not representative sampling of all account takeovers.

Run each pair as a separate reciprocal identity-switch experiment from
5 August 2017 through 9 August 2017. Preserve unswitched normal controls. The
same control days recur across scenarios; never count those copies as independent
observations or use them to narrow uncertainty intervals.

## Required execution method (not yet executed)

1. Verify the saved plan/model/dataset hashes before reading native prefix events.
2. Preserve original IDs, timestamps and source bytes. In the offline analytical
   projection only, reassign the two selected named identities after the fixed
   switch date. Never modify the source prefix or send these projected records
   to live cloud ingestion. These are simulated assignments, not native evidence
   of credential theft, intruders or provider account compromise.
3. Rebuild day-level features and strictly prior-day action history using the
   frozen clue_behavior_v1 code. Swapping precomputed vectors would incorrectly
   retain another identity's history-dependent new_action_count.
4. Keep case/pair labels, switch times and affected identity mappings outside
   the ten-feature model inputs. Apply the frozen model/scaler/threshold once.
5. Report per-case, per-account and per-active-day detections/misses, normal
   control alerts, missing activity and any detection delay. Attack recall, if
   reported later, refers only to these explicitly simulated affected windows;
   it is not real-world attack effectiveness or enterprise accuracy.
6. Retain failures and zero detections. Do not change pair selection, switch
   timing, threshold or model after observing outcomes and call the rerun an
   independent evaluation. A future revised model needs a new evaluation period.

## Expected limitation

The current AE is a population model, not an identity-conditioned model of
personal volume/resource preferences. A reciprocal switch can preserve most
numeric features, with only history-dependent novelty changing. A routine that
is normal for another fitted identity may remain inside the learned population.
The experiment explicitly tests this limitation; detection is not guaranteed.
Identity linking and source-aware personal baselines remain separate work.

scripts/inspect_clue_candidate.py reproduces diagnostics and generates the fixed
plan only. No account-switch, model fitting, threshold change, live activation,
AWS/CERT artifact replacement or production deployment occurs in this slice.
