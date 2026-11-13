# Argus POC — current working path and remaining gates

1 November 2026, verified about 03:01 MYT. Research replay navigation is deferred
at the user's request; detection readiness and investigation are the priority.

## Working now

In the **isolated POC preview** at `http://127.0.0.1:3011/workspace`:

1. Open a finding. Its account identity comes from the native account directory.
2. Expand **Account-day diagnostic context** and select a closed MYT day. When
   an actual triggering timestamp is known, that day is preselected; the UI does
   not invent a trigger relationship from the finding's creation date.
3. Review the real saved coverage/history reason. Current insufficient history
   stays unscored; no zero/Low result is fabricated.
4. Create a case with an explicit reason and related account context.
5. Inspect an event in its timeline. Review the account-day context, enter an
   analyst/reason, and **Retain diagnostic context**.
6. The case retains a server-validated immutable snapshot and artifact hash.
   Outdated case versions or artifacts are refused. A diagnostic is account-day
   context, not automatic attribution to a particular event or proof of compromise.
7. Record notes and an investigator decision. Closing the case preserves its
   context/audit history and does not silently change the linked finding status.

The Entities account inspection panel exposes the same readiness view. Provider
account scopes are masked in displayed diagnostic snapshots and audit detail;
their exact values remain in the retained provenance used for verification.

## Actual readiness, not a detection claim

At the operational check, collection was healthy and source pins passed.
The two personas with one accepted prior closed day were persona-02 and persona-04;
the other four had none. CLUE v2 requires five usable prior active days, plus a
compatible/quality-qualified day being scored. This is distinct from the AWS
study's all-six-roles and seven-day-span gates.

The current refreshed artifact contains **63 receipts and 0 scored receipts**.
It is a genuine explanation of available input, not successful attack detection.
No live score tier, alert activation, model training or reserved evaluation was
enabled/performed in this work.

## Automatic refresh

- Task: **Argus-Diagnostic-Refresh**.
- Daily trigger: **08:25 MYT**, after the existing 08:15 daily check. Tasks are
  separately scheduled; ordering is not a dependency guarantee if one runs late.
- Finite expiry: **17 November 00:00 MYT**, matching the current pilot period.
- Runs only while the laptop/session permits; it does not wake the laptop.
- Uses existing closed observations and the approved frozen B/C artifacts.
  No provider calls, new workload activity, retraining, threshold adjustment or
  reserved CLUE test access. Eligible future raw diagnostics can be computed,
  but actual score display remains separately gated.
- Exact source pins, approved model/provenance bindings and one-run-at-a-time
  protection. A source change requires reviewed config/pin updates.
- Writes fresh versioned artifacts; validates them before atomically publishing
  the local pointer. The POC API reads pointer changes without restarting.
- A failure before publication preserves the previous pointer/artifact and
  records an attempt report. A crash lock requires operator review.

Private state:

```text
data/live/diagnostic-refresh-v1/config.json
data/live/diagnostic-refresh-v1/last_success.json
data/live/diagnostic-refresh-v1/last_attempt.json
data/processed/clue-ae-v2/daily-live-receipts/run-*/
data/live/workspace-case-preview-20261030-v1/diagnostic-receipts-config.json
```

Commissioning run: 63 receipts, 0 scores, 0 provider calls, activation unchanged.
Manifest SHA256:
`44891bebf6ec764e0070796fd7cd27e70d760e04b6186455d2ffa956756f2253`.

This finite job does not extend GitHub/Cloudflare workloads or provide a
competition-day runtime. The separate freshness/runtime decision still applies.

## Verification

- **79 targeted tests passed**: case lifecycle/query behavior, diagnostic retention,
  artifact-pointer refresh, consumer validation, scheduled-worker behavior and
  Claude's 28 independent producer/consumer round-trip cases.
- Browser workflow passed using real saved readiness and a labelled verification
  case **only in the copied database**. No fabricated native events/model scores.
- Browser verified provider-scope masking in the retained context; display-only
  privacy regression also passed.
- Previous POC build and copied database were backed up before verification.
- Collecting backend health/pins passed afterwards. All 18 AWS study source hashes
  and the frozen W33 release-file hash remain unchanged.

Evidence files: `reviews/POC_OPERATIONAL_CHECK_2026-11-01.json`,
`data/live/poc-workflow-ui-20261101.json`, `data/live/poc-final-tests-20261101.txt`.
Test totals are from this run, not a claimed full-suite total.

## Remaining main-path work

1. Keep real collection working; inspect mandatory AWS gate days promptly. Do not
   backfill or restart the study to manufacture coverage.
2. When actual history qualifies, verify a real account-day AE score, feature
   contributions and evidence provenance through the same pipeline. Raw score
   availability is not proof of detection quality. Experimental display requires
   its existing review/approval boundary; unsupported inputs remain unscored.
3. Finish/rehearse the controlled live workspace writer switch. **The case POC
   still uses a copied event/case database**, not the collecting application's
   active writer. Its readiness artifact is refreshed from the actual pilot.
4. Evaluate the unchanged frozen scenarios at their permitted dates and report
   results against the baseline, including misses and unavailable slots.
5. Prepare a competition runtime independently of pilot expiry and review the
   privacy/access limitations before any external deployment.

The local analyst label remains user-supplied, not authenticated enterprise
identity. This is a local POC; no claim of production deployment is made.
