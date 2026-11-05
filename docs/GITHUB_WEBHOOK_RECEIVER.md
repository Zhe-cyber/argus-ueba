# Signed GitHub evidence capture — local implementation

The standalone `scripts/github_webhook_receiver.py` receiver is implemented and tested, but not deployed, listening, configured as a repository webhook or connected to the dashboard. The existing repository poller continues unchanged. Synthetic signed fixtures verify engineering behavior; they are not genuine user histories or detection results.

## Local interface

An explicit app factory takes a dedicated private `github-webhooks.db`, at least 32 secret bytes, and an exact repository numeric ID and full name. There are no import-time network or database side effects. The CLI binds only `127.0.0.1:8014`; it cannot accept public GitHub deliveries on its own.

```powershell
python scripts/github_webhook_receiver.py --database <private-directory>/github-webhooks.db --secret-file <private-secret-file> --repository-id <numeric-id> --repository <owner/name>
```

The secret file contains the exact webhook-secret bytes. For later deployment, generate a cryptographically random secret encoded as ASCII hex, with no newline, and configure that exact string in GitHub. Never put the secret, payload DB or raw deliveries into Git. Filesystem privacy and backup/retention need explicit operational configuration before deployment; this script does not encrypt SQLite or change Windows ACLs. Do not use arbitrary binary secret bytes that cannot be entered identically in GitHub's secret field.

POST `/github/webhook` accepts JSON and a single canonical UUID delivery header, an allowlisted event header and exact-byte SHA256 signature. It rejects content encoding, duplicate required headers and bodies exceeding 512 KiB. Signature validation precedes JSON parsing and schema/scope checks. The raw signed body is retained privately with its digest, receipt time, header event type, sender ID/type and pinned repository ID. Unsupported events explicitly fail.

Supported initial events: ping, push, pull_request, issues, issue_comment, create, delete. A ping is configuration evidence, not user behavior. Actor type reflects the native sender field; it does not prove a human physically performed an action. Receipt time is not a claimed native action timestamp. Some event payloads provide timestamps for objects, which a future bridge must interpret carefully instead of silently substituting receipt time.

SQLite commits with synchronous FULL before returning success. Identical delivery-ID/type/body returns duplicate; conflicting ID reuse returns 409. The same body under another delivery ID also returns 409, irrespective of event header. This conservative rule can flag legitimate byte-identical repeats and needs operational review, rather than treating receipt counts as a complete behavioral count.

Body signatures do not authenticate GitHub's delivery/event headers. Event-specific shape validation narrows misuse but does not cryptographically establish those headers or stop every replay variant. The ingress code validates the signature; the stored evidence records the body and digest, not a signature/key-version archive for independent future cryptographic reverification.

Storage failures return 503 with no successful acknowledgement. No logs or responses contain raw payloads or secrets. Raw bodies can contain private comments, commit messages, repository/actor details and attacker-controlled text; treat them as untrusted evidence. Do not feed them to a shell or LLM as instructions.

## Remaining integration and deployment

1. Select a hosted HTTPS receiver with durable private storage that remains available while the laptop sleeps. The local SQLite implementation is a reference for semantics, not a serverless deployment artifact. Determine account, least-privilege permissions, body/storage limits, retention, quotas and billing checks first.
2. Implement the equivalent hosted handler or deploy this app in an appropriate persistent environment; provision a distinct endpoint and stored secret. Do not expose the existing analyst/backend API through a public tunnel.
3. Create an explicitly scoped repository webhook and verify one real delivery through durable capture. Restrict subscription to the supported events. GitHub does not automatically redeliver all failed deliveries; implement monitoring and explicit redelivery/reconciliation before claiming reliable recovery.
4. Add a separately reviewed normalization bridge: native actor/time evidence, immutable receipt provenance, header trust annotations and cross-feed deduplication. Webhook delivery IDs and Events API IDs differ; never insert both feeds into one event count assuming equal IDs.
5. Integrate histories and coverage reporting, then preregister and evaluate any scoring method. This receiver provides no anomaly scores, novelty flags, account linking or activation.

No hosted receiver, new AWS/Cloudflare resources, repository webhook, schedule changes or live-store migration have been performed in this slice.
