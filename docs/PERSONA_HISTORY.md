# Controlled persona history pilot

This adds a separate due-only runner for the six existing toy-S3 machine roles.
It does not change the fixed simulation runner, cloud permissions, ingestion,
normalisation, model contracts or live scores. Profile parameters are illustrative,
not fitted to CLUE or measured from volunteers. This pilot is a controlled
sensitivity experiment; it does not substitute for independent human users.

## One-shot usage

Run from this checkout using the existing non-root `argus-simulator` profile:

```powershell
python scripts/run_persona_history.py --account-id YOUR_ACCOUNT
python scripts/run_persona_history.py --account-id YOUR_ACCOUNT --state-dir YOUR_CANONICAL_PRIVATE_HISTORY_DIR --execute
```

The first command only describes today's offline plan. It does not create state
or call a provider. The second executes only actions planned within the previous
15 minutes on the current **Malaysia calendar date**. There is no date override,
catch-up execution or synthetic provider timestamp. Future actions wait for a
later invocation; older ones become missed. Nothing in these commands installs a
scheduler. For unattended operation, an explicitly configured recurring invoker
must keep using the same checkout, profile and canonical state directory.
Invocations must be frequent enough for the 15-minute window; a sleeping laptop
causes missed actions, not fabricated historical data.

Use one canonical ledger for this lab across all invocations/worktrees. Do not
copy, delete, reset or use a fresh ledger to retry unknown actions or circumvent
limits. The ledger pins the account, stack and profile hash. Changing profiles
requires explicit review and a versioned experiment protocol.

## Limits and recovery

- Only `GetObject`, `HeadObject` and `GetBucketLocation` against the existing seven
  private synthetic buckets, using `fixture.txt`; no arbitrary methods/targets.
- Existing IAM policies, exact lab-runner identity, expected assumed-role ARNs,
  enabled CloudTrail and exact S3 read-event selectors are checked before reads.
- Each role uses a neutral session name. Scenario/provenance labels stay in the
  private ledger, outside provider records and detector inputs.
- At most five planned actions per role/day; reserve at most 48 SDK calls/run,
  64/day and 1,792 across the ledger's pilot. Reservations include STS/preflight
  and role assumptions and remain consumed after failures. Client retries are
  limited; a `before-send` guard also bounds HTTP attempts, including redirects.
- SQLite serialises claims and budget reservations before I/O. A crash can leave
  actions `claimed_unknown`, including actions not actually sent. They are not
  automatically retried. Reconcile them manually using provider evidence; this
  prioritises avoiding duplicate execution over completing every planned action.
- Fixture metadata/content and maximum size are checked on object reads; errors
  stop the invocation. Credentials/provider error bodies are never printed or
  persisted. The state directory still contains private account/resource IDs.

## Receipt audit and history provenance

After collecting native CloudTrail through the existing bounded collector:

```powershell
python scripts/run_persona_history.py --account-id YOUR_ACCOUNT --state-dir YOUR_CANONICAL_PRIVATE_HISTORY_DIR --audit-events YOUR_CONNECTED_EVENTS_DB
```

This performs no cloud calls and reads the event store read-only. It updates only
the history ledger. An action progresses from `api_ok_audit_pending` to
`provider_verified` only when exactly one native, source-account-scoped event has
the matching request ID, principal ID, operation, resource and no provider error.
Missing or ambiguous evidence remains pending. Provider-verified actions do not
prove a complete day of logging. `GetBucketLocation` requires delivery of the
existing management-event feed as well as S3 object-event coverage.

All roles use the same filename. Persona 03's ordinary archive access refers to
the confidential-named **toy bucket**, not a unique file or actual sensitive data.
Persona 05 is an ordinary higher-volume control. Cloudflare/GitHub automated legs
are disabled; a GitHub read cannot be represented as an Events API activity, and
Cloudflare authentication logs do not monitor all application operations.

The ledger supports source-verified role attribution for this lab, not approved
cross-provider person linking. Observed account-days must retain source scope,
setup/collector/lab provenance, partial-day status and missing-coverage flags.
Absent events do not establish confirmed inactivity. No profile parameter,
planned idle day, plan count or scenario flag is training evidence.

## Validation on 28 October 2026

Local backend/script regression suite: 239 passed, one optional PostgreSQL test
skipped. Runner tests use fake providers and temporary ledgers, including
concurrent claims, stale days, changed targets, duplicate invocations, budgets,
failure uncertainty and native-evidence matching. Existing fixed simulation
tests remain unchanged.

A separate real readiness check made three read-only AWS calls and confirmed the
exact non-root runner, logging enabled and selectors for exactly seven toy
buckets. At 06:52 Malaysia time the due-only runner correctly returned no due
actions, with zero actor calls. A real due-action/receipt round trip is **not yet
validated**. No scheduler, compatible live model or model activation was added.

Next evaluation gates: reviewed normal-history provenance and coverage; sufficient
chronological development/calibration observations; a compatible feature contract;
normal-only thresholds; and untouched later scenario/control periods. Report
normal alerts separately from detections/misses and matched legitimate changes.
