# Argus on one AWS server (R3 owner runbook)

Everything below that touches AWS, Cloudflare, GitHub or the laptop is **owner-run**. Nothing in this folder
contains an account id, address, e-mail or credential: replace every `<PLACEHOLDER>` yourself.

Shape: one EC2 instance (t3.small, 2 GB, Ubuntu 24.04, ap-southeast-1, 20 GB gp3), no inbound ports, shell via SSM
Session Manager, `cloudflared` as the only way in, one systemd unit running `scripts/argus_supervisor.py`
(ingest API 8013, collector, personas, mirror, workspace API 8017, notifier, web UI 3013, all on 127.0.0.1).
Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before any free-tier credit.

| File | Purpose |
|---|---|
| `argus.service` | systemd unit; starts only when `/var/lib/argus/CUTOVER_OK` exists (the single-consumer gate) |
| `cloudflared-config.example.yml` | `/api/*` -> 8017, everything else -> 3013, last rule 404; 8013 is never routed |
| `ops.linux.example.json` | `/etc/argus/ops.json`, Linux paths, AWS `profile: null` (instance role) |
| `iam-instance-policy.json` | instance role: receive/delete/get-attributes on the one queue, read ONE migration pack prefix (`migrate/<PACK_ID>/*`); no `sts:AssumeRole` (option A) |
| `persona-trust-statement.json` | **option B only (not used under option A)**: statement to ADD to each persona role's trust policy |
| `system-accounts.example.json` | labels the instance role as monitoring infrastructure |
| `../backend/requirements-ops.lock.txt` | pinned install set (versions of the laptop venv, Python 3.14) |
| `../scripts/cloud_migrate.py` | `pack` / `verify` for the stores |

## Two things the code does for the cloud path (read this first)

1. **`/api` prefix.** `cloudflared` cannot rewrite paths, and the workspace API's routes (`/workspace/...`, `/cases/...`,
   `/auth/...`) collide with UI page names (`/workspace`, `/cases`). So the unit sets `ARGUS_API_PREFIX=/api` and the
   workspace API strips that prefix itself, and the UI is built with `NEXT_PUBLIC_API_URL=https://argus.<domain>/api`
   (not the bare hostname). Same origin, no CORS, one Access cookie.
2. **`ARGUS_COOKIE_SECURE=1`** (set in the unit) makes the session cookie `Secure; HttpOnly; SameSite=Strict`.

## Steps, in order

### 17-19 Nov (preparation, laptop untouched)

1. **Instance role and instance.** IAM: create role `argus-ops-instance` (trusted by EC2) with the policy from
   `iam-instance-policy.json` (fill `<ACCOUNT_ID>`, `<QUEUE_NAME>`, `<MIGRATION_BUCKET>`; leave `<PACK_ID>` until step 10 gives the pack folder name, then set it) **plus the AWS-managed
   policy `AmazonSSMManagedInstanceCore`** (SSM's actions cannot be scoped to a resource, so they are attached as the
   AWS-maintained policy instead of an inline `*`). Launch: Ubuntu 24.04 x86, t3.small, 20 GB gp3, **no key pair**,
   security group with **no inbound rules**, that instance profile, IMDSv2 required.
2. **Backups.** Data Lifecycle Manager policy for the instance's volume: daily, retain 14.
3. **Software** (SSM Session Manager shell):
   ```
   sudo useradd --system --home /opt/argus --shell /usr/sbin/nologin argus
   sudo install -d -m 0755 /etc/argus
   sudo install -d -o argus -g argus -m 0700 /etc/argus/secrets
   sudo install -d -o argus -g argus -m 0750 /opt/argus /var/lib/argus
   ```
   Python 3.14 through `uv` (same minor as the laptop): install `uv`, then
   `sudo -u argus uv venv --python 3.14 /opt/argus/venv`. Node major 24 (laptop: v24): NodeSource or the Node
   tarball. The GitHub CLI `gh` (needed by the GitHub collector): install from cli.github.com's apt repository.
4. **Code.** `sudo -u argus git clone --branch r3-cloud-deploy <REPO_URL> /opt/argus/app` (the repo is private: use a
   short-lived read-only credential, then remove it). Install:
   `sudo -u argus uv pip install --python /opt/argus/venv/bin/python -r /opt/argus/app/backend/requirements-ops.lock.txt`.
   **If torch 2.12.0+cpu has no wheel for Python 3.14 on Linux, stop and tell the planner. Do not change the torch version.**
   Web UI (the workspace pages overlay the base frontend, as `scripts/prepare_workspace_preview.py` does):
   ```
   cd /opt/argus && sudo -u argus mkdir ui && sudo -u argus cp -r app/frontend/. ui/ \
     && sudo -u argus cp -r app/workspace_next/frontend/pages app/workspace_next/frontend/components app/workspace_next/frontend/lib ui/
   cd ui && sudo -u argus npm ci && sudo -u argus env NEXT_PUBLIC_API_URL=https://argus.<domain>/api npm run build
   ```
5. **Secrets** in `/etc/argus/secrets/`, each file owned by `argus`, mode **0600** (the loader refuses anything else):
   - `cloudflare-api-token`: Cloudflare API token, read-only for Access logs (one line).
   - `persona-01` ... `persona-06`: the persona service tokens, JSON `{"id": ..., "client_id": ..., "client_secret": ...}`
     (same content as the laptop's `persona-0N.dpapi` once decrypted). Put the non-secret `pilot-config.json` in
     `/var/lib/argus/cf-personas/`.
   - `github.env`: one line `GH_TOKEN=<fine-grained token, read-only for the lab repos>`.
   - `aws-credentials`: AWS shared-credentials file with ONLY a `[argus-simulator]` section (see Open question 1).
   Never paste any of these into a chat, ticket or this repo.
6. **Persona trust: skip under option A** (owner decision: the runner's key in `aws-credentials`, the instance role does
   not assume persona roles). Only if option B is ever chosen: for each of the six `argus-ueba-actors-persona-0N` roles, **add** the statement in
   `persona-trust-statement.json` to the trust policy (keep the existing runner statement). **Edit the trust policy only:
   never delete or recreate a role.** A recreated role gets a new principal id, which is the account key, and would
   reset that persona to Learning for 5 days.
7. **Config and labels.** Copy `ops.linux.example.json` to `/etc/argus/ops.json` and fill it (do **not** list the new Access
   application's id in `providers.cloudflare.app_ids`). Create `/var/lib/argus/workspace/` and copy
   `system-accounts.example.json` there as `system-accounts.json` **before the first tick**.
   Install `argus.service` and `cloudflared-config.example.yml` (`systemctl daemon-reload`; do **not** enable `argus` yet).
8. **Access first, then tunnel.** (a) Create the Cloudflare Access application for `argus.<domain>` and its allow policy
   (owner and supervisor e-mails, one-time PIN) and confirm both exist in the dashboard. Copy the application's
   **AUD tag** and your Zero Trust **team name** into the config's `originRequest.access` blocks (both routes), so
   `cloudflared` itself rejects requests without a valid Access token for this app. (b) Only then create the tunnel,
   add the DNS route for `argus.<domain>`, and install and start `cloudflared` with the edited config.
   (c) Check: an unauthenticated request to `https://argus.<domain>` (private window) must show the Access login, not the app.
   Create the workspace users:
   `sudo -u argus /opt/argus/venv/bin/python -m backend.auth add-user <name> --role analyst --users-file /var/lib/argus/auth/users.json`.

### Fri 20 Nov 2026 (the cutover)

9. **Laptop:** follow `docs/OPS_CONTINUITY.md` steps 3-4: `scripts/retire_pilot_tasks.ps1 -Apply`, wait until
   `Argus-Pilot-Collect` is Disabled (not Running) and no `local_pilot.py ... tick` / `collect_live` process remains, then
   `scripts/ops_cutover_check.py` must pass (the laptop drain check).
10. **Pack (laptop):** `python scripts/cloud_migrate.py pack --config <ops.json> --bundle <pinned AE v2 bundle dir> --out <new folder>`.
    Upload the folder to the private bucket under `migrate/<PACK_ID>/` and set `<PACK_ID>` in the instance policy's S3 statement.
    Note the printed counts; `verify` rejects a missing required store, an extra or altered file, and any symlink.
11. **Pull and install (server).** Download to `/var/lib/argus/incoming`, then run
    `python scripts/cloud_migrate.py verify --pack /var/lib/argus/incoming` (must exit 0). Copy each entry to the path in
    `/etc/argus/ops.json` (`events.db` -> `live_state_dir`, `preview.db` -> workspace dir, `auth/*`, `ledger/` ->
    `personas.ledger_dir`, `ticks/` -> `<status_dir>/ticks`, `side/*` -> workspace dir, `bundle/` ->
    `/var/lib/argus/bundle/`; adjust `ARGUS_LIVE_AE_BUNDLE` in the unit if the folder name differs) and run
    `verify --pack ... --config /etc/argus/ops.json --bundle /var/lib/argus/bundle/<bundle>` (must exit 0 again).
    Do not copy `workspace-copy.json`: the supervisor writes it with the server's path.
12. **Score check (evaluator, spec step 3):** recompute baseline and AE v2 scores for every stored account-day into a
    scratch copy and compare: baseline equal exactly; AE max abs diff <= 1e-6; zero flips of `flagged` or
    `flagged_secondary`. Any flip stops the cutover. Record the result in `results/`.
13. `python -m backend.readiness --db /var/lib/argus/connected/events.db` must print READY.
14. **Fence the laptop at AWS (owner, console).** After the drain check passes and before `CUTOVER_OK`: remove the laptop
    collector identity's permission to read the queue (detach its policy, or add an explicit Deny on `sqs:ReceiveMessage` and
    `sqs:DeleteMessage` for `<QUEUE_NAME>`, or deactivate its access key `<LAPTOP_COLLECTOR_KEY_ID>`). Prove it with ONE receive
    attempt using the laptop profile: it must fail with access denied. Do not continue if it succeeds.
15. **Only then:** `sudo touch /var/lib/argus/CUTOVER_OK && sudo systemctl enable --now argus`. **`CUTOVER_OK` is a local
    guard on this host only; it cannot stop another host. Exclusive queue ownership is enforced by step 14's AWS permission,
    not by the file.** The laptop collector must never run again unless you roll back.
16. After cutover remove the S3 read statement (`ReadTheMigrationPackOnly`) from the instance role and delete the pack.

**Fallback (no all-or-nothing):** if the server is not READY by **20 Nov 18:00 MYT**, run the Windows path instead
(`docs/OPS_CONTINUITY.md` step 6, `scripts/install_ops_tasks.ps1`). The ops collector must run by 20:00, when SQS and the 24 h
fetch windows start losing events. The cut line is the last point to decide; otherwise stay on the Windows path.

### 21-22 Nov (proof)

The proof is the L7 coverage rule itself: every persona call claimed in the new ledger is provider-confirmed in the
server's store (`scripts/live_eval_report.py`, coverage section). Also check `minutes_since_last_ok` in
`/var/lib/argus/ops/ops-status.json`.

### Rollback at any time

`sudo systemctl disable --now argus && sudo rm /var/lib/argus/CUTOVER_OK`; wait until no collector process is left
(`pgrep -f ops_collect`); on the server run `cloud_migrate.py pack` with the server config, copy the pack back.
Only after the server unit is disabled and the collector is gone, the owner re-enables the laptop collector's queue
permission (reverse of step 14: re-attach the policy / remove the Deny / reactivate the key), then take the Windows path.
Never re-enable the laptop's access while `argus` can still run on the server. There is only ever one consumer.

## Open questions (found while implementing; none silently resolved)

1. **Persona executor needs the runner IAM user, not the instance role.** `scripts/run_persona_history.execute` refuses to
   run unless `sts:GetCallerIdentity` is exactly `user/argus-lab/<stack>-runner`, and it calls CloudTrail with that identity.
   With `aws_profile: null` (instance role) every persona tick would stop with "Require exact non-root lab runner". I did not
   weaken that check (pinned persona mechanics). Shipped default: the runner's keys stay on the server in
   `/etc/argus/secrets/aws-credentials` (profile `argus-simulator`, mode 0600, `AWS_SHARED_CREDENTIALS_FILE` in the unit).
   That is the one long-lived key left on disk; the persona-role trust statement (step 6) is not used.
   Owner decision: option A (keep this). Option B would be: authorise a reviewed change that also accepts the instance role's assumed-role ARN
   (needs `cloudtrail:GetTrailStatus` / `GetEventSelectors` added to the instance policy).
2. **GitHub collector admin check.** `collect_github` requires the token's user to own the repo or have `permissions.admin`.
   A fine-grained read-only token of the repo owner should satisfy "owner", but this is not tested here. If it fails
   (`CollectionError`, shown in `ops-status.json`) the escalation trigger "token scope wider than read-only" applies.
3. **Collector and cloud-side Cloudflare token.** `scripts/setup_cloudflare.load_token` is Windows DPAPI only (and a pinned
   pilot file, not edited). The cloud path reads `cloudflare-api-token` from `/etc/argus/secrets` instead (`collect_live.py`).
4. **Silent-failure fix.** On Linux `local_pilot.lock` raised ImportError (msvcrt) inside a loop that swallows exceptions, so
   the collector and persona loops would have idled with no error. Both now use `scripts/linux_compat.lock` (fcntl). `local_pilot.py`
   itself is untouched (its file hash is pinned by the pilot).
5. **SSM permissions** are attached as `AmazonSSMManagedInstanceCore` (cannot be resource-scoped), so the inline policy file has no `*`.
   The extra `s3:GetObject` on `migrate/<PACK_ID>/*` is for the pack download; remove the statement after cutover (step 16).
6. **CloudFormation drift.** The persona roles belong to stack `argus-ueba-actors`; editing a trust policy in the console makes
   the stack drift. Do not run a stack update that rewrites the roles without adding the same statement to the template.
7. **Instance-role CloudTrail label.** `system-accounts.json` marks the role's own activity as infrastructure (display context,
   as for the existing service principals). It does not remove those events from scoring; they were never persona accounts, and
   the baseline/AE treat them as any other account. The label must equal the role name.
8. **Linux-only branches** (fcntl lock, 0600 secret check) are covered by tests that skip on Windows; the new `linux-ops` CI job
   runs them on ubuntu (Python 3.14, from the lock). The 3.14 CPU-torch wheel on Linux is verified only by that job.
9. **Credentials share one Unix user (residual risk, accepted for the competition).** The supervisor now passes the AWS,
   GitHub and Cloudflare variables only to the collector and persona children, but all children run as the same `argus`
   user, so a compromised web process could still read the 0600 files in `/etc/argus/secrets/` and the `github.env` the unit
   loads. The proper fix (separate `argus-web` user/unit, short-lived runner credentials) is post-competition work.
10. **Sessions** are in memory: a restart signs analysts out (accepted, separate task).

### What `scripts/local_pilot.py tick` does that the cloud path replaces, and what it loses

The laptop collector today is `local_pilot.py tick` (V3 harness, Argus-Pilot-Collect every 5 min, ingest on 8013). The l15
`argus_supervisor.py` + `ops_collect.py` + `ops_personas.py` cover the same phases: AWS SQS (`ops_collect` aws), AWS personas and
their provider confirmation (`ops_personas.run_aws` -> `history.execute` / `history.audit`), GitHub (`gh` events, same revisions
archive), Cloudflare Access log, and the Cloudflare persona requests with ray-id confirmation. Lost on the server: the pilot's
dated reserved executors (`run_reserved_study.py` for 14-15 Nov) and its V3 pin checks, which end before 17 Nov; and `gh`/DPAPI
logins, which become `GH_TOKEN` and `/etc/argus/secrets` files (open questions 2, 3).
