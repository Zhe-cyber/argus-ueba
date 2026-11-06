# Real six-role pipeline commissioning,29 October2026

User requested a test before spending days accumulating history. The bounded
warm-up test used all six existing restricted roles and each allowed operation:
GetObject, HeadObject and GetBucketLocation on each role's own toy fixture.
No IAM changes, new resources, writes, reserved attack cases or real-model fitting.

## Observed evidence

-18operations succeeded,27SDK/HTTP sends used under one shared reservation
  (3preflight reads,6AssumeRole and18S3requests). No retries or redirects occurred.
-18/18successful calls independently matched distinct native CloudTrail events
  by source/account, request ID, principal ID, exact assumed-role session ARN,
  action, bucket, successful outcome and bounded timestamp sanity.
-All six diagnostic vectors contained3events, one of each operation, with valid
  IP observability3/3and no missing/invalid IPs. This exercises the real normalized
  evidence and new eight-count feature extractor without fitting any model.
-The normal exporter returned zero training rows after the test. All test ledger
  rows carry commissioning_exclude_from_baseline;29Oct warm-up is outside normal
  partitions. Seven previously missed ordinary actions remained missed. Nothing
  was backfilled, and the afternoon ordinary schedule was unchanged.

This is receipt correlation and pipeline functionality, not18detected attacks,
accuracy, real-user validation or proof of future detector quality. It covers own
fixture buckets/operation types, not every possible future resource combination.

## Clock finding

An initial diagnostic required provider time no later than client completion+1s.
That assumption failed: provider/client clocks are independent. Exact request,
principal, role, action and bucket checks matched all18events. An independent
one-call STS health check measured server Date about2.17s ahead of the laptop
midpoint, with1.36sroundtrip and1sheader precision. No Windows or native event
clock/timestamp was changed.

The diagnostic now declares a fixed60s cross-clock sanity tolerance around
attempt/completion, plus same MY date and no future time at audit. Exact receipt
identity checks remain mandatory. Regression tests reject wrong roles/requests,
errors, duplicate IDs and timestamps outside the bound. The clock change affects
only this commissioning audit, not the frozen detector, native logs, study
windows or scoring thresholds. Preserve the initial failed timing report as
evidence of the corrected assumption.

## Safety, budget and records

scripts/commission_six_roles.py runs only during29Oct warm-up. It regenerates a
fixed plan, claims stable IDs before I/O, shares existing48/run128/day1792/pilot
limits and counts actual HTTP sends. Existing uncertain claims are never retried.
The collector was paused only for execution and restored in finally; backend and
shadow jobs were unchanged. Existing source/artifact pins remain intact.

27test calls plus1separately reserved clock-health call add28reservations. With
the original5callprobe, total reserved calls were33at the audit. All remain in
the same ledger. The one-time test cannot restart or become scheduled workload.

Private records are in the existing data/live/commissioning-six-2026-10-29 folder:
execution.json, clock-health.json, audit-initial.json, audit-final.json and
normal-export-exclusion/. Records contain diagnostic evidence, not training
samples. The report is pseudonymous role counts/features; raw receipt IDs and
native logs stay in the private SQLite stores. No credentials are printed/exported.

Still required: actual daily ordinary history, closed-day coverage gates,
fitting/validation/calibration, separately tested reserved-case executor/evaluator,
and an explicit scoring release. Overnight sleep remains a real risk to the
laptop pilot; this test does not restore the missed morning or guarantee availability.
