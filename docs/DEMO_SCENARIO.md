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

## B. Real run (owner, on or after 14 Nov 2026; superseded by section C)
Why it is safe: persona-02's role is read-only on the lab's own synthetic fixture buckets (`s3:GetObject` on
`fixture.txt`, `s3:GetBucketLocation`; nothing else, so ListObjectsV2 is an implicit deny); the caller must be the lab
runner user; every S3 call sets `ExpectedBucketOwner`; hard caps 40 S3 calls, 2 STS calls, 8 Cloudflare requests;
the script aborts on the first unexpected error. No IAM, trail, token or policy is changed.

Dry run (default, zero network calls; prints the plan):
```
python scripts/demo_scenario_live.py
python scripts/demo_scenario_live.py --cloudflare
```
Live (refuses before `2026-11-14T00:00:00+08:00`, and without both flags):
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

## C. Evaluation scenarios S1-S4 (L8; rules in specs/L7-live-evaluation-rules.md section 2)
`demo_scenario_live.py --scenario S1|S2|S3|S4` (default S1, dry run). Live also needs `--confirm <persona>`
(S1 persona-02, S2 persona-05, S3 persona-04, S4 persona-06), a date on or after 14 Nov 2026 MYT and the whole run
inside its window (S1/S2 21:00-22:00 MYT, S3/S4 10:00-17:00 MYT); the earliest date is now 14 Nov 2026. S3 caps: S1 40, S2 5, S3 1, S4 30; STS 2;
Cloudflare (8 requests) is S1 only. Ledger: `data/live/demo-scenario/run-<scenario>-<utc>.json`.

Schedule (L7 section 2): no earlier than 14 Nov 2026 and only after the rules were sent to the supervisor; at most
two scenarios per Malaysian day on different personas. Planned: 14 Nov S3 (10:00-17:00) + S1 (21:00-22:00);
15 Nov S4 (10:00-17:00) + S2 (21:00-22:00). A later start keeps the pairing. The script refuses a second run
for the same persona on the same MYT day (it checks the run records in `data/live/demo-scenario/`).

Commands (dry run first, then live, inside the window):
```
python scripts/demo_scenario_live.py --scenario S3
python scripts/demo_scenario_live.py --scenario S3 --live --confirm persona-04
python scripts/demo_scenario_live.py --scenario S1 --cloudflare
python scripts/demo_scenario_live.py --scenario S1 --live --confirm persona-02 --cloudflare
python scripts/demo_scenario_live.py --scenario S4
python scripts/demo_scenario_live.py --scenario S4 --live --confirm persona-06
python scripts/demo_scenario_live.py --scenario S2
python scripts/demo_scenario_live.py --scenario S2 --live --confirm persona-05
```

Rehearsal: `demo_scenario_sim.py --from <demo copy>/preview.db --root <new root> [--scenario ALL]` puts each
scenario on its own simulated day after the latest real day (S1 +1 ... S4 +4) and scores it with the backend
scorer. Recorded 12 Nov 2026 on a copy of the demo DB (latest real day 12 Nov), numbers not adjusted:

| Scenario | Day | AWS score / tier | Signals (new_action, new_resource, unusual_hours, volume, sensitive_new) | Expected |
|---|---|---|---|---|
| S1 persona-02 | 13 Nov | 86 High; Cloudflare 35 Medium; group 96 High | 0.6, 0.909, 1.0, 1.0, 0.909 | High (matched) |
| S2 persona-05 | 14 Nov | 22 Low | 0.0, 0.0, 1.0, 0.107, 0.0 | Medium at the time; L7 now states Low (matched) |
| S3 persona-04 | 15 Nov | 27 Low (v1.1); 30 Medium under v1.2 | 0.0, 0.55, 0.0, 0.0, 0.917 | Medium (lower under v1.1; matched under v1.2) |
| S4 persona-06 | 16 Nov | 15 Low | 0.0, 0.0, 0.0, 1.0, 0.0 | Low or Medium (matched) |

Real results will differ (different history and timing). The rehearsal is not evaluation evidence.
