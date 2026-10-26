# W1: Cloudflare CLI authentication and inspection

Date: 2026-10-27. Stacked on codex/w1-aws-cli-setup.

The user completed Zero Trust Free enrollment and requested CLI/API operations.
Wrangler 4.153.0 offers Workers OAuth scopes but no Access audit-log scope.
No Cloudflare credentials were found locally. A user-created API token is needed.

Implement a Windows PowerShell helper that accepts a token only via a masked local
prompt, verifies it with Cloudflare, and saves it using Windows current-user DPAPI
outside the repository. Never accept tokens in command-line arguments, print them,
or edit .env. Default operation only reads application and identity-provider counts
and a bounded sample of authentication logs; no app deployment or policy mutation.
Account IDs must be 32 hex characters. Network errors must not dump responses or
request headers. Inspection failures must produce a nonzero exit status.

For this initial inspection request account-specific Apps Read, Identity Providers
Read and Audit Logs Read. Future provisioning requires separate explicit setup
permissions; the eventual collector must have only Audit Logs Read.

Acceptance: PowerShell parser succeeds; invalid account fails before network or
credential writes; mocked API calls verify output redaction and missing permission
failure; no secrets tracked. Live inspection awaits the user's local authorization.

Non-goals: publishing Argus, DNS changes, paid subscriptions, ingesting logs before
server deduplication, treating authentication logs as in-session activity.
