# Live AWS AE shadow view

The live collector and real AE inference are now separate working paths. A
read-only job scores the actual connected AWS log snapshot every30 minutes while
the laptop is awake and the user is logged in. It produces `latest.json` and
`latest.html` under the private `data/live/cloud-ae-shadow-v1/` directory beside
the existing connected store, plus `last_attempt.json` for run success/failure.
Open `latest.html` locally to see the scores. This is a separate local engineering
view; the main analyst dashboard and live risk fields are unchanged.

## What the number means

Each row uses a principal's latest observed UTC date and strictly earlier
same-principal history, extracted into the frozen 12-count cloud vector. A
StandardScaler transforms it before the 12-32-16-8-16-32-12 autoencoder reconstructs
it. The raw mean squared reconstruction residual is shown, without clipping,
normalisation to a percentage, or a risk threshold. Residual feature names are
not SHAP attributions. Principal aliases are stable private-keyed HMACs; raw
identities, emails, IPs and resources are not published in the report or page.

The model is the existing legacy flaws.cloud AWS benchmark model, not the
71-feature CERT or 10-feature CLUE model. Its transfer to live data has not been
validated, and its original training extractor version is not authenticated.
Current UTC dates are partial; historical observed dates also have unverified
completeness. Setup/collector/admin activity may be included. Lack of earlier
locally observed actions does not prove an action has never occurred.

Only configured-account AWS CloudTrail rows are scored. Missing identities are
counted and excluded, never invented. Cloudflare/GitHub continue collecting, but
this view does not score or merge them. No output is a compromise probability,
confirmed malicious account, validated review priority or performance result.

## Guardrails and operations

`scripts/cloud_ae_shadow.py init` requires a fresh dedicated output directory,
existing pilot config and explicitly trusted local artifact directory. It pins
model/scaler/metrics hashes and the scorer/extractor/builder source before any
model deserialisation. `torch.load` uses `weights_only=True`. The scaler is a
trusted local pickle: do not initialise this job with downloaded or unreviewed
artifacts. Altered code or artifacts fail closed, requiring a deliberate new
release; hashes are never refreshed automatically.

Database access is SQLite `mode=ro`, `query_only`, in one consistent transaction.
No application event_store import, production URL, provider request, event write,
score-table write, model registration or activation. Snapshots above100000
scoped events fail instead of truncating history. Nonfinite values, future or
unzoned timestamps, invalid metadata and contract mismatches also fail.

`scripts/install_cloud_ae_shadow.ps1` first verifies real inference, then refuses
an existing task name. The separate `Argus-Pilot-AE-Shadow` task runs as the
current interactive user, hidden, at least privilege, every30 minutes,
IgnoreNew, no stored Windows password and no wake. It expires at midnight
15 November MY, matching the collection pilot. No collection-task restart or
source-pin refresh was needed. The job itself also checks expiry before model
or database access. Turning the laptop off stops all local refreshes.

An HTML view reloads itself every minute, but this does not launch inference.
It marks the last successful timestamp stale after60 minutes. Failed attempts
preserve last successful JSON and visibly mark the HTML as previous output;
`last_attempt.json` records the failure type without raw exception data.
Check both files before using a screenshot. Treat aliases as pseudonymous;
this private page is not automatically a public-poster artifact.

## Verification and next gate

First actual snapshot on28 October2026:2393 scoped AWS events,10 attributable
principals,4 partial-current-UTC-date windows. Raw MSE range approximately
0.0001141-0.02132. These numbers demonstrate engineering inference only.
No threshold or risk tier was applied. Local suite410 passed,1 optional PG skip.

Before review-priority activation, use the prospective V2 protocol's fitting,
validation and normal-calibration windows; freeze a compatible model/scorer and
normal-only threshold, verify coverage/history, then evaluate the reserved cases
and matched legitimate control. The method annex remains due5 November before
validation starts. Neither this shadow view nor additional collection guarantees
that detection will pass. If it fails, report that outcome and retain pipeline
and offline evidence as the signed-off deliverable.
