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

Initial preflight on 27 October 2026: Worker listing succeeded with zero Workers,
but workers/subdomain returned HTTP 403 / code 10000. No cloud resources were
created by that run. Awaiting token permission recheck or updated local credential.

Validation:

```powershell
python -m pytest scripts/tests/test_setup_cloudflare.py -q
node --test scripts/tests/cloudflare-demo.test.mjs
```

Official API/runtime references:
- https://developers.cloudflare.com/workers/configuration/cloudflare-access/
- https://developers.cloudflare.com/api/resources/workers/subresources/subdomains/methods/get/
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/methods/update/
