# Q3 — Field-measured latency: CloudTrail → EventBridge → SQS (management events, default bus, free tier)

**Question (from research/QUESTIONS.md):** What do practitioners actually measure for the
`AWS API Call via CloudTrail` → EventBridge → SQS path (not just AWS's "seconds to ~2 min"
docs claim), and does it stay zero-cost at <1k events/day? Feeds W1-B's <60s success
criterion.

## Answer

No practitioner has published a rigorous, instrumented latency benchmark specifically for
**EventBridge** delivery of CloudTrail management events (the one hard measurement study
found — Tracebit, Nov 2023 — instruments CloudTrail→**S3** delivery, not EventBridge, and
that is a different, slower path already captured in LOG.md/R1). What exists instead is
consistent qualitative/anecdotal practitioner and AWS-official confirmation that the
EventBridge path is materially faster than the S3 path — "seconds to a couple of minutes"
from the event firing to a rule matching and dispatching — with no source reporting the
9–16 minute tail outliers that S3 delivery shows. The docs-level claim in UPGRADE_PLAN.md
R2 is therefore not contradicted by field evidence, but it is also not independently
*verified* by a controlled benchmark; it rests on AWS's own framing plus consistent but
informal practitioner corroboration. More importantly, this research surfaced three
**operational gotchas that are more load-bearing than the latency number itself**: (1) a
CloudTrail **trail must exist and be actively logging** — CloudTrail's always-on 90-day
Event History does *not* feed EventBridge; without an enabled trail, `AWS API Call via
CloudTrail` events never arrive on the default bus, regardless of latency; (2) by default,
EventBridge rules only match **write/mutating** management events — read-only calls
(`Describe*`, `Get*`, `List*`, and others) are silently excluded unless the rule state is
explicitly set to `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` (CLI/CloudFormation
only, not console); (3) global services (IAM, STS, Route 53, CloudFront) emit CloudTrail
events **only in us-east-1**, so a regional EventBridge rule outside us-east-1 will miss
IAM/STS activity entirely — relevant to Argus if login/role-assumption events are a
detection target. The zero-cost claim holds at <1k events/day: SQS's 1M-request/month free
tier and EventBridge's 14M-invocation/month free tier are both permanent (not
first-12-months-only) as of the pricing pages checked June–July 2026, so at Argus's demo
volume the EventBridge+SQS path costs $0; the CloudTrail trail itself is also free for the
first copy of management events per region. The only paid element in the whole chain would
be data events or a second trail, neither of which W1-B needs.

## Evidence

- AWS EventBridge docs, "AWS service events delivered via AWS CloudTrail" (checked
  2026-07-03, page reflects current console/API behavior): confirms `AWS API Call via
  CloudTrail` requires "an active trail" — "To record events with one of the CloudTrail
  `detail-type` values, you must enable a CloudTrail trail with logging." Also states
  write/mutating management events are matched by default-`ENABLED` rules, while read-only
  management events require rule state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`.
  https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail.html
- AWS EventBridge docs, "Receiving read-only management events from AWS services" (checked
  2026-07-03): explicitly confirms read-only events (e.g., IAM `GetPolicy`/`GetRole`, KMS
  `GetKeyPolicy`/`DescribeKey`) are excluded from default-enabled rules and lists the CLI
  flag needed; notes the CLI/CloudFormation-only restriction (no console toggle).
  https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail-management.md
- AWS re:Post, "What EventBridge gets from CloudTrail?" and "Eventbridge trigger with cloud
  trail event" (community answers, retrieved 2026-07-03, undated but current per AWS
  support engineers active on the thread): consensus answer — "CloudTrail events that are
  captured by any of your configured trails in the region are delivered to EventBridge...
  events not recorded by any of the trails you've configured do not get delivered." I.e.
  CloudTrail's built-in Event History alone (no trail) is insufficient.
  https://repost.aws/questions/QUpD2vMmXFSSWv2CPdZiaRSg/what-eventbridge-gets-from-cloudtrail
- AWS re:Post, "Why Does CloudTrail Take 10-15 Minutes to Log IAM User ConsoleLogin
  Failures?" (thread exists and is indexed; full body blocked by 403 on direct fetch,
  content read via search snippet, 2026-07-03): reports a **practitioner-observed 10–15
  min delay** for a specific case (failed IAM console login events reaching Event
  History/CloudWatch), materially worse than the "seconds to ~2 min" EventBridge framing.
  This is CloudTrail→Event-History/CloudWatch, not confirmed to be the EventBridge path
  specifically — treat as a caution flag, not a refutation, until the full thread can be
  read (site blocks scripted fetch; would need manual/authenticated retrieval).
  https://repost.aws/questions/QUdsbji-puTLGizEfUyStfbA/why-does-cloudtrail-take-10-15-minutes-to-log-iam-user-consolelogin-failures
- Tracebit blog, "How fast is CloudTrail today? Investigating CloudTrail delays using
  Athena" (Sam Cox, dated 2023-11-27 — the most rigorous instrumented measurement found,
  now ~32 months old): CloudTrail→**S3** delivery average ~2.5 min, P95/P99 just over 5
  min, max outliers >16 hours, <1-in-3,000 events delayed >10 min. Explicitly does **not**
  measure EventBridge delivery — only S3. This corroborates the existing LOG.md/R1 finding
  (S3 path unsuitable for <60s) but does not directly answer Q3's EventBridge question.
  https://tracebit.com/blog/how-fast-is-cloudtrail-today-investigating-cloudtrail-delays-using-athena
- AWS CloudTrail FAQ (checked 2026-07-03): "Typically, CloudTrail delivers an event within
  5 minutes of the API call" — this is the general/S3-oriented claim, not EventBridge-
  specific; confirms first-trail management events are free per region.
  https://aws.amazon.com/cloudtrail/faqs/
- Practitioner blog/tutorial consensus (OneUptime "Detect Unauthorized API Calls with
  CloudTrail and EventBridge", dated 2026-02-12; multiple similar Medium/dev.to guides on
  ConsoleLogin detection via EventBridge, non-dated but referencing current console UI as
  of searches run 2026-07-03): repeated informal claim that EventBridge-based detection is
  "seconds to a couple of minutes" from API call to alert — consistent with, but not an
  independent verification of, AWS's own docs framing. No source in this category
  published a controlled before/after timestamp measurement.
  https://oneuptime.com/blog/post/2026-02-12-detect-unauthorized-api-calls-with-cloudtrail-and-eventbridge/view
- Amazon EventBridge quotas doc (checked 2026-07-03): default 300 rules/event bus, hard
  ceiling 2000/bus (raisable via Service Quotas), 5 targets/rule — irrelevant at Argus's
  scale (a handful of rules) but confirms no free-tier-specific quota restriction applies.
  https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-quota.html
- AWS SQS pricing page + EventBridge pricing page (checked 2026-07-03): SQS free tier is
  1M requests/month, **permanent**, not restricted to account's first 12 months, applies
  across all queue types and is aggregated across regions. EventBridge free tier is 14M
  invocations/month, also permanent, global allowance (excludes GovCloud). At <1k
  events/day (~30k/month) Argus is roughly 3% of the SQS free-tier ceiling and <1% of the
  EventBridge ceiling — comfortably zero-cost with wide headroom.
  https://aws.amazon.com/sqs/pricing/ ; https://aws.amazon.com/eventbridge/pricing/
- AWS CloudTrail pricing / cost-management docs (checked 2026-07-03): first copy of
  ongoing management events delivered to S3 is free per region; a second trail in the same
  region, or additional org-trail copies, cost $2.00/100k events; data events are never
  free (no first-copy exemption). W1-B only needs one management-events trail → free.
  https://aws.amazon.com/cloudtrail/pricing/ ; https://docs.aws.amazon.com/awscloudtrail/latest/userguide/cloudtrail-trail-manage-costs.html

## Impact on Argus

- **The <60s W1-B success criterion is plausible but should be stated as "typically" not
  "guaranteed."** No source contradicts the "seconds to ~2 min" framing for the
  EventBridge path, and it is clearly faster than the already-rejected S3 path. But because
  no one has published a controlled, timestamped EventBridge-specific benchmark, and one
  re:Post thread reports a 10–15 min delay for a related (though not confirmed identical)
  CloudTrail path, the plan should hedge: keep <60s as the target/demo expectation, but do
  not present it in the paper/viva as an AWS SLA — it is not one, and none of R2's own
  wording implies it is (good — no change needed there). Recommend adding a footnote in
  UPGRADE_PLAN.md/paper: "informal practitioner reports and AWS's own framing both describe
  seconds-to-low-minutes; no controlled benchmark exists as of mid-2026."
- **New required build step, not currently flagged in UPGRADE_PLAN.md as far as this
  research saw:** W1-B's EventBridge rule needs an **enabled CloudTrail trail** in the
  target region — the account's default Event History is not sufficient. If the AWS
  free-tier demo account doesn't already have a trail, this is a one-time setup item to
  add to the Stage B implementation checklist (specs/ or the executor's task list), not a
  design change.
- **Read-only event coverage decision needed.** If any Argus detection scenario depends on
  read-only calls (e.g., reconnaissance-style `ListUsers`/`GetSecretValue`/`DescribeKey`
  patterns — plausible for an insider-threat UEBA), the default EventBridge rule state
  will **silently drop them**. This needs an explicit decision: either accept
  write-events-only coverage for the MVP (simpler, matches most "account compromise"
  detection use cases which are mutating actions anyway) or set
  `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` via CLI (console doesn't support it) and
  accept higher event volume from noisy read-only calls (KMS/IAM Describe/Get/List). Given
  Argus's low-volume free-tier target, recommend defaulting to write-events-only for W1-B
  and noting the read-only limitation as a known scope boundary in the demo script.
- **Region binding for IAM/STS events.** If W1-B's demo scenario includes a console
  login or role-assumption event (likely, since that is the canonical insider-threat demo
  action), the EventBridge rule and trail must be in **us-east-1**, because global-service
  CloudTrail events (IAM, STS, Route 53) are only emitted there regardless of which region
  the trail is created in. Worth a one-line check in the Stage B setup script/spec.
- **Zero-cost claim confirmed, no change needed to plan's cost assumptions.** SQS and
  EventBridge free tiers are both permanent and comfortably cover <1k events/day; the one
  CloudTrail trail needed is free for first-copy management events. No paid resources
  required for W1-B at Argus's volume.

## Confidence

**Medium.** High confidence on the *mechanics* (trail requirement, read-only exclusion,
region binding for global services, free-tier cost ceilings) — these are drawn directly
from current AWS documentation, cross-checked against independent re:Post community
consensus, and internally consistent. **Lower** confidence specifically on the *numeric
latency claim* itself: no controlled, dated, EventBridge-specific benchmark was found (the
one rigorous benchmark — Tracebit — measures the S3 path, and it's already 32 months old
against the "recency <18 months" bar this protocol asks for). What would raise this to
high: a 2025/2026-dated blog or re:Post thread with explicit before/after timestamps for
the EventBridge (not S3) delivery path, or running our own timed test against the AWS
free-tier account once W1-B is built (cheap and fast — recommend the evaluator agent do
this as part of Stage B validation rather than trusting docs/anecdote further). What would
lower it: if our own measurement during W1-B build-out shows delivery times clustering
above 60s, which the CLI docs' vague "seconds to a couple of minutes" language does not
rule out.
