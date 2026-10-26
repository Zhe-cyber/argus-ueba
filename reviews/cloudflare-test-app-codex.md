# Cloudflare test target: author self-review

27 October 2026. Independent review remains pending; no merge requested.

Reviewed the credential boundary, fail-closed Worker, exact-email policy, route
enable ordering, collision refusal, API redirect refusal and safe error output.
No credentials or personal allow-list address are committed. The address is supplied
as a runtime argument and stored in the provider's Worker binding and Access policy.
The target does not expose Argus or connect to data stores. No paid subscription or
DNS configuration is modified. Partial resource cleanup is intentionally manual.

Validation: 104 backend/script tests passed with DATABASE_URL=sqlite-local;
4 isolated Node authentication tests passed; git diff --check passed. Tests cover
inspect-only behavior, permission failure before changes, name collision/subdomain
rename refusal, route enable after policy verification, policy mismatch refusal,
forged headers, missing/wrong identity, identity lookup errors and no identity in
the static success page. The native credential loader read the real local token
without displaying it, and the live preflight stopped at HTTP 403/code 10000 on
workers/subdomain. No remote resources were created by the preflight.

Subsequent live setup: permission update became effective; account had no existing
workers.dev subdomain. Registered the demo subdomain and deployed the Worker and
exact-email Access app. The provider rejected a future compatibility date; pinned
2025-01-01 and reran the five provisioning/four Node checks successfully. API
read-back confirms route enabled, previews disabled, single exact-email policy.
Public TLS negotiation initially failed, then succeeded without weakening
certificate validation. Cloudflare filtered the default Python client headers
(edge 1010); ordinary browser request headers returned HTTP 302 to the expected
Access team. A forged authenticated-email header also returned that login redirect.
The user reported reaching the success page. The API then returned the matching
allowed login, connection cloudflare, at 2026-10-26T18:58:36Z. The first immediate
query was empty; the later query returned one matching record. No latency claim.

The real record passed 11 in-memory normalization checks: shared schema, source,
identity, login action, application, timestamp, IP, request ID, provider user ID,
country and raw-record preservation. No database writes, raw record persistence
or anomaly scoring occurred. GitHub backend/frontend CI checks passed.

Remaining product work: continuous collection, idempotent storage, baseline data,
cross-provider identities and dashboard detection. No anomaly detection or
baseline claim is made from this authentication test.
