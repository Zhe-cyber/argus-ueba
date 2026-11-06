# W19: Standalone GitHub signed-evidence receiver

Written 29 October 2026. Build and test locally; no deployment or repository webhook creation in this slice. User commits/pushes manually.

## Goal and scope
Add scripts/github_webhook_receiver.py, focused backend/tests/test_github_webhook_receiver.py, operational documentation and update.md notes. Do not edit pinned backend runtime, existing DBs, collector/task configuration, permissions or models.

## Contract
- Explicit app factory; no network listeners, credentials loading or DB creation at import.
- Local CLI binds only 127.0.0.1:8014; explicit repository ID/name, dedicated github-webhooks.db and private secret file. Secret at least 32 bytes. Database must be separate from the connected events.db.
- POST /github/webhook: stream limit 512 KiB, verify exact-byte HMAC SHA256 before parsing, reject duplicate security headers, non-JSON, compressed payloads, invalid UTF-8/JSON, mismatched repository, invalid sender ID or malformed delivery UUID.
- Accept only ping, push, pull_request, issues, issue_comment, create and delete with event-specific payload checks. Unknown types fail explicitly. Repository IDs, not login guesses, pin scope.
- Preserve exact signed body, SHA256 and received-at time in dedicated SQLite. Store derived event type/actor/repository references with evidence basis. Receipt time is not native action time. Full body may contain private commit messages/comments; private storage only, no body logging or public exports.
- ACK only after transaction commit. Same delivery ID/body/type returns duplicate; changed content under same ID is a conflict. Identical signed body under another delivery ID is also a conflict even with a different event header, to avoid silently counting header-relabelled replays. Flag this conservative rule as possibly rejecting legitimate byte-identical repeat events.
- Signature authenticates bytes only: GitHub event/delivery headers are not covered by body HMAC. Require event-specific shape, keep these header-derived claims explicit and do not present receipt counts as proven unique user actions.
- No automatic retries/redelivery guarantees. No auto insertion into existing normalized store. Future bridge must separately handle cross-feed dedup, native time, provenance, schema compatibility, retention and activation.

## Acceptance
Realistic synthetic signed fixtures test signature/byte tampering, limits, duplicate headers, scope, event schemas, duplicate/conflict semantics, durable exact bytes, no storage on rejection and explicit source-time limitations. Force SQLite for full backend tests. Leave running pilot healthy and unchanged.
