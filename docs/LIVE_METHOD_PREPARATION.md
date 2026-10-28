# Live method preparation: engineering starts before history is ready

Status29 October2026: preparation, not a frozen detector annex. The V2 collection
calendar and gates remain fixed. Work on code, synthetic tests and evidence
checks can begin now; actual fitting excludes29 October warm-up and begins with
30 October data. No model is trained by the readiness tool.

## Completed now

`scripts/live_history_readiness.py` reconstructs every expected V2 ordinary
action for30 October-10 November from the frozen profile. It reads the existing
action ledger and actual connected SQLite store in read-only transactions. It
rechecks native AWS source/account/event ID, request ID, expected assumed-role
session ARN, principal ID, operation, bucket, success and Malaysia local date.
A ledger status of provider_verified alone is insufficient. Native IDs cannot
be reused for multiple selected actions. Unknown/pending claims prevent a usable
day. Missing planned actions remain missing; no backfill or fake inactivity.

Reports show each role/day's planned, verified, missing, missed and unresolved
counts, verified/planned fraction and future/current-partial/usable/incomplete
state. Only closed MY dates with at least90% planned actions verified and no
unresolved claims can pass. The tool then checks the existing history gates:
five fitting dates spanning seven calendar dates, two validation dates, two
calibration dates per role and pooled12 calibration account-days from at least
four eligible roles across three dates. Additional method-specific requirements
are still required; a history-gate pass is never model-release approval.

Warm-up/commissioning/setup dates and reserved case dates are outside the query.
No score values, scenario outcomes, model artifacts or provider APIs are used.
Synthetic test fixtures exercise full gate passes and receipt failures; they
are not included in actual history or reported as pilot results. The report
contains role labels and counts rather than raw identities, resources or IPs.

Example command (paths intentionally explicit, use a fresh report name):

```powershell
python scripts/live_history_readiness.py --pilot-config <private-pilot-config.json> --out <new-private-report.json>
```

## Compatibility gaps identified before fitting

| Existing component | Why direct reuse is insufficient |
| --- | --- |
| export_cloud_baseline.py | Reads one-shot run manifests; daily ledger evidence needs its own versioned export contract |
| train_verified_cloud.py | Uses UTC cutoffs/closed-day checks and a legacy calibration transformation; V2 study uses MY local dates and a fixed empirical review budget |
| Legacy12-count cloud AE | Raw inference works, but benchmark transfer and original training extractor provenance are unvalidated |
| CLUE personal/context scorers | Different source semantics; prior maximum-score calibration failures remain negative findings |

Do not change these frozen contracts silently, relabel UTC windows as MY windows,
pass ledger rows as old manifests, or use warm-up/setup as normal baseline. The
new readiness report is an evidence-audit foundation for the new exporter, not
an adapter that makes incompatible trainers valid.

## Next implementation slices, starting before the data is ready

1. Implemented: export_live_daily.py reuses audited native evidence and eligibility
   to export the separate aws_lab_daily_v1 eight-count profile plus categorical
   action/resource/hour context. See AWS_LAB_DAILY_FEATURE_CONTRACT.md. Actual
   fitting still requires closed, eligible data; no legacy weights are compatible.
2. Complete the detector annex before5 November23:59: account-conditioned method,
   population AE and volume comparators; sampling requirements; fixed fitting
   procedure, seeds and hyperparameters; normal-only calibration rule including
   ties; no automatic adaptation through held-out evaluation. Method choices
   remain explicitly unresolved here; this preparation note is not preregistration.
3. Implement local training/reload/calibration checks and test on synthetic data
   only until the actual partitions close. Actual fitted artifact hashes can
   only be recorded after fitting; the procedure is frozen beforehand.
4. Implement and test the separately registered scenario executor before11Nov
   freeze. Preserve actual timestamps, action counts and independent analyst
   context for the matched approved-change control.

The 30-minute shadow view continues running in parallel. It demonstrates
inference, while the ledger study supplies the evidence needed to qualify a
compatible model and threshold. Neither path guarantees positive detection
results. Keep the15 November fallback and report negative findings if gates fail.
