# Source-scoped account identities, 30 October 2026

Local pilot enabled contract: source-principal-v1. This is account attribution,
not person verification or cross-provider identity linking.

Internal keys are SHA256 of version, source, collection namespace, native owner,
principal kind and native ID, prefixed acct_. Labels are separate. The hash is an
opaque key, not a claim of anonymisation. No email/name equality links accounts.

| Provider | Native identity basis |
|---|---|
| AWS IAM user | principalId, scoped by source namespace and identity account |
| AWS assumed role | sessionIssuer principalId; otherwise explicit AssumedRole AROA prefix |
| AWS root | root principal in its AWS owner/collection scope |
| AWS service | invokedBy service principal in scope |
| GitHub | numeric actor_id, in the recorded collection namespace |
| Cloudflare | user_id, in the recorded account namespace |
| Cloudflare service credential | native Client ID in an explicit nonidentity Access log; distinct service_token kind |

Role sessions group under the role, not a verified person. GitHub collection
namespaces currently follow the configured repository; the same actor monitored
under different collection namespaces remains separate pending explicit mapping.
GitHub bot-looking labels are not proof of account type. Missing native ID or
namespace leaves an event unattributed, never a guessed person/account.

## Storage and runtime

Additive event columns: account_key, account_label, account_kind, account_basis;
indexed account_key. Original user, source namespace, metadata, timestamps,
native IDs, payload digests and pipeline receipts are retained unchanged.

Cloudflare machine logs observed on 30 October carry the Client ID in
`user_email` and an empty `user_id`, with `connection=nonidentity`. The parser
preserves that native value as `service_client_id`; this is not a human email
or an invented user ID. Machine keys include the service_token kind and
`cloudflare_service_client_id` basis. Explicit nonidentity without a supported
native client ID stays unattributed, even if a user_id is supplied. Service
credentials cannot be approved into human identity mappings. New ingestion
also preserves explicit allowed outcomes; earlier stored records are not
backfilled or reinterpreted as having an outcome they did not retain.
In enabled mode, history, rolling rules, live-score keys, account enumeration,
source counts and native case references use scoped keys. Human-readable labels
are returned separately. Unknown legacy references reject ambiguous resolution
with HTTP 409. Existing benchmark/default compatibility mode is unchanged.

Unattributed events are retained and receipted without creating a fake account,
model score or account-specific alert. Existing unqualified live-score rows are
retained but not reinterpreted as scoped scores. Migrated accounts without a new
scoped score remain Unknown; no model is activated or automatically calibrated.

Explicit pilot option account_keys=source-principal-v1 sets ARGUS_ACCOUNT_KEYS.
No AWS actor profile, native-study selector, method, schedule or credential scope
was changed. Frozen study exports still read original native event fields.

## Local migration outcome

- Backed up config, SQLite events and case state before changes.
- Backfilled all 2,796 existing events from stored native metadata; 0 unattributed
  at migration time. Original-field digest and row count unchanged.
- 15 native accounts: AWS 12, GitHub 2, Cloudflare 1. The old count was 14:
  distinct AWS services previously shared an empty display identifier.
- Mapped 38 alerts where the former reference resolves to exactly one key.
  The prior user reference is retained in alert details under identity_migration_v1.
- Kept 2 ambiguous legacy alerts unchanged. They are unresolved identity signals;
  they are not assigned to a guessed account or escalated into a mixed case.
- Renamed one uniquely matched legacy case key. Owner, notes, status, creation
  and update timestamps and complete history are byte-equivalent as JSON values.
  Conflicting case destinations or many-to-one case candidates are never merged.

Migration command: scripts/migrate_account_keys.py. Local SQLite only, explicit
state/output paths, optional --migrate-unique-cases, additive/idempotent mapping.
Private reports and backups: data/live/account-key-release-v1/.
Counts above are release-time observations and increase with collection.

## Verification and recovery

187 backend tests passed with DATABASE_URL=sqlite-local. Includes scope/name
collisions, native-ID rename continuity, role-session grouping, missing identity,
history/rule isolation, replay deduplication, immutable native evidence, migration
idempotence, ambiguous escalation rejection and case merge refusal.
Frontend production build and fresh headless Chrome checks passed, including a
scoped profile's label/identity basis. All 15 profiles and recent feeds were also
read-checked for source isolation. No browser writes were sent to pilot state.

Owned backend and collector were paused, source pins updated for the reviewed
files, health verified and collection resumed. The UI remains loopback-only.
Do not blindly restore the pre-release database after collection resumes: that
would discard newer evidence. A rollback would require a paused, reviewed reverse
reference migration or reconciliation with the backup. No rollback was performed.

Source remains uncommitted for user review/commit. Private data and update.md
remain outside the commit. No live AE activation or approved human identity map
is implied by this release.
