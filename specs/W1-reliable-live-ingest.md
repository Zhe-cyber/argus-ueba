# W1: Retry-safe live ingestion and bounded collectors

27 October 2026. Branch codex/w1-reliable-live-ingest, stacked on PR #8.
User authorized continuing real-cloud integration and proposed simulated users.

First deliverable: atomic, server-side idempotency before any real queue draining.
Reuse the native-ID design from the earlier unmerged W1-B0 patch, correcting its
crash-after-insert gap and avoiding Azure correlation IDs (not unique events).

- Deduplicate only genuine native event IDs: AWS eventID, Azure id/Id, Cloudflare
  ray_id, GitHub Events API id. Preserve ID-less/CERT replay rows independently.
- Scope the unique key by source and collector-supplied source_account_id; this
  is a source namespace, not authentication or tenant authorization. Preserve
  existing clients with an empty default namespace. Derive AWS account from its
  native record when available and reject contradictory envelopes.
- Add idempotent SQLite/Postgres migrations. Existing rows get NULL event IDs;
  do not rewrite, hash-dedup or delete historical benchmark data.
- Commit event, scores and a derived-result receipt atomically. On failure roll
  back; a retry processes normally. Return the original result on duplicates
  without scoring or creating alerts again. Reject conflicting content for an
  already-used native key with HTTP 409. Persist a payload digest, not raw data.
- Serialize SQLite writes with BEGIN IMMEDIATE; use per-user transaction advisory
  locks for Postgres. Optional alert failures roll back a savepoint, preserving
  the existing best-effort alert policy without poisoning the transaction.
- No frozen feature/AE changes, thresholds or identity inference. Live missing
  model remains Unknown. Human merges; localhost only, no public deployment.

Next deliverable after tests/review: bounded collectors using explicit accounts,
only acknowledge SQS after a committed successful ingest, retain malformed or
rejected messages for the configured DLQ, and no secret/raw PII logging. Use
Cloudflare's real Access log API and GitHub activity feed with accurate labels.
Start with --once runs; no unrequested background scheduler.

Acceptance: retry stability, source/account separation, ID-less CERT preservation,
conflicting key refusal, restart and concurrent duplicate safety, safe old-schema
migration, score-failure rollback and retry recovery, alert savepoint behavior;
all backend/script tests forced to sqlite-local. Never run against Neon. Record
Postgres validation limits explicitly if no isolated local test service is available.

Simulation evaluation: five normal personas and one account that switches to a
controlled suspicious routine. Genuine cloud identities must be distinguished
from personas sharing credentials. Hidden scenario labels must stay outside
model features. Fit/calibrate using normal-only, chronologically separate data;
keep a held-out normal test stream and compromised-account stream. Describe this
as controlled simulation on real services, not enterprise-user validation. No
destructive actions, fabricated provider timestamps or unbounded LLM tool access.
