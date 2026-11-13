# Microsoft 365 / Entra ID sign-in connector

**Status: ready, not connected.** The code and tests exist; no tenant has been registered and no
real call has ever been made. All tests use mocked HTTP and synthetic records.

## What it collects

Entra ID sign-in events from Microsoft Graph `GET /v1.0/auditLogs/signIns`, one record per
sign-in, posted to the local Argus backend `/ingest` as source `azure_ad`.

- `event_id` is the Graph sign-in `id`, so re-reads are deduplicated by (source, tenant, id).
- `source_account_id` is the tenant id. Identity keys are tenant-scoped.
- Users are keyed by the stable object id `userId` (not the renamable UPN). Sign-ins with no user
  (zero `userId`) are keyed by `servicePrincipalId`, else `appId`, as `service_principal`.
- Normalised action is `signin_success` (status.errorCode 0) or `signin_failure` (any other code,
  including MFA-interrupt codes such as 50074); resource is the app (`appDisplayName`, else
  `resourceDisplayName`). Country, client app, error code, conditional-access status and risk level
  are kept in metadata. Records without the Graph-only fields (`signInEventTypes`,
  `riskLevelDuringSignIn`, `isInteractive`) keep the older FYP1 mapping.
- By default v1.0 returns user sign-ins; service-principal sign-ins need a different filter
  (`signInEventTypes/any(t: t eq 'servicePrincipal')`) and are not requested by this connector yet.
  The parser and identity code already handle them.

## Requirements

- An Entra ID **P1 or P2** licensed tenant (a free 30-day P1/P2 trial works). Without a licence the
  API returns an error naming the P1/P2 requirement.
- An app registration with the **AuditLog.Read.All** *application* permission and **admin consent**.
- A local Argus backend in live mode (same as the other collectors).

## Azure portal steps (app registration)

1. Sign in to https://entra.microsoft.com as a Global Administrator of the tenant.
2. Identity > Applications > App registrations > **New registration**. Name it (for example
   `argus-signin-reader`), single tenant, no redirect URI. Register.
3. On the Overview page copy **Application (client) ID** and **Directory (tenant) ID**.
4. API permissions > **Add a permission** > Microsoft Graph > **Application permissions** >
   search `AuditLog.Read.All` > Add.
5. Click **Grant admin consent for <tenant>** and confirm; the status must show a green tick.
6. Certificates & secrets > **New client secret**. Copy the secret **Value** immediately (it is
   shown once) into a text file **outside the repository**, for example
   `C:\Users\<you>\secrets\entra_client_secret.txt`. Note the expiry date and rotate before it.

## Configure and run

1. Copy `config/entra.example.json` to `config/entra.json`; fill tenant id, client id, the secret
   file path and a `state_file` path (also outside the repo; both are rejected if inside it).
2. Validate, with no network access:

   ```
   python scripts/collect_entra.py check --config config/entra.json
   ```

   It prints the token call, the Graph call, the paging and ingest target it would use. The
   secret is never printed.
3. Start the live backend, then run one bounded poll:

   ```
   python scripts/collect_entra.py collect --config config/entra.json
   ```

   Output is counts only (`received`, `inserted`, `duplicates`, `retained`, `malformed`,
   `requests`, `drained`). Exit code 1 means something was retained or the request cap was hit.
   Schedule it every 10 to 15 minutes if wanted; there is no background job.

## How polling behaves

- Watermark file stores the newest `createdDateTime` committed. Each run asks for
  `createdDateTime ge <watermark - overlap_minutes>` (default 60) so late-arriving events are
  re-read; dedup makes this safe. First run looks back `initial_lookback_hours` (default 24).
- The watermark advances only if every record was committed and all pages were read. If
  `max_requests` (default 20) is hit first, it stays put and the run reports `drained: false`;
  Graph returns newest first, so raise the cap to clear a large backlog.
- HTTP 429: waits the `Retry-After` value (capped at 120 s), up to 3 retries per request, then stops.
  Pages are spaced 2 s apart (limit: 5 requests per 10 s per app per tenant).
- Only `@odata.nextLink` URLs under the Graph signIns endpoint are followed.

## Limits

- **Latency**: roughly 5 to 15 minutes typical, no published SLA. This is near-real-time, not the
  under-60-second AWS claim; do not state parity.
- **Retention**: 30 days on P1/P2 (7 days on Free), so history older than that cannot be fetched.
- **Throttling**: 5 requests / 10 s per app per tenant.
- The free 30-day trial tenant is a single-shot window; plan for it.

## What the owner needs to connect a real tenant

A P1/P2 tenant, the app registration above with admin consent, the secret in a file outside the
repo, `config/entra.json`, then `check` and `collect`. Nothing in the repo holds credentials.
