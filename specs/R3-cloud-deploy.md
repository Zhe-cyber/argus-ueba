# Spec: R3-cloud-deploy — run the whole live system on one AWS server, behind Cloudflare

**Branch:** `r3-cloud-deploy` (from `l15-eval-report` once it is committed) · **Executor:** executor (sonnet);
security pass by Codex · **Written:** 13 Nov 2026

## Goal
After this task the live system (collector, persona workloads, scoring, comparator, workspace API, web UI,
notifier) runs 24/7 on one small Linux server in AWS instead of the laptop. Analysts reach it at one HTTPS
address through a Cloudflare Tunnel, behind Cloudflare Access and then the app's own sign-in. The laptop is no
longer needed for collection, so a power cut or Wi-Fi drop at home (7 Nov, 13 Nov) can no longer break it.

## Why this shape (planner-decided; do not re-open)
- **One EC2 instance (t3.small, 2 GB RAM, x86, Ubuntu 24.04 LTS, ap-southeast-1)**, not Lightsail: only EC2
  takes an IAM instance role, which means no long-lived AWS keys on disk. x86 avoids any aarch64 torch wheel
  surprises.
- **SQLite on the instance disk (gp3, 20 GB)**, not Neon: the workspace mirror refuses anything but SQLite
  (`workspace_next/live_mirror.py`), and every evaluation number has been produced on SQLite. Backups are
  native **EBS snapshots via Data Lifecycle Manager** (daily, keep 14). SQLite in WAL mode is crash-safe, so a
  crash-consistent snapshot is a valid database. No backup code.
- **The existing `scripts/argus_supervisor.py` is the only process manager**, run by **one systemd unit**
  (`Restart=always`). It already runs every component, binds them all to 127.0.0.1, and is portable
  (`CREATE_NO_WINDOW` is a getattr fallback). There is no Docker and no second scheduler.
- **Cloudflare Tunnel (`cloudflared` as a systemd service)** is the only way in. The instance has **no inbound
  ports at all**: its security group allows no inbound traffic, and the owner gets a shell through SSM Session
  Manager. Cloudflare cannot host this itself, because Workers cannot run FastAPI with torch.
- **One hostname, path routing**: `argus.<domain>` sends `/api/*` to the workspace API (8017) and everything
  else to the web UI (3013). Being same-origin, there is no CORS and no cross-site cookie, and the Access
  cookie covers both. The ingest API (8013) and the mirror are **never** routed.
- **No Vercel and no Neon.** One box keeps one failure domain and one place to look.

## Non-goals
- Containerising the app, multi-instance setups or autoscaling.
- Making Neon or Postgres the live store.
- Changing any scoring method, feature, threshold or frozen artifact.
- Persistent sessions. A restart logs users out, which is acceptable; that is a separate task.
- Collecting the new Cloudflare Access app's own logs. Its app id must **not** be added to
  `providers.cloudflare.app_ids`, or analysts' own logins would become scored accounts.
- Any change to the running laptop system on 14–15 Nov (evaluation days). Code work on this branch is fine.

## Files in scope
- `scripts/ops_collect.py`, `scripts/collect_live.py`: AWS `profile` may be `null`, meaning boto3's default
  chain (the instance role). This changes nothing when a profile is set.
- `scripts/ops_personas.py` and the DPAPI secret loader it calls: on non-Windows, read each secret from
  `/etc/argus/secrets/<name>` and refuse to start unless the file is owned by the service user with mode 0600.
  Windows behaviour is unchanged.
- `workspace_next/app.py`: `ARGUS_COOKIE_SECURE=1` passes `secure=True` to `auth.install` (the parameter
  already exists).
- `backend/system_accounts.py` or the existing system-account labelling: label the instance role's own
  CloudTrail activity (credential refresh, SSM, snapshots) as a monitoring-infrastructure account, never scored
  as a persona or user.
- New `deploy/` folder:
  - `argus.service` (systemd unit for the supervisor);
  - `cloudflared-config.example.yml` (ingress rules above, ending in `http_status:404`);
  - `ops.linux.example.json` (Linux paths, `profile: null`);
  - `iam-instance-policy.json` (least privilege: receive/delete/get-attributes on the one queue, `sts:AssumeRole`
    on exactly the six `argus-*-persona-0N` roles, SSM core);
  - `persona-trust-statement.json` (the statement to add to each persona role's trust policy);
  - `README.md` (owner runbook, below).
- New `scripts/cloud_migrate.py` with `pack` and `verify`:
  - `pack` copies each store with SQLite's backup API (never a raw file copy): the live `events.db`, the
    workspace `preview.db` plus `auth/`, the persona and machine ledgers, and the pinned AE v2 bundle.
  - `pack` writes `migrate-manifest.json` holding per-table row counts, `max(id)`, the bundle's file sha256s and
    the method-binding sha.
  - `verify` recomputes the same on the server and exits non-zero on any difference.
- Tests for each change above. `backend/requirements.txt`: add a pinned lock for the ops path if one is missing.

## Approach
1. Code changes above, each behind "unchanged on Windows" tests.
2. **Linux check (CI):** add one GitHub Actions job on ubuntu-latest that installs from the lock and runs
   `backend.readiness` against a fixture DB and the `cloud_migrate.py pack → verify` round trip.
3. **Cross-platform score check (evaluator):** on the server after migration, recompute baseline and AE v2
   scores for every stored account-day **into a scratch copy** and compare them with the stored values:
   - baseline equal exactly;
   - AE max abs diff ≤ 1e-6;
   - zero flips of `flagged` or `flagged_secondary`.
   Any flip stops the cutover. Record the result in `results/`.
4. **Owner runbook (`deploy/README.md`)**, in order. Every console step is the owner's; Claude only prepares.
   - **16 Nov:**
     1. Launch the instance (no key pair, no inbound rules) with the instance role.
     2. Turn on DLM.
     3. Install Python 3.14 (via `uv`, same minor version as the laptop) and Node (same major as the laptop).
     4. Clone the branch, install the lock, and build the UI with `NEXT_PUBLIC_API_URL=https://argus.<domain>`.
     5. Put secrets in `/etc/argus/secrets/` (0600):
        - a Cloudflare API token, read-only for Access logs;
        - the persona service tokens;
        - a fine-grained GitHub token, read-only for the lab repos.
     6. Add the trust statement to the six persona roles. **Edit the trust policy only — never delete or recreate
        a role.** A recreated role gets a new principal id, which is the account key, and would reset that
        persona to Learning for 5 days.
     7. Create the tunnel and the Access application (owner and supervisor emails, one-time PIN).
   - **17 Nov after 00:00 MYT:** on the laptop, follow OPS_CONTINUITY.md steps 3–4 (retire, wait for drain,
     `ops_cutover_check.py`). Then `cloud_migrate.py pack`, upload to a private S3 bucket, pull on the server,
     run `verify`, run the score check (step 3), and run `backend.readiness` on the server, which must print
     READY. **Only then** `systemctl enable --now argus`: from that moment the server is the single SQS
     consumer.
   - **Fallback (no all-or-nothing):** if the server is not READY by **17 Nov 18:00 MYT**, run the Windows path
     instead (OPS_CONTINUITY.md step 6, `install_ops_tasks.ps1`). The ops collector must run by 20:00, when SQS
     and the 24 h fetch windows would start losing events. Retry the cloud move after Round 2.
   - **18–19 Nov:** the proof is the L7 coverage rule itself: every persona call claimed in the new ledger is
     provider-confirmed in the server's store (`live_eval_report.py` coverage section). Also check
     `minutes_since_last_ok` in `ops-status.json`.
   - **Rollback at any time:** `systemctl disable --now argus`, wait until no collector process is left, copy
     the store back with `cloud_migrate.py pack` on the server, then take the Windows path. There is only ever
     one consumer.

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` gives 0
  failures on Windows, and the new ubuntu CI job is green.
- [ ] `grep -rnE "source_ip|sourceIPAddress|user_agent|userAgent" backend/baseline_scorer.py backend/live_ae.py`
  shows no feature use. If it does, stop: a new executor host would change the scores.
- [ ] `cloud_migrate.py pack` then `verify` on a copy of the demo store exits 0. Deleting one row makes it exit
  non-zero.
- [ ] On a non-Windows test, a secret file with mode 0644 is refused, and Windows still uses DPAPI.
- [ ] With `ARGUS_COOKIE_SECURE=1`, the session cookie carries `Secure; HttpOnly; SameSite=Strict`.
- [ ] `deploy/iam-instance-policy.json` has no `*` resource and no IAM write actions. Codex confirms this.
- [ ] The tunnel example routes only 3013 and 8017. Codex confirms 8013 is unreachable.
- [ ] PR body contains the owner runbook checklist and the cost line: about US$15–20/month for t3.small, 20 GB
  gp3 and snapshots, before any free-tier credit.

## Risk notes
- **Single SQS consumer** is the top risk. Never start the server service before the laptop drain check
  passes. Never run both. `install_ops_tasks.ps1 -Apply` re-checks the drain, and the server start must too
  (the runbook gate).
- **Persona role identity** is the account key (`backend/account_identity.py`, `sessionIssuer.principalId`). Do
  not recreate the roles.
- **Server's own CloudTrail noise** becomes a new account unless it is labelled. Label it before the first tick.
- Do not touch the frozen contracts, `scripts/reserved_study.py` SOURCE_FILES or `scripts/train_clue_v2.py`
  TRAINING_SOURCES, the method binding file, or the pinned bundle.
- No credentials, account ids, emails or IPs in the repo, logs, `ops-status.json` or the PR. The examples use
  placeholders.
- Read LESSONS.md first. In particular: CRLF on edited Windows files, and Windows-only paths in tests (the CI
  failure of 12 Nov).

## Escalation triggers
- Any AE flag flip or baseline difference in the cross-platform check.
- The GitHub collector needs a token scope wider than read-only repository metadata and events.
- The persona trust change would require recreating a role.
- torch 2.12 CPU has no Linux wheel for the pinned Python 3.14: stop and ask; do not change the torch version.
