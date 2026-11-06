# W20: Daily pilot coverage check

29 October 2026. Standalone read-only operational check; no provider calls, scoring, backfill or edits to pinned runtime. User commits/pushes manually.

- Reuse V2 readiness evaluator; distinguish future/current dates from incomplete closed dates. Summarize yesterday's study roles and ALL incomplete closed study days.
- Current tick freshness limit 15 minutes; GitHub/Cloudflare poll limit 75 minutes. Failed/future/missing timestamps are explicit. No observed SaaS activity alone is not failure.
- Count yesterday's scoped stored events separately from polling health. Parse aware native times. Bound reads; no raw identifiers in reports.
- Yesterday's tick journal reports gaps/failures but never proves completeness; missing telemetry stays unknown. Warm-up and reserved cases never become normal observations.
- Private versioned JSON snapshots, atomic latest.json, safe last_attempt.json failure marker preserving previous report. No model release decision.
- Separate source-pinned task config. Reject drift. New owned Argus-Pilot-Daily-Check runs hidden, current-user interactive, daily 08:15 MY and at logon, StartWhenAvailable/IgnoreNew. No password/network requirement/wake/global power changes. Expire 15 November 00:00 MY; script enforces expiry.
- Synthetic tests cover freshness, missing/failed telemetry, legitimate zero activity, historical/future days, journal bounds and read-only DB behavior. Verify real report and existing pilot health. Never replace existing tasks.
