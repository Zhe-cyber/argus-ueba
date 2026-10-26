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
Public TLS negotiation initially failed in both HTTP clients without weakening
certificate validation. No login records yet.

Remaining evidence: unauthenticated HTTP denial/redirect, approved user login and
corresponding real Access log. These are not yet verified, and no anomaly detection
or baseline claim is made.
