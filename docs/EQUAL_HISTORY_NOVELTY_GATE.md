# Equal-history resource novelty: rejected at normal calibration

28 October 2026. Method and stop rule fixed in spec commit `7eab957`, code saved
in `71e287b` before calibration. Offline development experiment only, using the
existing inspected CLUE prefix; no new native data downloaded or reserved.

## Question and method

The W6 contrast depended on account history length. This tests the reviewer's
suggestion to use exactly the last **five resource-active fitting dates** per
account and score the fraction of today's distinct paths absent from that
reference. Fit only on 13-26 July, then freeze state. Globally unseen paths
count as unfamiliar, rather than being dropped. Full-fitting global vocabulary
is used only for a separate descriptive flag and never changes the score.
No-resource days have a separate `no_resource_activity` state, without a score.

Calibrate on 1-4 August normal data at linear q99, strict `score > threshold`,
minimum six scorable rows across three accounts. The predeclared rejection
gate is a threshold of exactly one: no bounded novelty fraction can strictly
exceed it. No change to >=, reference length, alert budget or threshold after
seeing results. No per-account neural network, AE retraining or live scoring.

## Result

| Normal-calibration observation | Result |
|---|---:|
| Frozen fitting population | 55 accounts |
| Eligible five-date resource references | 49 accounts |
| Original calibration account-days | 169 |
| Scorable days | 154, across 45 accounts |
| No-resource activity days | 10 |
| Insufficient fitting-resource-history days | 5 |
| Linear q99 threshold | **1.0** |
| Days exactly at threshold | **51 / 154 (33.1%)** |
| Strict alerts | 0 |
| Predeclared gate | **Saturated: no-go** |

Among the 51 maximal-novelty normal days, 33 contain only globally unseen
resources. The other 18 contain at least one resource known somewhere in the
full fitting window, while all their paths are absent from the account's own
last-five-date reference. The latter does not establish whether the account
used them on an earlier date; no ownership or intent inference is made.

Any threshold below one would flag at least these 51 days, or 33.1% of the
scorable calibration days. At one, the strict rule can never fire. Consequently
this scalar cannot provide the intended sparse alert rule on this calibration
distribution. Zero strict alerts are a saturation failure, not successful
discrimination or evidence of a low operational false-positive rate.

**Switch scoring was not run**, as required by the stop rule. Do not report a
measured 0/25 attack result, attack recall or held-out normal performance for
this candidate. No fresh evaluation window was consumed. Existing W6/AE
artifacts and scores remain unchanged; neither detector was rerun by this gate.

## What this does and does not establish

Fixed histories remove the specific W6 history-ceiling disparity and including
new-to-everyone resources increases scoring coverage. Neither change makes raw
path unfamiliarity sufficiently selective at the fixed alert budget here.
This rejects this fixed scalar candidate, not personal baselines, unsupervised
learning or the multi-cloud normalization concept in general.

Literal novelty may still describe evidence, but should not by itself be
presented as compromise or a validated live alert trigger. Next investigate
whether stable resource context/action combinations separate accounts on the
existing development data, with explicit source semantics and coverage. Do not
lower the threshold, consume fresh data to tune away saturation, or transfer
this CLUE result/threshold to AWS, Cloudflare or GitHub. A later candidate needs
its own fixed method and fresh evaluation; success is not assumed.

## Reproduction and provenance

```powershell
$env:DATABASE_URL = 'sqlite-local'
python -m pytest scripts/tests/test_equal_history_novelty.py -q
python scripts/check_equal_history_calibration.py --original-directory EXISTING_W6_OUTPUT --prefix EXISTING_PREFIX --manifest FROZEN_MANIFEST --out data/processed/NEW_PRIVATE_DIRECTORY
```

The CLI verifies the existing W6 report, manifest, prefix and frozen source
hashes, checks 605 fitting and 169 calibration rows, and saves/reloads the new
JSON reference before calibration. All invariant checks passed. The gate reads
existing local files only; no provider calls, application-database writes,
deployment, model activation or original-artifact overwrite. No raw data or
fitted reference dictionaries enter Git.

Private output: `data/processed/clue-fixed5-calibration-gate-v2` containing
`reference.json`, `normal_calibration.json`, `calibration_gate_report.json`.
Report SHA256:
`8db793a305e274ecfa502bcf733585cac76d3c74ffb9657a6bd1b81531cd8866`.

Local regression: **347 passed, one optional PostgreSQL skip**, with
`DATABASE_URL=sqlite-local`. Checks include exact last-five selection,
fitting-only immutable state, globally unseen inclusion, separate no-resource
state, JSON reload, coverage/eligibility, strict saturation and artifact binding.
Independent Claude review of this new candidate has not been requested;
the user prefers to send review material manually. The experiment implements
their supplied review's suggestion with a predeclared normal-only rejection
gate; it does not claim Claude endorsed or inspected this implementation.
