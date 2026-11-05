# Reserved AWS case study: implementation and runbook

29 October review follow-up: see PRECALIBRATION_REHEARSAL.md, EXPECTED_SENSITIVITY_PRECALIBRATION.md and COMMIT_PILOT_CHECKLIST.md. Sensitivity note and engineering harness are now implemented; real-fitting execution remains pending eligible 6–7 November data. These additions do not amend the production protocol/guards or claim a real rehearsal already passed.

Implemented 29 October 2026, before normal fitting starts. Protocol V2 and method annex v1 remain unchanged. No real reserved case has run, no actual pilot bundle has been fitted, and live risk scoring is not activated.

## What runs automatically

The existing laptop collector routes actor execution to run_reserved_study.py only on 12 and 13 November MY. Other dates still use the original ordinary runner. The reserved wrapper reuses the same ledger, action IDs, claim-before-I/O mechanism, API/HTTP budget caps, non-root runner/roles, scoped logging checks, fixture checks, 15-minute due grace and no uncertain retries.

For persona-01 and persona-02 on each registered date, exactly the chronologically first planned GetObject changes its resource to the existing p06/fixture.txt. Role, operation, scheduled time, count and every other action stay unchanged. Other roles continue their ordinary profiles. It adds no scenario calls. All six roles' case-date days are excluded from normal fitting/validation/calibration by the unchanged normal exporter.

The ordinary execution path refuses reserved dates, preventing accidental ordinary reads from consuming case action IDs. The reserved execution path requires a valid release BEFORE claims or provider calls. Missing/changed/no-go releases block actor execution on those dates rather than silently falling back. Collection and receipt auditing continue. Do not bypass a blocked release by editing the ledger or manually performing replacement reads.

## Before calibration: complete and commit

Target review/commit by 5 November. The freeze command additionally requires all bound source files committed and unchanged, with their most recent Git commit before 8 November 00:00 MY. This is local operator/Git provenance, not external attestation. The scripts intentionally have no CLI clock, target or synthetic override.

The ordinary generator probabilities/weights/seed/limits remain byte-frozen. Labels such as Morning auditor describe toy workload profiles, not real business tasks. Distinct resource preferences and seeded variation may support a controlled sensitivity probe, but can still amount to learning scripts. A count-only AE may miss the substitution.

## 11 November only: model/release freeze

First reconcile/export/train the ordinary normal windows with the existing trainer. A training completion is not an activation decision. A real candidate must pass compatibility, reload parity, all-six-role history gates and the primary calibration/role-ceiling gate. If it fails, report no-go; do not switch to a comparator using scenario results.

From the active checkout with its existing Python environment, on 11 November MY:

    python scripts/reserved_study.py --bundle <private-real-bundle> --output <ledger-directory>/reserved-release.json --account-id <account-id> --stack argus-ueba-actors

This makes no provider calls and never installs a model. Use a fresh release path. It recomputes calibration from frozen normal scores, binds bundle/source/protocol hashes, scope, target dates and the receipt cutoff. Default loaders refuse synthetic bundles. Retain release, bundle, dataset, producing source bytes and Git revision. Do not overwrite a release or mutate its bound artifacts after it is created.

If creation fails partway, an existing release file is not proof of qualification: the runner always revalidates it before use. Preserve it as a failed artifact and investigate; do not casually replace it after scenarios begin.

## 12/13 November: due-only execution

Keep the laptop awake/logged in/online during 08:00–20:00 MY. The existing collector task performs execution; do not run a second scheduler. Missing/failed actions stay missing/unresolved; no substitute day/account or post-hoc replay is permitted. The approved-change label is separate analyst context, not an input feature or extra permission.

The wrapper's explicit CLI exists for operational review but is not needed alongside the scheduler:

    python scripts/run_reserved_study.py --account-id <account-id> --stack argus-ueba-actors --state-dir <ledger-directory>

Without --execute it only displays a plan on a registered current date. The --execute option uses the same strict release/ledger gates. It is not a way to recover a missed slot or bypass unhealthy collection; normal operations should stay through the guarded pilot scheduler.

## 14 November 20:00 MY onward: final receipt audit/evaluation

Evaluation refuses to run before the fixed final arrival cutoff, preventing early case-based design changes. The native events' persisted ingested_at determines whether a receipt arrived by cutoff. Native event timestamps alone are insufficient. Local ingestion timestamps are operational evidence, not externally attested clock measurements.

    python scripts/evaluate_reserved_study.py --release <ledger-directory>/reserved-release.json --ledger <ledger-directory>/ledger.db --events <connected-directory>/events.db --account-id <account-id> --stack argus-ueba-actors --out <fresh-private-report.json>

Both databases are opened read-only in separate snapshots. A status of provider_verified alone does not qualify: evaluator independently matches the exact expected operation/resource/request/principal/assumed-role ARN, account, success, native ID and timing. The +/-60-second client/provider clock sanity margin follows the commissioning clock finding; it does not change detector thresholds. Duplicate, late, wrong, absent or pending receipts do not become clean observations. At most 1,000 case ledger rows are read; unexpected claims fail the audit.

Each scored role/day requires >=90% planned receipts, no unresolved claims, closed date and complete valid IP context. Targets additionally require their exact substituted receipt. No missingness is zero-filled. Independent auditing can mark a ledger-verified record unscored.

All frozen model components are reported with their calibration gates and strict greater-than cutoffs. A no-go comparator or OR receives unavailable flags, not an invented decision. The primary method is not replaced. Analyst labels enter the result display only after feature extraction/inference; they never select references, thresholds or responses.

Report four target account-day slots (two unannounced, two approved) and the other eight ordinary-profile control account-days, with all missing/unscored cases and late receipts. These counts are not independent human samples or general attack/false-positive rates. The approved change may look equally unusual: that demonstrates investigation burden, not malicious intent classification.

No outcome automatically activates live scores or approves a model release. A separate reviewed activation decision remains required.

## Verification and current state

Full isolated scripts/backend suite: 554 passed, one optional PostgreSQL test skipped. After adding four additional mocked executor/routing cases, the focused reserved-study suite passed all 22 tests. Synthetic tests use explicitly tagged synthetic bundles and fake AWS clients; they are not real case outcomes.

Tests cover exact substitutions, full-day budget/claim/no-retry behavior, reserved routing, release-before-I/O, cutoff/date refusal, exact native auditing, wrong account context/role/request/resource, failed/late/missing receipts, absent/invalid IPs, synthetic bundle refusal, threshold tampering and keeping analyst context out of inference.

Runtime release changed only five reviewed source pins: local_pilot.py, run_persona_history.py and the three new reserved scripts. The owned backend/collector were briefly paused, config backed up, and restarted after verification. Current ordinary collection and daily coverage check pass. No extra missed claims were introduced during this release. All latest source/test/doc changes remain local and uncommitted for user review.
