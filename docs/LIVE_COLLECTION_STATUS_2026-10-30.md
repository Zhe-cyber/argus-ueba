# Live collection check — 30 October 2026

Snapshot verified at 08:53 MYT. Counts below are stored observations, not numbers
of humans, normal training examples or complete provider histories.

| Source | Stored records | Latest operational evidence |
|---|---:|---|
| AWS CloudTrail | 2,828 | Successful 08:52 poll: 3 inserted, 3 acknowledged, no retained failures |
| Cloudflare Access | 3 | Human/machine collection healthy; first scheduled machine request today due 08:56, so no daytime action expected at this snapshot |
| GitHub | 70 | 69 prior Events records plus one real bot repository-activity record; project Events poll also successful |

Backend identity and reviewed source pins verified. AWS and Cloudflare scheduled
collection resumed after the controlled adapter release. No actor plan, study
date, model threshold, W33 file or live score was changed.

## GitHub round trip completed

The private bot commit was matched to a native repository activity by exact commit
SHA and bot actor ID, then ingested once. The dashboard API returns one matching
bot account with Unknown review priority and null AE score. Repeated native
receipts deduplicate; conflicting payloads fail. Original provider activity is
privately archived. No additional commissioning commit was created.

The lab collects repository activity only, so it does not count a later Events
API observation of the same push. Project repository collection remains on its
existing Events feed. This is not a claim of enterprise audit-log access or
general semantic deduplication. Source details are recorded in W34.

The completed finite commissioning watcher is disabled. **Recurring GitHub bot
workloads remain pending**: the successful round trip is a prerequisite, not
proof that a daily scheduler already exists. The next GitHub task is its separate
finite plan, durable claim/budget ledger, reconciliation and tests.

## Model and collection limits

Live scoring remains pending. No benchmark model was activated merely to populate
the dashboard. AWS setup/service traffic is included in total stored events;
the controlled-persona ledger and fitting exclusions remain separate.

The AWS ledger at 08:48 had 27 provider-verified actions and 7 missed actions
across its recorded history, including commissioning. These are not today's
success counts. Missed actions were not backfilled. At 08:52 no AWS persona
action was due. Cloudflare scheduled requests and provider receipt arrival are
separate stages; request success alone is not collection success.

Validation: 259 backend/related collector/pilot tests passed using isolated
synthetic SQLite data. A real native activity ingest and dashboard API check also
passed. Counts and states will change as the scheduled jobs run.

The frontend production build also passed, with the API explicitly compiled as
`http://127.0.0.1:8013`, and the owned frontend process was restarted. Source-card
wording is now GitHub, covering the two supported record formats. The read-only
headless analyst-workspace checks passed (source cards, account profile, alert
filters, escalation preview/cancel and retired demo redirect); no mutating
requests were sent. Next's build configuration skips lint/type validation, so
this is not a separate lint/type-check claim.
