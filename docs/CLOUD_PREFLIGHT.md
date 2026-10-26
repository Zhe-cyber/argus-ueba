# Real-account preflight

Update: CLI deployment and non-root collector access now work. See
[AWS_CLI_SETUP.md](AWS_CLI_SETUP.md) for verified resources, credential handling,
coverage and remaining release gates. The initial preflight findings below are
historical, not the current CLI status.

Status checked 27 October 2026: a local AWS CLI default profile exists, but STS
rejected its credentials with InvalidClientTokenId. This does not establish whether
CloudTrail is enabled. No resources or AWS settings were changed. The user currently
signs into the console with the root account.

## AWS: establish separate access first

Use the console to establish a named non-root administrative identity, then use that
identity for setup. Prefer temporary role/SSO credentials for the collector. Do not
create or share root access keys. AWS guidance:
https://docs.aws.amazon.com/IAM/latest/UserGuide/root-user-best-practices.html

For the initial read-only CloudTrail Event History collector, the required permission
is below. LookupEvents requires Resource '*'; this is not AdministratorAccess.

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "cloudtrail:LookupEvents",
    "Resource": "*"
  }]
}
```

Configure a separate CLI profile named `argus-readonly` using the chosen identity's
local sign-in flow. Leave the existing default profile unchanged. Do not paste keys,
MFA codes, session tokens or passwords into chat or commit them to the repository.

Read-only verification after sign-in:

```powershell
aws sts get-caller-identity --profile argus-readonly
aws cloudtrail lookup-events --profile argus-readonly --region us-east-1 --max-results 5
```

Check the returned identity is the intended role/user, not root. Also check the
region in which you perform the test action: regional management events need the
matching region; global-service activity requires checking us-east-1.

This proves Event History access only. The EventBridge/SQS architecture is separate:
it needs a logging trail, an appropriately configured rule, queue policy, dead-letter
handling, and a collector role restricted to the specific queue. It is not provisioned
by this change. Provisioning permissions must not become collector permissions.

## Cloudflare: determine whether Access is configured

Having DNS/CDN sites on Cloudflare does not establish an Access deployment. In the
Cloudflare Zero Trust dashboard, check whether an Access application exists and
whether a real login to that application produces an authentication-log record.
Record the account and application identifiers locally. A collector will need the
account-scoped `Access: Audit Logs Read` permission; keep its token local.

Documentation and supported authentication-log API:
https://developers.cloudflare.com/cloudflare-one/insights/logs/dashboard-logs/access-authentication-logs/

Authentication logs cover login attempts, not actions later performed inside an
application. Do not demonstrate a download scenario without the relevant data logs.

## GitHub: identify the actual feed

The current connector reads activity events, not organization security audit logs.
Choose a repository you own for live testing. A future webhook integration must
verify signatures and deduplicate deliveries; never expose an unauthenticated receiver
for real production events. GitHub identity linking should preserve the numeric actor
ID and account/org context, not infer a person from a matching username alone.

## What to report back

- AWS: named non-root CLI profile works, and which region is used for test actions.
- Cloudflare: whether an Access application and real login log exist.
- GitHub: which owned test repository can generate demonstration activity.

No passwords, keys or tokens are needed in these answers. Until the application has
authentication and isolated account identities, keep development on localhost with
synthetic data. Real integrations and the first public deployment are separate gates.
