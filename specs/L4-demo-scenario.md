# Spec: L4-demo-scenario — "Batch reporter goes rogue": simulated rehearsal now, real lab run on 16 Nov

**Branch:** `l1-live-baseline` (continue in `C:\Users\yyzhe\argus-worktrees\l1-live-baseline`, uncommitted) · **Executor:** executor (sonnet) · **Written:** 2026-11-11

## Goal
(A) A rehearsal site on a scratch copy where simulated events make persona-02 score High, so the
demo can be practised this week. (B) A separate, labelled script the project owner runs on or after
16 Nov 2026 that performs the same behaviour on the real AWS and Cloudflare lab, within the persona
role's existing permissions. The executor builds and tests (B) but never runs it live.

## Non-goals
- No live cloud call by the executor. No reading/decrypting credential stores. No IAM, trail,
  token or policy change. No edits to pilot checkouts, `backend/`, `SOURCE_FILES`,
  `TRAINING_SOURCES`, `scripts/cloudflare_machine_pilot.py`, `scripts/cloudflare_lab_setup.py`,
  `scripts/local_pilot.py`, `scripts/collect_live.py` (import read-only where stated).
- No simulated row ever enters the live DB or the 8017/3013 demo copy.
- No scoring changes. No commit/push.
- Collection after 16 Nov (extending the pilot) is a separate spec.

## Files in scope
New: `scripts/demo_scenario_sim.py`, `scripts/demo_scenario_live.py`,
`scripts/tests/test_demo_scenario.py`, `docs/DEMO_SCENARIO.md`.
Edited: `workspace_next/app.py` and `frontend/components/WorkspaceUI.js` (rehearsal banner only).

## Scenario (planner-decided; same in A and B)
Account: persona-02 "Batch reporter" — AWS role `…-persona-02` and its Cloudflare service token.
Normal profile: buckets p01/p02/p03, 2–5 events a day, 09:00–12:00 and 14:00–18:00 MYT.
| # | Behaviour | Count |
|---|---|---|
| 1 | `GetObject fixture.txt` on `confidential` | 12 |
| 2 | `GetObject fixture.txt` on p04, p05, p06 | 6 each |
| 3 | `GetBucketLocation` on confidential, p04, p05, p06 | 1 each |
| 4 | `ListObjectsV2` on `confidential` (not permitted: expect AccessDenied) | 1 |
| 5 | Cloudflare `GET /workloads/persona-02/demo-<n>` | 8 |
Time: evening MYT, outside the persona's usual hours (target 21:00–21:30).
All within the role's existing read-only policy except #4, which is expected to be denied.

## Approach

### A. Simulated rehearsal
1. `python scripts/demo_scenario_sim.py --from <demo copy db> --root data/live/live-v1-rehearsal`:
   copy the DB (refuse unless the source folder has a valid `workspace-copy.json` with
   `not_live: true`), write a marker with `not_live: true` and `rehearsal: true`, then insert the
   scenario rows for the **latest closed MYT day** at 21:05–21:25 MYT.
2. Rows reuse the exact stored shape and `account_key/label/kind/basis`, `source`,
   `source_account_id` of persona-02's existing AWS-role rows and Cloudflare-token rows (copy from
   a real row in the copy; change only id, event_id, timestamp, action, resource, ingested_at,
   metadata). `event_id` = `sim-<uuid4>`; metadata = `{"simulated": true, "scenario": "L4"}` only.
   `resource` for AWS rows is the real bucket name pattern as stored for existing rows. Row #4 is
   stored with action `ListObjectsV2` (metadata adds `"errorCode": "AccessDenied"`).
3. Run `baseline_alerts.sync` on the rehearsal copy. Start API on **8018** and UI on **3014**
   against it (own frontend copy/build with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8018`; no mirror
   loop). `ARGUS_WORKSPACE_UI_ORIGIN=http://127.0.0.1:3014`.
4. Banner: when the marker has `rehearsal: true`, `/workspace/status` returns it and every page
   header shows `REHEARSAL — contains simulated events` in an amber bar.
5. Print (labels and numbers only) persona-02's AWS account-day score, tier, each signal value,
   the Cloudflare token's score, and the workload group score for that day.
   **Expected, not to be tuned:** AWS account-day High (≥ 60). Report whatever it is.

### B. Real run (built now, run by the owner on/after 16 Nov)
6. `python scripts/demo_scenario_live.py` defaults to **dry-run**: prints the plan (counts, order,
   pacing) and makes zero network calls. Live mode needs all of:
   `--live --confirm persona-02`, and local time ≥ `2026-11-16T00:00:00+08:00` (hard-coded
   constant; refuse earlier with a clear message — the controlled study is still open).
7. AWS: boto3 profile `argus-simulator`; `sts.get_caller_identity` must be the lab runner user
   (compare the ARN suffix `:user/argus-lab/argus-ueba-actors-runner`; never print the account
   number). `AssumeRole` persona-02 with `RoleSessionName="argus-demo-persona-02"`,
   `DurationSeconds=900`. Bucket names and role ARN come from `scripts/simulation_lab.py` helpers
   (import read-only). Every S3 call passes `ExpectedBucketOwner`. Order: #3, #1, #2, #4; 2 s apart.
   Hard caps in code: ≤ 40 S3 calls, ≤ 2 STS calls; abort on the first unexpected error; #4 treats
   `AccessDenied` as the expected outcome and anything else as "recorded, continue".
8. Cloudflare (`--cloudflare`, optional): 8 GETs, 5 s apart, to the lab host using the persona-02
   token loaded with the existing loader in `scripts/cloudflare_machine_pilot.py` /
   `github_lab_app.py` (import; do not copy the decryption code; never print or log the secret or
   headers). On 401/403 (token expired or not refreshed) stop the Cloudflare part, report it, and
   let the AWS part stand. Cap 8.
9. Writes `data/live/demo-scenario/run-<utc>.json`: per call — time, operation, bucket symbol
   (p04/confidential, not the real name), HTTP status / error code, request id. No secrets, no
   account number.
10. Tests (`botocore.stub.Stubber`, mocked HTTP, frozen clock): refuses before 16 Nov; refuses
    without `--confirm`; dry-run makes zero calls; exact call counts and order; cap enforced;
    session name; AccessDenied on #4 is success; 403 on Cloudflare stops only that part; ledger
    contains no 12-digit number.
11. `docs/DEMO_SCENARIO.md`: what it does, why it is safe (read-only role, own lab, caps), the
    exact commands for dry-run and live, expected signals and score, how to see it in the UI, and
    the statement that it is a demonstration outside the controlled study.

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures
- [ ] `python scripts/demo_scenario_live.py` (dry-run) prints the plan and exits 0; `--live --confirm persona-02` today exits non-zero with the "study still open" message and makes no call
- [ ] Rehearsal: `http://127.0.0.1:3014` shows the amber banner; the queue's first row is a baseline alert for persona-02; Entities → Workloads → "Batch reporter (persona-02)" shows the merged timeline with the simulated events
- [ ] The 8017/3013 copy and the live DB contain zero rows with `event_id LIKE 'sim-%'` (query both read-only, print counts)
- [ ] `git diff --stat origin/six-role-commissioning -- backend/` empty; no tracked file under `scripts/` modified (new files only)

## Risk notes
Pilot checkouts read-only; counts-only output; temp SQLite in tests; no npm install; do not touch
ports 8013/8015/3011/8017/3013 or the mirror loop. The live script must be impossible to run by
accident: dry-run default, date guard, explicit confirm.

## Escalation triggers
Stop and report if: importing a helper would execute cloud calls or decrypt secrets at import
time; the persona-02 row shape cannot be copied unambiguously; the rehearsal AWS account-day is
not High (report the signal values — do not adjust the scenario or the scoring); the same step
fails twice.
