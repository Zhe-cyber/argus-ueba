# Generate real Access login evidence

This deploys a tiny static authentication target, not the Argus application. It
does not connect to a database, ingest endpoint, AWS, or any customer resource.
Only the approved email can receive its success page. User identity comes from
the Cloudflare runtime's `ctx.access`; forged HTTP headers are insufficient.

Prerequisite: the local token saved with `cloudflare_inspect.ps1` needs account
permissions Access: Apps and Policies Edit, Workers Scripts Edit, and the existing
read permissions. Restrict it to the intended account. Use setup privileges only
for provisioning; an eventual collector needs only Access: Audit Logs Read.

Run with the local Python interpreter (no additional dependencies):

```powershell
python scripts/setup_cloudflare.py --account-id YOUR_ACCOUNT_ID --allowed-email YOUR_EMAIL
```

Default operation is read-only preflight. Append `--deploy` to create the Worker
and exact-email Access policy and enable its workers.dev route after policy
read-back. Preview URLs are disabled. If no workers.dev subdomain is registered,
add `--new-subdomain A_UNIQUE_NAME`; the script refuses to rename an existing one.
No paid subscription, DNS zone, or custom domain is created.

The account/email are arguments; credentials are not. The script decrypts the
saved Windows DPAPI credential in memory and never prints it or raw API bodies.
Permission errors stop preflight. The script refuses same-name existing resources;
it intentionally does not overwrite, adopt or delete them on reruns. If a later
step fails, partial resources remain for manual inspection and correction.

After deployment, check an unauthenticated request is redirected to Access or
denied. Open the returned URL yourself and authenticate using the approved email.
Then query Access logs through the existing inspection helper. A successful login
proves a real authentication record can be collected; it does not prove anomaly
detection, sufficient baseline history, identity linkage, or in-session telemetry.

Live setup on 27 October 2026: initial token-edit propagation returned HTTP 403;
a later preflight succeeded and reported no registered subdomain (404/code 10007).
Registered `argus-lab-e98718.workers.dev`, uploaded `argus-access-demo`, created the
Access application, verified the single exact-email allow policy and enabled the
route with preview URLs disabled. URL:
https://argus-access-demo.argus-lab-e98718.workers.dev

The provider rejected the current client date as a future compatibility date, so
the Worker now pins the established `2025-01-01` runtime baseline. Setup succeeded
after that correction. The public hostname initially failed TLS negotiation, then
became reachable without weakening certificate validation. Default Python client
headers received Cloudflare edge error 1010; ordinary browser request headers
received the expected HTTP 302 to the configured Cloudflare Access team. Requests
with a forged authenticated-email header also received that same login redirect.
The API confirms route enabled, previews disabled and exact policy.

The user subsequently reached the authenticated success page. The Access API
returned a matching allowed `login` event with `connection=cloudflare`, timestamp
`2026-10-26T18:58:36Z` (27 October, 02:58:36 Malaysia time), application/identity
IDs, country, IP and request ID. The first immediate query returned no record; a
later query returned it. No latency guarantee is inferred from this observation.

The actual record was normalized in memory through `backend.normalizer.normalize`
using `cloudflare_access`. All eight shared-schema fields were present; identity,
action, application, timestamp and IP were preserved, alongside country, request
ID, provider identity ID and the original raw record. No raw record or personal
identity/IP value was committed. No database writes or anomaly scores were made.

Verified scope: real protected app -> successful login -> provider authentication
log -> shared-schema normalization. Continuous ingestion, duplicate-safe storage,
dashboard detection, baseline sufficiency and cross-provider linking remain
separate work. The draft PR's backend and frontend CI checks also passed.

Validation:

```powershell
python -m pytest scripts/tests/test_setup_cloudflare.py -q
node --test scripts/tests/cloudflare-demo.test.mjs
```

Official API/runtime references:
- https://developers.cloudflare.com/workers/configuration/cloudflare-access/
- https://developers.cloudflare.com/api/resources/workers/subresources/subdomains/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
