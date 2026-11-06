# W30: dedicated GitHub workload App setup

30 October 2026. User selected a dedicated App/bot rather than personal-account
automation. This step prepares authentication; it does not enable workloads.

Dedicated repository: private `Zhe-cyber/argus-activity-lab`. Project repository
and user-controlled project commits are untouched. App is owner-only, requests
Contents write and Metadata read, has no active webhook or user OAuth flow.
Human creates/installs it through the GitHub manifest flow, selecting only the
lab repository. Local helper verifies the account and exact installation scope
before reporting installed_verified. No bot or person identity is invented.

Helper: `scripts/github_lab_app.py serve`, loopback 127.0.0.1:8774, 30-minute
expiry, random registration state verified on both callbacks, strict Host,
no access logs, no-store/no-referrer responses. Public form contains requested
configuration only. Manifest conversion code and returned secrets are never
printed or logged. Complete conversion response is written once under current-
user Windows DPAPI before validation; no plaintext fallback/overwrite. Any
failed conversion or binding requires inspection, not automatic re-registration.

App JWT uses RS256 with 8-minute expiry and 60-second clock allowance. Installation
tokens are requested with one repository ID and Contents/Metadata permissions,
remain in memory, and are never printed or saved. Repository/privacy/owner,
app ID, selected-repository mode, suspension and permissions are checked. A
separate metadata-only installation token verifies the inventory contains just
the lab repository. JWT and manifest keys are parsed and locally verified.
No added JWT dependency.

Tests cover manifest permissions, cryptographic JWT verification/expiry, owner
and scope rejection, encrypted-only writes/refusal to overwrite, and one-repo
installation-token requests. Four focused tests passed; a real Windows DPAPI
round-trip and loopback form GET also passed before asking the user to register.
At that initial checkpoint browser approval/install was pending. See the
completion update below for subsequent verified operations.

Next after installation: verify one bot-authored toy change and native event
collection before any task installation. Six workload profiles under one App
remain **one native GitHub bot account**, not six independent users. Preserve
controlled-workload provenance and freeze the new schedule/ledger separately
from the existing AWS study. No live score/model activation.

Private state: `data/live/github-app-lab-v1/` (ignored). No private key, token,
manifest conversion response or authorization code belongs in Git/review text.
The user can stop the short-lived helper without stopping the original pilot.

Reference: [GitHub App manifest flow](https://docs.github.com/en/apps/sharing-github-apps/registering-a-github-app-from-a-manifest).

Registration correction: GitHub rejected the initial loopback webhook URL even
with the hook inactive. The hook URL now names the existing public, Access-
protected test Worker, while remaining inactive with no subscribed events.
The browser registration/setup redirects remain loopback. No Argus API was
exposed or new public endpoint deployed. Tests now reject a loopback hook URL.

## Installation and commissioning update

The user's installation succeeded on the single private lab repository. The
first verification callback failed because the CLI OAuth token could not use
the App-user installation-inventory endpoint. Verification now uses a metadata-
only installation token, confirms exactly one repository, then validates the
repository-restricted Contents token. No reinstall or secret transfer required.

One labelled toy-file commit was created by the App, with native REST commit
metadata confirming the expected Bot actor ID/login. Its native PushEvent has
not appeared in the repository Events API yet; no substitute event was inserted.
The explicit commissioning claim prevents any second commit on retry. Reconcile
matches repository ID, native bot actor and exact commit SHA, preserves the
provider ID/time/payload, and only marks success after the local ingest receipt.

Nine focused tests passed. In addition to setup tests, they verify bot identity,
strict native-event matching, no repeat after an existing claim, no fabricated
event while the feed is empty, exact forwarding and no duplicate after success.

A separate short-lived checker may poll native events every five minutes for
up to six hours, with hashed sources and no action-generation path. It is not
the recurring persona workload. Workload scheduling remains disabled until
the round trip is verified. Existing AWS study/runtime source pins are unchanged.
