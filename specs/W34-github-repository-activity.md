# W34: native GitHub repository activity for the private workload lab

30 October 2026. Separate live-integration work; no W33 or frozen model changes.

## Observed problem and evidence

The commissioning commit exists and its Bot author ID is verified. Both owner
and App authentication returned an empty repository Events feed. The restricted
App can read `GET /repos/{owner}/{repo}/activity`; one native `push` activity
matches the exact commissioning commit and bot actor ID. This supplies real
provider evidence without creating another action or inventing a PushEvent.

## Contract

Use API version `2022-11-28`, already pinned by the App client. The actual observed
activity row contains integer id, activity_type, actor, timestamp, before, after,
ref and node_id. Repository context comes from the verified request and native
repository metadata (ID, full_name, private flag and owner ID), since the row
does not contain a repository. This context is attribution, not authentication
of arbitrary callers to the existing local API.

A dedicated `/ingest/github-repository-activity` endpoint validates this format.
It retains provider source `github_events` and native actor identity but marks
metadata `evidence_format=github_repository_activity_v1`. Internal receipt IDs
are `repository-activity:<native repository ID>:<native activity ID>`, preventing
collision with Events API IDs. The raw provider row and its native ID remain
unchanged. Time maps from timestamp, resource from verified repository context,
and action from native activity_type. IP and commit count remain unavailable.
Do not relabel this row as an Events API PushEvent or organisation audit log.

Original activity JSON is content-addressed and saved privately before ingest.
Only a matching committed receipt permits commissioning to become `ingested`.
Repeated identical activity returns duplicate; changed payload under that key
is a strict conflict. Failed/unknown receipts do not trigger a new commit.

## Count authority and boundaries

The private lab selects **repository activity only**, not a union of activity
and Events feeds. Its finite commissioning reconciler no longer ingests the
lab Events feed. The existing project-repository Events collector is unchanged
and does not poll the lab repository. Thus no action is counted twice by the
installed paths. The server does not claim a general cross-endpoint semantic
deduplication capability: enabling both feeds for the same repository would
require a separate tested authority/reconciliation design.

The shared GitHub source is for display/account attribution; frozen model input
compatibility is not implied. The new explicit Repository actions do not silently
become W23 native PushEvent features. No model activation or live risk tiers.
Six workload profiles under this single App remain one native bot account.

## Operational release

Back up and pause only affected owned jobs. Bind reviewed backend/collector/
reconciler changes and the new backend format helper, restart and verify backend
identity before collection resumes. Preserve all AWS study dates, persona plans,
budgets, ledgers and W33 files. After commissioning ingestion, disable its
finite watcher; it is not the recurring bot scheduler. A daily workload scheduler
still requires its own bounded plan, durable claims, tests and source binding.

Reference: [GitHub repository activities API](https://docs.github.com/en/rest/repos/repos#list-repository-activities).
