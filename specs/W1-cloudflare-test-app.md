# W1: Access-protected Cloudflare test application

Date: 27 October 2026. Branch codex/w1-cloudflare-test-app, stacked on PR #7.
The user authorized CLI setup, granted setup token scopes and specified their
email as the sole allowed identity. Keep that personal address in runtime
configuration only, not in committed code or documentation.

Goal: provision a minimal Worker to generate real Access authentication events.
The Worker must fail closed unless ctx.access supplies an authenticated identity
whose email matches the configured address. A self-hosted Access application
protects its workers.dev hostname with a single exact-email allow policy. No
public Argus backend or customer data is deployed.

Implement a CLI defaulting to inspection, --deploy for changes. Read the existing
encrypted credential using Windows DPAPI without printing it. Check the account
identifier, list existing resources and obtain the workers.dev subdomain before
any mutations. Refuse to overwrite an existing same-name Worker or Access app.
If no workers.dev subdomain is registered, require --new-subdomain explicitly;
never rename an existing subdomain. Upload a Worker that denies requests without
Access context, create the restrictive Access app, and only then enable its public
workers.dev route. Disable preview URLs. Leave partial resources for inspection
on failure; no automatic destructive cleanup. API errors expose status/codes only.

Acceptance: mocked safety tests for inspect-only, preflight permission failure,
name collision and enable-last mutation order; Worker checks for missing/forged
headers, wrong authenticated email, allowed email and no credential/data leakage.
If deployment succeeds, unauthenticated HTTP request redirects to Access or denies
access, and the policy read-back confirms the exact-email rule. Actual login logs
require the user to sign in. No model/detection success claim from a login alone.

CI: add the isolated Worker authentication checks to the existing Node job;
Python provisioning checks run in the existing scripts/tests suite. No cloud
credential is required in CI and no deployment trigger is added.

Initial blocker: GET workers/subdomain returned HTTP 403/code 10000; the user's
token edit later became effective. Deployment and policy verification succeeded.
Public HTTPS and Access login redirects are verified, including a request with
a forged identity header. The approved user's actual login is still pending.
No paid subscription or new DNS zone. Human merges; no production app deployment.
