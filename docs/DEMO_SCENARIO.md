# Demo scenario L4: "Batch reporter goes rogue"

Persona-02 "Batch reporter" normally reads buckets p01-p03, 2-5 events a day, 09:00-12:00 and 14:00-18:00 MYT.
The demo shows it reading the confidential and unused buckets in the evening. **This is a demonstration outside
the controlled study**; it is never used as study evidence and never trains or tunes anything.

| # | Behaviour | Count |
|---|---|---|
| 1 | `GetObject fixture.txt` on `confidential` | 12 |
| 2 | `GetObject fixture.txt` on p04, p05, p06 | 6 each |
| 3 | `GetBucketLocation` on confidential, p04, p05, p06 | 1 each |
| 4 | `ListObjectsV2` on `confidential` (not permitted, AccessDenied expected) | 1 |
| 5 | Cloudflare `GET /workloads/persona-02/demo-<n>` | 8 |

Time: evening MYT (target 21:00-21:30), outside the persona's usual hours.

## A. Rehearsal now (simulated, separate copy)
```
$env:DATABASE_URL="sqlite-local"
python scripts/demo_scenario_sim.py --from data/live/live-v1-preview/preview.db --root data/live/live-v1-rehearsal
```
Copies the demo DB (only if its folder has a `not_live: true` marker) into a new root, writes a marker with
`rehearsal: true`, inserts the scenario rows (`event_id` = `sim-<uuid>`, metadata `{"simulated": true, "scenario": "L4"}`)
for the latest closed MYT day at 21:05-21:25, runs the baseline sync and prints the persona-02 scores.
Serve it on API 8018 / UI 3014 (never the live DB or the 8017/3013 demo); every page then shows an amber
`REHEARSAL - contains simulated events` bar. In the UI: Work queue (baseline finding for persona-02) and
Entities > Workloads > "Batch reporter (persona-02)" for the merged timeline.

Rehearsal result (v1.1 score, day of the simulated rows): AWS account-day 72 High (new_action 0.6, new_resource 0.889,
unusual_hours 1.0, volume 1.0, sensitive_new 0.0); Cloudflare token 35 Medium; workload group 82 High
(10-point cross-source bonus). Expected on 16 Nov: similar, not identical (history differs).

## B. Real run (owner, on or after 16 Nov 2026)
Why it is safe: persona-02's role is read-only on the lab's own synthetic fixture buckets (`s3:GetObject` on
`fixture.txt`, `s3:GetBucketLocation`; nothing else, so ListObjectsV2 is an implicit deny); the caller must be the lab
runner user; every S3 call sets `ExpectedBucketOwner`; hard caps 40 S3 calls, 2 STS calls, 8 Cloudflare requests;
the script aborts on the first unexpected error. No IAM, trail, token or policy is changed.

Dry run (default, zero network calls; prints the plan):
```
python scripts/demo_scenario_live.py
python scripts/demo_scenario_live.py --cloudflare
```
Live (refuses before `2026-11-16T00:00:00+08:00`, and without both flags):
```
python scripts/demo_scenario_live.py --live --confirm persona-02
python scripts/demo_scenario_live.py --live --confirm persona-02 --cloudflare [--cf-state <folder with pilot-config.json and persona-02.dpapi>]
```
AWS uses profile `argus-simulator` (`--profile` to change), AssumeRole session `argus-demo-persona-02`, 900 s,
order #3, #1, #2, #4, 2 s apart. Cloudflare is optional: 8 GETs 5 s apart with the persona-02 token loaded by the
existing DPAPI loader (`--cf-state` defaults to the lab setup's state folder in the checkout you run from). On
401/403 (token expired or not refreshed; the pilot token expiry is 14 Nov) only the Cloudflare part stops and the
AWS part stands.

Ledger: `data/live/demo-scenario/run-<utc>.json` (time, operation, bucket symbol such as p04/confidential, HTTP
status, error code, request id; no secrets, no account number).

Seeing it: events appear in CloudTrail after a delay, then in Argus after the next collection. Open Entities >
Workloads > "Batch reporter (persona-02)" and the Work queue for that day.
