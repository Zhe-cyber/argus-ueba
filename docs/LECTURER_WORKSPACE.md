# Lecturer workspace, 30 October 2026

Local UI: http://127.0.0.1:3000. Owned pilot API: http://127.0.0.1:8013.
This release is local only. No public deployment, live AE activation, new cloud
permissions or changes to the frozen AWS method, actor profiles or ledger.

30 October refinement: operational overview and compact alert table replace
presentation-style workflow panels. Methodology, source coverage and scoring
explanations are collapsed under Details/About signals. Alert status is editable
in each row; evidence expands per row; investigation review remains explicit.
The redundant unscored summary cards are omitted when the live AE is unavailable;
the status and each account's Unknown priority remain visible. Frontend-only
refinement verified by production build and read-only browser checks; no backend
or collector restart/change was needed.

## What to show

1. Connected activity: real persisted AWS CloudTrail, Cloudflare Access and
   GitHub Events counts, account references and latest event/receipt times.
   Counts include workload identities and do not mean independent human users.
   Evidence receipt is deliberately not labelled collector health or completeness.
2. Alert review: separate rule signals, account observations and AE alerts.
   Inspect recorded evidence and filter by origin/status. Severity is a review
   cue, not a probability or proof of compromise. First-seen account alerts are
   observations, not detections of malicious behaviour.
3. Investigate: review the selected alert before creating/linking a case.
   Escalation acknowledges the alert; preserves case owner/notes; repeated
   escalation does not append the same note again. Closed alerts/cases require
   explicit reopening. Escalation sends no external notification or cloud action.
4. Benchmark model evidence: existing validated, aliased CLUE10 replay only.
   Its held-out normal partition is 191 account-days: 185 Low, 4 Medium, 2 High
   review priorities. Thresholds and reconstruction evidence are visible.
   These are real frozen-model outputs, previously inspected development
   evidence for later model changes. This is NOT the new shared-core candidate,
   a live model, or real attack detection accuracy.

The live accounts remain unscored because no compatible live model is released.
The five-feature shared-core work is still a draft/implementation task. Do not
present the UI refresh as successful live transfer or a new trained model.

## Cleanup and operation

Demo Lab navigation and its synthetic injection UI are retired; /demo redirects
to /. Removed bulk High-risk quick-start case creation from the normal workflow
and demo-page guidance from empty event feeds. No historical events or alerts
were deleted or relabelled. Unscored live views omit misleading zero High/Low
summary cards; account evidence remains accessible.

Monitoring endpoint: GET /monitoring/overview, read-only aggregated stored events
and active alert-origin counts. It exposes no account IDs or raw payloads.
Unknown legacy alert types remain unverified, rather than guessed as rules/AE.
Current sources have 26 rule signals, 14 observations and 0 AE alerts at release;
these counts naturally change with new ingested activity.

Backend/collector tasks were paused for verified source-pin updates and resumed.
Source-pin scope: backend/main.py, backend/event_store.py and scripts/local_pilot.py.
The optional offline_replay_dir only permits this checkout's existing validated
data/processed/clue-replay-v1 bundle and does not enable live inference.
Private pre-release config backups remain beside the pilot config. The dashboard
is a hidden local Next production process, not a newly installed startup task;
its lifetime is separate from the existing pilot tasks. UI process/log files:
data/live/dashboard-w24/. Do not share full account/alert screenshots publicly
without reviewing identifiers. Source-overview crop contains aggregate counts.

## Verification

- Backend regression: 175 passed, forced DATABASE_URL=sqlite-local; temporary
  SQLite/investigation state only. Includes source-summary provenance, case-note
  preservation, repeated escalation and closed-case/alert rejection.
- Frontend production compilation and page generation passed. Next build skips
  lint/type validation under the repository's existing configuration.
- Fresh headless Chrome checks: source cards, no Demo Lab navigation, origin
  filters, investigation review/cancel, retired route redirect, no page errors.
- Existing replay browser checks: priority totals, filters, calibration labels
  and numerical evidence. Live stats unchanged; no browser writes to pilot state.

Reviewed source remains uncommitted for the user to commit. Do not stage private
data, models, screenshots, local config or update.md. Existing AWS commit cutoff
and rehearsal dates still apply; this release does not freeze the CLUE protocol.
