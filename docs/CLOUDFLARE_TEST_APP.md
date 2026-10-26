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
after that correction. The public hostname initially failed TLS negotiation from
both Python and the system HTTP client. Do not bypass TLS validation. Public
redirect/denial checks and the approved user's login remain pending until HTTPS
is reachable. The API confirms route enabled, previews disabled and exact policy.

Validation:

```powershell
python -m pytest scripts/tests/test_setup_cloudflare.py -q
node --test scripts/tests/cloudflare-demo.test.mjs
```

Official API/runtime references:
- https://developers.cloudflare.com/workers/configuration/cloudflare-access/
- https://developers.cloudflare.com/api/resources/workers/subresources/subdomains/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
