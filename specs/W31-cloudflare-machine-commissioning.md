# W31: Cloudflare service-identity commissioning

30 October 2026. User authorized background Cloudflare persona activity. Use
machine service tokens, not automated email/MFA sessions or fake human accounts.
Keep the original approved-human Access app, AWS study/profile, backend pins and
CLUE evaluation untouched. No model activation or workload scheduler in this step.

Prepared `scripts/cloudflare_lab_setup.py`: bounded existing-account inventory,
name-collision checks, current-user DPAPI round-trip before provider mutation,
durable claim before creating one service token, one-time response encrypted
before use, and expiration no later than 15 November 00:00 Asia/Kuala_Lumpur.
Unknown outcomes stop instead of retrying; a definite 403 is recorded and can
be retried after the user edits permission, with inventory collision checks.
No credentials appear in arguments, stdout, JSON status or Git. Only private
ignored state contains encrypted credentials and provider scope identifiers.

Three focused synthetic tests passed: one bounded create with encrypted-only
storage, no existing-app mutations, permission denial, collision/expired/unknown
outcome rejection. A real token-create request returned HTTP 403 after the
read-only preflight and encryption check passed. Attempt status is
`permission_denied`. No service token or machine app was created and no new
Cloudflare traffic has been scheduled.

User action required: add Account / Access: Service Tokens / Edit to the SAME
saved API token and same account, retaining its existing permissions. API names
this `Access: Service Tokens Write`. No token replacement or chat transfer needed.

After permission is fixed: create one encrypted expiring token, provision a
separate Access-protected toy Worker with an exact service-token Service Auth
policy, read back the policy, verify unauthenticated denial, then one successful
machine request. Native log identity/field coverage must be inspected before
designing the machine ingestion adapter. Existing collector requires user_email
and cannot simply treat machine events as human sign-ins. Do not invent a
user ID/email to make collection pass. Preserve native ray ID, original event
time and explicit allowed outcome. Verify one exact native receipt reaches
Argus before generating the remaining profiles or installing any schedule.

Source: [Cloudflare service-token creation permissions](https://developers.cloudflare.com/api/resources/zero_trust/subresources/access/subresources/service_tokens/methods/create/).

## Permission fix and real commissioning

The user's token edit resolved HTTP 403. One expiring service token is created
and encrypted locally. A separate static `argus-machine-lab` Worker and Access
application are deployed. Policy read-back confirms exactly the commissioning
token under Service Auth (`non_identity`); the workers.dev route was enabled
last and preview URLs remain disabled. Original human app is untouched.

Unauthenticated request denied; one authenticated GET returned HTTP 200 with
the static machine-only marker and a native Cloudflare ray ID. Both the request
claim and provider response status/ID are saved without secrets. No retry of
the action or fake log. The matching Access log is pending: no machine event
was forwarded and no service identity was invented in Argus.

Six Python setup/provisioning tests and three Worker tests passed. Coverage
includes inspect-only behavior, exact policy validation, enable-last order,
wrong-policy fail-closed, forged headers, GET-only bounded paths and static
uncached output. A separate source-pinned checker can poll for the exact ray
ID every five minutes, for six hours at most, without generating new traffic.
Native field/identity inspection and a backend round trip remain prerequisites
for the six-profile background workload. No model/scoring/runtime pin changes.
