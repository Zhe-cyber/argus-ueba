# Local collection from real providers

This is a local development integration, not a public production deployment.
The API still needs application authentication and verified identity isolation
before public use. source_account_id namespaces native event IDs; it is not an
authorization or person-linking mechanism.

## Start a separate live backend

Use a Python environment with backend dependencies installed. Keep personal state
outside tracked benchmark files:

```powershell
$env:DATABASE_URL = 'sqlite-local'
$env:ARGUS_MODE = 'live'
$env:LIVE_STATE_DIR = Join-Path (Get-Location) 'data\live\connected'
$env:ALLOWED_ORIGINS = 'http://127.0.0.1:3000,http://localhost:3000'
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

In another terminal, run the dashboard with `NEXT_PUBLIC_API_URL` set to
`http://127.0.0.1:8000`. The local dashboard is http://127.0.0.1:3000.
Do not bind the API to 0.0.0.0 or send these logs to a public preview.
The gitignored connected directory holds personal events, scores and analyst
state. Do not commit it. Preserve or back it up before changing worktrees.

## Bounded one-shot collection

```powershell
python scripts/collect_live.py cloudflare --account-id YOUR_CF_ACCOUNT --app-id YOUR_ACCESS_APP_UUID
python scripts/collect_live.py github --repo OWNER/REPOSITORY
python scripts/collect_live.py aws --account-id YOUR_AWS_ACCOUNT --queue-url YOUR_QUEUE_URL --profile argus-collector --batches 1
```

The collector accepts only an explicit loopback HTTP IP and port. It rejects
redirects/proxies and refuses to forward events unless health reports live mode
and `native-receipt-v1`. There is no continuous daemon or scheduler in this change.

AWS checks STS account/non-root identity, queue account/ARN and a same-account DLQ.
Each run receives at most 10 messages per batch and at most five batches. Only a
matching committed receipt permits deletion. Invalid JSON, wrong-account envelopes,
missing native IDs, backend failures or invalid receipts remain for retry and the
configured SQS DLQ. A failed deletion is also retained/retryable. No poison-message
deletion or raw payload/error logging. Source CloudTrail/S3 retention is unchanged.

Cloudflare reads at most 100 authentication records within the previous 24 hours,
restricted to the selected app. It uses the existing DPAPI credential. GitHub
verifies repository ownership/admin access via the authenticated gh CLI and reads
at most 100 activity events, retaining only the previous 24 hours. This is the
Events API, not organization security audit logging. Neither bounded feed is a
complete historical export or an exactly-once upstream delivery guarantee.

## Retry semantics

Native keys use (source, source_account_id, event_id). Actual provider IDs are used;
Azure correlation IDs and guessed payload hashes do not identify independent
events. Existing callers can use an empty namespace; collectors provide an explicit
one. AWS native account metadata is checked against an explicit envelope.

Event insertion, scoring, alert attempts and a derived-result receipt share one
transaction. A failed pipeline rolls back. A retry of committed identical content
returns the original receipt with duplicate=true, without scoring or alerting
again. Its counters describe that original processing result, not a new snapshot
of the user's current totals. Same-key changed content returns 409 for review.
Receipts do not store raw provider payloads; a digest detects content conflicts.

ID-less/CERT rows remain independent, preserving replay observations. Existing
database rows migrate with NULL native IDs and are retained. The original eight
normalized fields remain, with optional native ID/account fields added; frozen
71/12-dimensional features and scoring mathematics are unchanged.

SQLite writers serialize through BEGIN IMMEDIATE. PostgreSQL transactions use a
per-user advisory lock. Alert failures retain the existing best-effort policy and
roll back only their savepoint. Direct low-level insert_event callers do not get
an API receipt; do not seed native-keyed events that way for production collection.

## Verified evidence on 27 October 2026

Real connected state contains 46 AWS management events, one Cloudflare successful
login and seven GitHub activity events (54 total). One historical synthetic UI
fixture was found in the earlier development database; the original was preserved,
and the connected copy excludes that fixture and its orphan state. The counts
above refer only to real connected events.

The Cloudflare and GitHub collectors were each rerun: all eight repeated records
were duplicates and zero additional observations were stored. AWS acknowledged
46 messages only after successful receipts. Source-specific counts, local API
readiness and dashboard HTTP 200 were checked without exporting identities/IPs.

The cloud AE artifacts are absent in this checkout, so account risk is Unknown.
These results establish collection/storage/display plumbing, not anomaly accuracy,
training completeness, SHAP, identity linking or the proposed agent simulation.

Validation: full local SQLite suite 132 passed, with the opt-in PostgreSQL test
skipped unless ARGUS_TEST_PG_URL is set. Four Worker tests also passed. A guarded
PostgreSQL test uses only 127.0.0.1:55432/argus_ingest_test and a temporary schema;
the CI workflow supplies a disposable PostgreSQL 17 service. It must never use
Neon or a production DATABASE_URL. Initial local Docker startup did not become
ready, so do not claim a successful local PostgreSQL run.
