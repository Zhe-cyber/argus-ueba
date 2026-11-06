# Daily pilot coverage

The standalone checker makes no provider calls, runs no actors, changes no source data and assigns no risk score. Its Windows task is separate from the backend/collector.

## Schedule and private output

Task Argus-Pilot-Daily-Check runs at 08:15 Asia/Kuala_Lumpur and at current-user logon. StartWhenAvailable catches a missed daily trigger after the laptop resumes, subject to Windows scheduling and the task expiry. It is interactive, least privilege, hidden, IgnoreNew, with no Windows password saved and no wake/network requirement. It does not keep the laptop awake or send notifications. The user must review its report; operational warnings do not repair missing collection. A successful task exit means the report was generated, not that all coverage gates passed.

Task triggers and the script expire at 15 November 2026 00:00 MY. They do not modify existing pilot tasks, global power settings or Windows Update. At-logon checks may precede collector startup; recheck after the collector settles if freshness is temporarily unknown.

Private local output is under the existing live data root, daily-pilot-check-v1:

- config.json: separate checker dependency hashes and pilot config path.
- latest.json: latest successfully generated report; always check its computed_at_utc.
- last_attempt.json: latest attempt success/failure. A failed check preserves the older latest report and explicitly marks it potentially stale here.
- Unique timestamp/UUID JSON snapshots and the installed task XML.

Do not share the whole private config/data directory. Reports omit raw account IDs, emails, IPs and provider errors; even pseudonymous role/activity metadata deserves review before publication.

Manual recheck from the active checkout with the existing Python environment:

    python scripts/daily_pilot_check.py --config <private-live-root>/daily-pilot-check-v1/config.json

## Interpretation

- Collector tick older than 15 minutes, or GitHub/Cloudflare poll older than 75 minutes, requires review. Failed, invalid and future timestamps remain explicit. A newer collector failure marker overrides an otherwise fresh completed tick's apparent success.
- Yesterday's source activity is separate from poll health. Zero Cloudflare/GitHub activity can be legitimate. Observed account references are not a count of independent people. Counts include source-scoped stored activity, not only ordinary AWS persona actions.
- AWS readiness comes from the existing native-receipt audit: each closed study role/day requires at least 90% verified planned actions and no unresolved receipts. Report all incomplete closed study days, not only yesterday. Today's partial and future days do not become failures or normal zeros.
- The historical tick-journal gap check covers 08:00–20:00 MY, including the active-window boundaries. Overnight silence is excluded. Malformed/missing journals stay uncertain; observed ticks never prove source completeness. Dates outside the pilot collection period are not retroactively required to have full journals.
- Warm-up, setup and reserved scenarios are not normal study days. The checker does not evaluate their detection outcomes.
- History minimums passing is not model approval. Training, stricter model-specific gates, prospective evaluation and release remain separate.

The checker reads separate ledger/native/telemetry snapshots. Late receipts and concurrent collection can change the next report; it does not lock or pause the collector. It bounds native rows and journal sizes, refuses source drift and preserves old reports on audit failure. A source change requires deliberate review and checker repinning, not an automatic refresh.

First installation on 29 October: scheduled run completed with TaskResult 0, operational_checks_pass, history_pending. Fitting has not started; yesterday was outside normal study windows. Existing backend identity and source pins remained healthy. Verification: 201 isolated coverage/readiness/backend tests passed.
