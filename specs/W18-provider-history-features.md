# W18: Cloudflare and GitHub descriptive history profiles

Written 29 October 2026. Specification only; extraction and scoring are not implemented by this document. User commits and pushes manually.

## Goal
Prepare provider-specific daily histories from collected native events without interpreting missing fields as benign values or claiming authentication monitoring from repository events.

## Evidence from current code
- scripts/collect_live.py collects Cloudflare Access requests for one approved app, rejecting records without an email or a boolean allowed outcome.
- GitHub collection uses the owned/administered repository Events API, page 1 with at most 100 events. This is not an organization audit feed and provides no sign-in or source-IP coverage.
- Both collectors filter a 24-hour interval; successful polling does not establish complete provider coverage. Polling gaps and response limits can omit events.
- Correction after inspecting backend/event_store.py: normalisation returns raw in memory, but the database persists only normalised fields and the native payload digest, not the raw payload. A digest does not recover missing fields or verify the stored projection independently.
- Cloudflare allowed is not a dedicated normalized metadata field. Exact future extraction needs additional durable evidence; never treat a display suffix as a native boolean.
- Old GitHub action labels may incorrectly say zero commits. Use valid stored metadata.commits where present, never infer a count from old labels or a commits array.

## Proposed new contracts
Use independent versions cloudflare_access_daily_v1 and github_activity_daily_v1. Neither is compatible with AWS-lab, legacy12, CERT71 or CLUE model artifacts.
One observation is one provider-scoped account on one CLOSED Asia/Kuala_Lumpur date. Never create an all-zero normal row from an empty or missing day. Treat today's activity separately as partial.

### Cloudflare: six ordered descriptive counts
1. event_count: distinct native Access requests.
2. allowed_count: requests with raw.allowed exactly true.
3. denied_count: requests with raw.allowed exactly false.
4. unique_apps: distinct nonempty raw.app_uid values.
5. unique_valid_ips: canonical distinct IPv4/IPv6 addresses.
6. off_hours_events: requests outside weekday 08:00 inclusive to 20:00 exclusive MY; a descriptive convention, not a suspiciousness verdict.

Require allowed_count + denied_count = event_count. Report invalid outcomes instead of converting them to allowed. Missing/invalid IPs have separate counters. Countries have separate present/missing/invalid counters; an unknown country is not a country category. The six counts do not include geo-rarity or IP novelty.

Sidecars: raw action distribution, app distribution, local-hour distribution, observed valid IP/country categories with missingness, and stable source-scoped account references. IP categories remain private. No inferred in-app actions, session length, device identity or MFA strength.

### GitHub: eight ordered descriptive counts
1. event_count: distinct native repository events.
2. push_count: raw.type == PushEvent.
3. pull_request_count: raw.type == PullRequestEvent.
4. issue_count: raw.type == IssuesEvent.
5. issue_comment_count: raw.type == IssueCommentEvent.
6. ref_change_count: raw.type in CreateEvent or DeleteEvent.
7. unique_repositories: distinct nonempty raw.repo.name values.
8. off_hours_events: same MY descriptive convention.

Other event types remain in event_count and a type-count sidecar. No security severity is assigned to event types. Comment/PR counts measure events, not unique objects or coding productivity.

Sidecars: event-type/repository/hour distributions, push counts with known/unknown commit totals, sum of known commit counts and its explicit denominator. Omit a total-all-pushes commit count unless every push count is known. GitHub IP, country and login evidence are unavailable, never numeric zero features.

## Identity and provenance
Partition by provider + source_account_id + stable native actor ID where present. Cloudflare user_id and GitHub actor.id are scoped native IDs; fallback to a labelled source-scoped email/login only when necessary. Record the key basis; never silently join an ID-less history to an ID-based history. Future merges require an explicit audited mapping.
Keep human, bot, controlled workload and unknown provenance separate. A bot suffix is a hint, not verified human/bot attribution; preserve native type if available. Do not present multiple AWS roles as independent people or auto-link actors by similar display names/email alone.
Cross-provider mappings require verification or analyst approval with validity dates and evidence. Linked timelines may show source activity; a unified risk score needs its own validated aggregation method.

## Coverage and future baseline eligibility
Keep observed_activity, partial_day, gap_detected, bounded_sample and no_observation distinct. Include poll success/failure timestamps, first/last native timestamps, rejection/missingness counts, queried scope, requested limit and cap-hit indicators where observable. A response at the limit signals possible truncation; below the limit does not prove completeness.
The current poll ledger is operational evidence, not a complete historical completeness certificate. Missing collection telemetry remains unknown. Do not grant the AWS planned-action 90% gate to unscheduled genuine activity.
Initial delivery is descriptive history only, with no review-priority assignment. Before a scoring experiment, preregister disjoint chronological fit/validation/calibration/test dates, method, alert budget, per-account active-day/event minima, required field coverage and acceptable collection gaps. Freeze these before inspecting reserved evaluation outcomes. Existing history is development data. Small samples and constant features can require no-go.
Do not reuse the AWS role study's dates, feature vectors or thresholds as evidence of Cloudflare/GitHub detection. With one active human account, describe an individual-account case study; peer baselines and multi-user performance remain unsupported.

## Implementation acceptance checks
- Standalone read-only export; no backend runtime edits, new cloud resources, extra provider calls, automatic schedule changes or model activation.
- Count native IDs once within source/account scope; retain provenance and raw-evidence hash bindings.
- Reject invalid/zoned-less timestamps and mixed-account/day inputs; count and report exclusions.
- Missing IP/country/commit values stay missing; explicit zero commit count remains known.
- Local midnight, weekend, invalid IP, duplicate native ID, bot/unknown provenance and partial-day cases have focused tests.
- Same counts across two accounts can coexist with different categorical histories; extraction never invents ownership or novelty.
- Verify source database unchanged; public output excludes raw emails, IPs, account IDs and repository names unless explicitly approved.
- Freeze contract bytes/hash when extraction is implemented; scoring requires a separate prospective protocol and evaluation.

## Next implementation slice
Implement a separate github_projection_daily_v1 read-only exporter first, using only persisted evidence. Its eight counts are event_count, push_label_count, pull_request_label_count, issue_label_count, issue_comment_label_count, ref_change_label_count, unique_repositories and off_hours_events. Action categories are explicitly inferred from stored normalizer labels, not recovered native event types. Report unclassified labels and missing commit evidence. This does not implement github_activity_daily_v1 or Cloudflare native-outcome features.

Use keyed aliases for account/repository references; do not export names or the alias key. Bind the exported projection snapshot and individual evidence references to hashes, while marking raw verification unavailable. Closed observed days remain bounded samples with unknown completeness, not baseline-qualified normal days. Current days are counted separately and excluded from the daily dataset. Refuse future timestamps, invalid identities/timestamps/digests and conflicting native keys; report exclusions. Output into a fresh directory and open SQLite mode=ro/query_only in a consistent transaction.

29 October review amendment: implemented projection contract is now github_projection_daily_v2. Exclude PR review from the PR-event label count; preserve the initial v1 development artifacts and producer bytes. Descriptive scope only remains the competition deliverable for this source. Hosted webhooks and native-evidence migration are deferred pending completion of the AWS critical path.

Inspect availability and missingness, then decide whether a prospective scoring study is supportable. Do not manufacture frequent sign-ins or repository changes merely to meet an eligibility gate.
