SECURITY RE-REVIEW. Project: Argus UEBA, R3 cloud deploy (single AWS server behind Cloudflare Tunnel + Access).
Your earlier review of commit 1a82311 returned REQUEST_CHANGES with 6 findings (full text below). The diff below is the
uncommitted fix set on top of 1a82311. You may read any file in this repository (read-only).
For EACH of the 6 original findings state: FIXED / PARTIALLY FIXED / NOT FIXED, with file:line evidence.
Then list any NEW confident security defects introduced by the fixes (file:line, defect, concrete failure scenario).
Known accepted residual risks (do not re-raise): all server processes share one OS user; the migration manifest is not
independently signed.
End with exactly one verdict line: APPROVE or REQUEST_CHANGES.

=== ORIGINAL REVIEW ===
# R3 cloud deployment security review

Base: `l15-eval-report`. Reviewed HEAD `1a82311bdf4d4081506597f0e2a55147e0885f6f`, including the deployment specification and runbook. Scope was static local review. No provider calls or commits were made.

## High

1. **Migration verification can bless altered or incomplete evidence.** `scripts/cloud_migrate.py:94â€“98,159â€“176`. SQLite verification compares table row counts and maximum IDs. Changing an existing finding or analyst decision without changing its ID passes that check. The verifier also derives the required inventory from the transferred manifest, so removing a required store and its manifest entries can pass verification. Require the expected inventory from trusted configuration, and verify exact content digests for completed SQLite backups and other artifacts against a manifest authenticated independently of the transfer. If installation intentionally rewrites a store, verify its canonical record digest.

2. **The cutover gate cannot fence the old SQS consumer.** `deploy/argus.service:9`, `deploy/README.md:83â€“85,99â€“100`, `scripts/ops_collect.py:298â€“310`. The local marker sits in a directory writable by the service account and survives restarts. If the laptop collector comes back while EC2 has the marker, each host can receive and delete different messages into its own database. The Linux lock only coordinates calls sharing its local lock path. Put the approval marker under root control and enforce exclusive queue ownership by disabling the old consumer's queue access before granting the new one, with the reverse order for rollback.

## Medium

3. **The deployment gives web processes access to collector and runner credentials.** `deploy/argus.service:12â€“21`, `scripts/argus_supervisor.py:93â€“120`. The unit loads the GitHub environment file and the supervisor forwards its environment to the web UI and workspace API. The same UID can read the option A long-lived AWS key file even at mode 0600. A compromised web process could reuse either credential within its provider permissions. Isolate the web processes and collectors under different UIDs, inject secrets only into the process that uses them, and replace the persistent runner key with a short-lived identity when supported.

4. **Pack paths can cross the intended source or verification directory.** `scripts/cloud_migrate.py:73â€“77,85â€“91,137â€“147`. Manifest filenames are joined directly to the pack root and the pack walker follows file symlinks. An accidentally symlinked file under a bundled directory can copy a readable local secret into a bundle destined for upload. Verification can also hash files outside the incoming directory. Require canonical relative names within an expected layout and reject symlinks and nonregular entries during pack and verification.

5. **The instance role keeps migration and persona permissions beyond the runtime requirement.** `deploy/iam-instance-policy.json:13â€“27`, `deploy/README.md:120â€“125,136â€“137`. The collector's instance role can read every object under the migration prefix and directly assume the six lab roles even though option A uses a separate runner for those roles. If the instance is compromised while these grants are attached, its credentials can retrieve any retained migration pack and assume the lab roles. Use a separate temporary grant for the exact migration objects and leave persona-role assumption out of the instance role under option A.

6. **The tunnel can publish the application before Access is enforced.** `deploy/cloudflared-config.example.yml:7â€“12`, `deploy/README.md:76â€“79`. The runbook routes the public hostname before creating the Access policy, and the connector has no Access token validation of its own. During setup or after an Access hostname mismatch, public requests can reach the workspace login and health routes, despite the EC2 security group allowing no inbound ports. Provision Access before routing the hostname and configure connector-side Access JWT validation on both routes using the expected application audience.

**REQUEST_CHANGES**



=== FIX DIFF (git diff HEAD) ===
diff --git a/deploy/README.md b/deploy/README.md
index 2b9aaba..bf13a35 100644
--- a/deploy/README.md
+++ b/deploy/README.md
@@ -13,8 +13,8 @@ Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before
 | `argus.service` | systemd unit; starts only when `/var/lib/argus/CUTOVER_OK` exists (the single-consumer gate) |
 | `cloudflared-config.example.yml` | `/api/*` -> 8017, everything else -> 3013, last rule 404; 8013 is never routed |
 | `ops.linux.example.json` | `/etc/argus/ops.json`, Linux paths, AWS `profile: null` (instance role) |
-| `iam-instance-policy.json` | instance role: receive/delete/get-attributes on the one queue, assume the six persona roles, read the migration pack |
-| `persona-trust-statement.json` | statement to ADD to each persona role's trust policy |
+| `iam-instance-policy.json` | instance role: receive/delete/get-attributes on the one queue, read ONE migration pack prefix (`migrate/<PACK_ID>/*`); no `sts:AssumeRole` (option A) |
+| `persona-trust-statement.json` | **option B only (not used under option A)**: statement to ADD to each persona role's trust policy |
 | `system-accounts.example.json` | labels the instance role as monitoring infrastructure |
 | `../backend/requirements-ops.lock.txt` | pinned install set (versions of the laptop venv, Python 3.14) |
 | `../scripts/cloud_migrate.py` | `pack` / `verify` for the stores |
@@ -29,10 +29,10 @@ Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before
 
 ## Steps, in order
 
-### 16 Nov (preparation, laptop untouched)
+### 17-19 Nov (preparation, laptop untouched)
 
 1. **Instance role and instance.** IAM: create role `argus-ops-instance` (trusted by EC2) with the policy from
-   `iam-instance-policy.json` (fill `<ACCOUNT_ID>`, `<QUEUE_NAME>`, `<MIGRATION_BUCKET>`) **plus the AWS-managed
+   `iam-instance-policy.json` (fill `<ACCOUNT_ID>`, `<QUEUE_NAME>`, `<MIGRATION_BUCKET>`; leave `<PACK_ID>` until step 10 gives the pack folder name, then set it) **plus the AWS-managed
    policy `AmazonSSMManagedInstanceCore`** (SSM's actions cannot be scoped to a resource, so they are attached as the
    AWS-maintained policy instead of an inline `*`). Launch: Ubuntu 24.04 x86, t3.small, 20 GB gp3, **no key pair**,
    security group with **no inbound rules**, that instance profile, IMDSv2 required.
@@ -65,7 +65,8 @@ Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before
    - `github.env`: one line `GH_TOKEN=<fine-grained token, read-only for the lab repos>`.
    - `aws-credentials`: AWS shared-credentials file with ONLY a `[argus-simulator]` section (see Open question 1).
    Never paste any of these into a chat, ticket or this repo.
-6. **Persona trust.** For each of the six `argus-ueba-actors-persona-0N` roles, **add** the statement in
+6. **Persona trust: skip under option A** (owner decision: the runner's key in `aws-credentials`, the instance role does
+   not assume persona roles). Only if option B is ever chosen: for each of the six `argus-ueba-actors-persona-0N` roles, **add** the statement in
    `persona-trust-statement.json` to the trust policy (keep the existing runner statement). **Edit the trust policy only:
    never delete or recreate a role.** A recreated role gets a new principal id, which is the account key, and would
    reset that persona to Learning for 5 days.
@@ -73,18 +74,21 @@ Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before
    application's id in `providers.cloudflare.app_ids`). Create `/var/lib/argus/workspace/` and copy
    `system-accounts.example.json` there as `system-accounts.json` **before the first tick**.
    Install `argus.service` and `cloudflared-config.example.yml` (`systemctl daemon-reload`; do **not** enable `argus` yet).
-8. **Tunnel and Access.** Create the tunnel, route `argus.<domain>` to it, install `cloudflared` as a service with the
-   edited config. Create the Cloudflare Access application for `argus.<domain>`: allow the owner and supervisor
-   e-mails, one-time PIN. Create the workspace users:
+8. **Access first, then tunnel.** (a) Create the Cloudflare Access application for `argus.<domain>` and its allow policy
+   (owner and supervisor e-mails, one-time PIN) and confirm both exist in the dashboard. (b) Only then create the tunnel,
+   add the DNS route for `argus.<domain>`, and install and start `cloudflared` with the edited config.
+   (c) Check: an unauthenticated request to `https://argus.<domain>` (private window) must show the Access login, not the app.
+   Create the workspace users:
    `sudo -u argus /opt/argus/venv/bin/python -m backend.auth add-user <name> --role analyst --users-file /var/lib/argus/auth/users.json`.
 
-### 17 Nov, after 00:00 MYT (the cutover)
+### Fri 20 Nov 2026 (the cutover)
 
 9. **Laptop:** follow `docs/OPS_CONTINUITY.md` steps 3-4: `scripts/retire_pilot_tasks.ps1 -Apply`, wait until
    `Argus-Pilot-Collect` is Disabled (not Running) and no `local_pilot.py ... tick` / `collect_live` process remains, then
-   `scripts/ops_cutover_check.py` must pass.
+   `scripts/ops_cutover_check.py` must pass (the laptop drain check).
 10. **Pack (laptop):** `python scripts/cloud_migrate.py pack --config <ops.json> --bundle <pinned AE v2 bundle dir> --out <new folder>`.
-    Upload the folder to the private bucket under `migrate/`.
+    Upload the folder to the private bucket under `migrate/<PACK_ID>/` and set `<PACK_ID>` in the instance policy's S3 statement.
+    Note the printed counts; `verify` rejects a missing required store, an extra or altered file, and any symlink.
 11. **Pull and install (server).** Download to `/var/lib/argus/incoming`, then run
     `python scripts/cloud_migrate.py verify --pack /var/lib/argus/incoming` (must exit 0). Copy each entry to the path in
     `/etc/argus/ops.json` (`events.db` -> `live_state_dir`, `preview.db` -> workspace dir, `auth/*`, `ledger/` ->
@@ -96,14 +100,20 @@ Cost: about US$15-20 per month for the t3.small, 20 GB gp3 and snapshots, before
     scratch copy and compare: baseline equal exactly; AE max abs diff <= 1e-6; zero flips of `flagged` or
     `flagged_secondary`. Any flip stops the cutover. Record the result in `results/`.
 13. `python -m backend.readiness --db /var/lib/argus/connected/events.db` must print READY.
-14. **Only then:** `sudo touch /var/lib/argus/CUTOVER_OK && sudo systemctl enable --now argus`. From this moment the
-    server is the single SQS consumer. The laptop collector must never run again unless you roll back.
-
-**Fallback (no all-or-nothing):** if the server is not READY by **17 Nov 18:00 MYT**, run the Windows path instead
+14. **Fence the laptop at AWS (owner, console).** After the drain check passes and before `CUTOVER_OK`: remove the laptop
+    collector identity's permission to read the queue (detach its policy, or add an explicit Deny on `sqs:ReceiveMessage` and
+    `sqs:DeleteMessage` for `<QUEUE_NAME>`, or deactivate its access key `<LAPTOP_COLLECTOR_KEY_ID>`). Prove it with ONE receive
+    attempt using the laptop profile: it must fail with access denied. Do not continue if it succeeds.
+15. **Only then:** `sudo touch /var/lib/argus/CUTOVER_OK && sudo systemctl enable --now argus`. **`CUTOVER_OK` is a local
+    guard on this host only; it cannot stop another host. Exclusive queue ownership is enforced by step 14's AWS permission,
+    not by the file.** The laptop collector must never run again unless you roll back.
+16. After cutover remove the S3 read statement (`ReadTheMigrationPackOnly`) from the instance role and delete the pack.
+
+**Fallback (no all-or-nothing):** if the server is not READY by **20 Nov 18:00 MYT**, run the Windows path instead
 (`docs/OPS_CONTINUITY.md` step 6, `scripts/install_ops_tasks.ps1`). The ops collector must run by 20:00, when SQS and the 24 h
-fetch windows start losing events. Retry the cloud move after Round 2.
+fetch windows start losing events. The cut line is the last point to decide; otherwise stay on the Windows path.
 
-### 18-19 Nov (proof)
+### 21-22 Nov (proof)
 
 The proof is the L7 coverage rule itself: every persona call claimed in the new ledger is provider-confirmed in the
 server's store (`scripts/live_eval_report.py`, coverage section). Also check `minutes_since_last_ok` in
@@ -112,8 +122,10 @@ server's store (`scripts/live_eval_report.py`, coverage section). Also check `mi
 ### Rollback at any time
 
 `sudo systemctl disable --now argus && sudo rm /var/lib/argus/CUTOVER_OK`; wait until no collector process is left
-(`pgrep -f ops_collect`); on the server run `cloud_migrate.py pack` with the server config, copy the pack back,
-then take the Windows path. There is only ever one consumer.
+(`pgrep -f ops_collect`); on the server run `cloud_migrate.py pack` with the server config, copy the pack back.
+Only after the server unit is disabled and the collector is gone, the owner re-enables the laptop collector's queue
+permission (reverse of step 14: re-attach the policy / remove the Deny / reactivate the key), then take the Windows path.
+Never re-enable the laptop's access while `argus` can still run on the server. There is only ever one consumer.
 
 ## Open questions (found while implementing; none silently resolved)
 
@@ -122,8 +134,8 @@ then take the Windows path. There is only ever one consumer.
    With `aws_profile: null` (instance role) every persona tick would stop with "Require exact non-root lab runner". I did not
    weaken that check (pinned persona mechanics). Shipped default: the runner's keys stay on the server in
    `/etc/argus/secrets/aws-credentials` (profile `argus-simulator`, mode 0600, `AWS_SHARED_CREDENTIALS_FILE` in the unit).
-   That is the one long-lived key left on disk, and the persona-role trust statement in step 6 is then not exercised.
-   Decision for the planner: keep this, or authorise a reviewed change that also accepts the instance role's assumed-role ARN
+   That is the one long-lived key left on disk; the persona-role trust statement (step 6) is not used.
+   Owner decision: option A (keep this). Option B would be: authorise a reviewed change that also accepts the instance role's assumed-role ARN
    (needs `cloudtrail:GetTrailStatus` / `GetEventSelectors` added to the instance policy).
 2. **GitHub collector admin check.** `collect_github` requires the token's user to own the repo or have `permissions.admin`.
    A fine-grained read-only token of the repo owner should satisfy "owner", but this is not tested here. If it fails
@@ -134,7 +146,7 @@ then take the Windows path. There is only ever one consumer.
    the collector and persona loops would have idled with no error. Both now use `scripts/linux_compat.lock` (fcntl). `local_pilot.py`
    itself is untouched (its file hash is pinned by the pilot).
 5. **SSM permissions** are attached as `AmazonSSMManagedInstanceCore` (cannot be resource-scoped), so the inline policy file has no `*`.
-   The extra `s3:GetObject` on `migrate/*` is for the pack download; delete the bucket/policy line after cutover.
+   The extra `s3:GetObject` on `migrate/<PACK_ID>/*` is for the pack download; remove the statement after cutover (step 16).
 6. **CloudFormation drift.** The persona roles belong to stack `argus-ueba-actors`; editing a trust policy in the console makes
    the stack drift. Do not run a stack update that rewrites the roles without adding the same statement to the template.
 7. **Instance-role CloudTrail label.** `system-accounts.json` marks the role's own activity as infrastructure (display context,
@@ -142,7 +154,11 @@ then take the Windows path. There is only ever one consumer.
    the baseline/AE treat them as any other account. The label must equal the role name.
 8. **Linux-only branches** (fcntl lock, 0600 secret check) are covered by tests that skip on Windows; the new `linux-ops` CI job
    runs them on ubuntu (Python 3.14, from the lock). The 3.14 CPU-torch wheel on Linux is verified only by that job.
-9. **Sessions** are in memory: a restart signs analysts out (accepted, separate task).
+9. **Credentials share one Unix user (residual risk, accepted for the competition).** The supervisor now passes the AWS,
+   GitHub and Cloudflare variables only to the collector and persona children, but all children run as the same `argus`
+   user, so a compromised web process could still read the 0600 files in `/etc/argus/secrets/` and the `github.env` the unit
+   loads. The proper fix (separate `argus-web` user/unit, short-lived runner credentials) is post-competition work.
+10. **Sessions** are in memory: a restart signs analysts out (accepted, separate task).
 
 ### What `scripts/local_pilot.py tick` does that the cloud path replaces, and what it loses
 
diff --git a/deploy/iam-instance-policy.json b/deploy/iam-instance-policy.json
index a1984d6..902c33c 100644
--- a/deploy/iam-instance-policy.json
+++ b/deploy/iam-instance-policy.json
@@ -1,30 +1,21 @@
-{
-  "Version": "2012-10-17",
-  "Statement": [
-    {
-      "Sid": "ConsumeTheOneEventQueue",
-      "Effect": "Allow",
-      "Action": ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes"],
-      "Resource": "arn:aws:sqs:us-east-1:<ACCOUNT_ID>:<QUEUE_NAME>"
-    },
-    {
-      "Sid": "AssumeOnlyThePersonaRoles",
-      "Effect": "Allow",
-      "Action": "sts:AssumeRole",
-      "Resource": [
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-01",
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-02",
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-03",
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-04",
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-05",
-        "arn:aws:iam::<ACCOUNT_ID>:role/argus-lab/argus-ueba-actors-persona-06"
-      ]
-    },
-    {
-      "Sid": "ReadTheMigrationPackOnly",
-      "Effect": "Allow",
-      "Action": "s3:GetObject",
-      "Resource": "arn:aws:s3:::<MIGRATION_BUCKET>/migrate/*"
-    }
-  ]
-}
+{
+  "Version": "2012-10-17",
+  "Statement": [
+    {
+      "Sid": "ConsumeTheOneEventQueue",
+      "Effect": "Allow",
+      "Action": [
+        "sqs:ReceiveMessage",
+        "sqs:DeleteMessage",
+        "sqs:GetQueueAttributes"
+      ],
+      "Resource": "arn:aws:sqs:us-east-1:<ACCOUNT_ID>:<QUEUE_NAME>"
+    },
+    {
+      "Sid": "ReadTheMigrationPackOnly",
+      "Effect": "Allow",
+      "Action": "s3:GetObject",
+      "Resource": "arn:aws:s3:::<MIGRATION_BUCKET>/migrate/<PACK_ID>/*"
+    }
+  ]
+}
diff --git a/scripts/argus_supervisor.py b/scripts/argus_supervisor.py
index 86783b4..4201173 100644
--- a/scripts/argus_supervisor.py
+++ b/scripts/argus_supervisor.py
@@ -15,6 +15,7 @@ from datetime import datetime, timedelta, timezone
 import json
 import os
 from pathlib import Path
+import re
 import sqlite3
 import subprocess
 import sys
@@ -27,6 +28,9 @@ from scripts import ops_collect  # noqa: E402
 from scripts.local_pilot import atomic_json  # noqa: E402
 
 FAIL_LIMIT, FAIL_WINDOW, BACKOFF_CAP, HEALTH_EVERY = 5, 600, 60, 30
+# Provider credentials: only the collector and persona children get them (the web-facing children must not).
+SECRET_ENV = re.compile(r'^(AWS_(SHARED_CREDENTIALS_FILE|CONFIG_FILE|PROFILE|ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)'
+                        r'|(GH|GITHUB)_[A-Z_]*TOKEN|(CLOUDFLARE|CF)_.*)$', re.I)
 NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
 
 
@@ -90,6 +94,11 @@ def prepare_workspace(cfg):
     return folder
 
 
+def scrubbed(environ):
+    """environ without any provider credential variable (case-insensitive, so Windows spellings match too)."""
+    return {k: v for k, v in environ.items() if not SECRET_ENV.match(k)}
+
+
 def components(cfg, config_path):
     s = cfg['supervisor']
     python = s.get('python') or sys.executable
@@ -97,7 +106,8 @@ def components(cfg, config_path):
     ui = f"http://127.0.0.1:{s['web_ui_port']}"
     logs = cfg['status_dir'] / 'logs'
     logs.mkdir(parents=True, exist_ok=True)
-    base = {**os.environ, 'DATABASE_URL': 'sqlite-local', 'ARGUS_LOG_DIR': str(logs)}
+    base = {**scrubbed(os.environ), 'DATABASE_URL': 'sqlite-local', 'ARGUS_LOG_DIR': str(logs)}
+    collector_env = {**os.environ, 'DATABASE_URL': 'sqlite-local', 'ARGUS_LOG_DIR': str(logs)}  # keeps the credentials
     auth = cfg.get('auth', {})
     workspace_env = {**base, 'ARGUS_WORKSPACE_COPY_DB': str(workspace / 'preview.db'), 'ARGUS_WORKSPACE_UI_ORIGIN': ui,
                      'ARGUS_SUPERVISOR_HEALTH': str(cfg['status_dir'] / 'health.json')}
@@ -107,8 +117,8 @@ def components(cfg, config_path):
     conf = str(config_path)
     result = [
         Child('ingest-api', [python, str(ROOT / 'scripts/ops_collect.py'), 'serve', '--config', conf], env=base),
-        Child('collector', [python, str(ROOT / 'scripts/ops_collect.py'), 'loop', '--config', conf], env=base),
-        Child('personas', [python, str(ROOT / 'scripts/ops_personas.py'), 'loop', '--config', conf], env=base),
+        Child('collector', [python, str(ROOT / 'scripts/ops_collect.py'), 'loop', '--config', conf], env=collector_env),
+        Child('personas', [python, str(ROOT / 'scripts/ops_personas.py'), 'loop', '--config', conf], env=collector_env),
         Child('mirror', [python, '-m', 'workspace_next.live_mirror', '--source', str(cfg['live_state_dir'] / 'events.db'),
                          '--dest', str(workspace / 'preview.db'), '--interval', str(s.get('mirror_interval_seconds', 60))], env=base),
         Child('workspace-api', [python, '-m', 'uvicorn', 'workspace_next.app:create_app', '--factory', '--host', '127.0.0.1',
@@ -133,7 +143,7 @@ def drift_daily(python, db, today=None, spawn=subprocess.Popen):
             return
         state['day'] = day
         try:
-            spawn([python, '-m', 'backend.drift_monitor', '--db', str(db)], cwd=ROOT, env={**os.environ, 'DATABASE_URL': 'sqlite-local'},
+            spawn([python, '-m', 'backend.drift_monitor', '--db', str(db)], cwd=ROOT, env={**scrubbed(os.environ), 'DATABASE_URL': 'sqlite-local'},
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
         except OSError:
             pass
diff --git a/scripts/cloud_migrate.py b/scripts/cloud_migrate.py
index f6939ac..dba658c 100644
--- a/scripts/cloud_migrate.py
+++ b/scripts/cloud_migrate.py
@@ -1,209 +1,235 @@
-"""Move the operational stores between hosts (laptop <-> cloud server) without a raw file copy.
-
-  python scripts/cloud_migrate.py pack   --config ops.json --bundle <pinned AE v2 bundle dir> --out <new folder>
-  python scripts/cloud_migrate.py verify --pack <folder>                                   (transfer intact?)
-  python scripts/cloud_migrate.py verify --pack <folder> --config ops.json --bundle <dir>  (installed copies equal?)
-
-pack copies every SQLite file with the backup API (consistent even while the source is in WAL mode), plain files
-byte for byte, and writes migrate-manifest.json: per table row count and max(id), sha256 of every other file, and
-the sha256 of the baseline method-binding file in this checkout. verify recomputes the same and exits 1 on any
-difference. Prints counts and names only, never file contents. Run pack only after the collector has drained.
-"""
-from __future__ import annotations
-
-import argparse
-from contextlib import closing
-from datetime import datetime, timezone
-import hashlib
-import json
-from pathlib import Path
-import shutil
-import sqlite3
-import sys
-
-ROOT = Path(__file__).resolve().parents[1]
-if str(ROOT) not in sys.path:
-    sys.path.insert(0, str(ROOT))
-from scripts import ops_collect  # noqa: E402
-
-MANIFEST = 'migrate-manifest.json'
-SCHEMA = 'argus_cloud_migrate_v1'
-METHOD_FILE = 'config/baseline_method_v1_2.json'
-SIDE_FILES = ('system-accounts.json', 'workload-groups.json')  # small workspace settings next to preview.db
-SKIP_SUFFIXES = ('-wal', '-shm', '.lock', '.tmp')
-
-
-def sha256(path):
-    digest = hashlib.sha256()
-    with Path(path).open('rb') as handle:
-        for block in iter(lambda: handle.read(1 << 20), b''):
-            digest.update(block)
-    return digest.hexdigest()
-
-
-def table_stats(path):
-    """{table: {'rows', 'max_id'}} for every user table (max_id None when the table has no id column)."""
-    uri = Path(path).resolve().as_uri() + '?mode=ro'
-    with closing(sqlite3.connect(uri, uri=True)) as db:
-        stats = {}
-        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
-            quoted = '"' + name.replace('"', '""') + '"'
-            has_id = any(col[1] == 'id' for col in db.execute(f'PRAGMA table_info({quoted})'))
-            rows, top = db.execute(f'SELECT count(*), {"max(id)" if has_id else "NULL"} FROM {quoted}').fetchone()
-            stats[name] = {'rows': rows, 'max_id': top}
-        return stats
-
-
-def entries(cfg, bundle):
-    """(name inside the pack, path on a host, kind) for every store; names are the same on both hosts."""
-    s = cfg['supervisor']
-    workspace = ops_collect._path(s['workspace_dir'])
-    out = [('events.db', cfg['live_state_dir'] / 'events.db', 'db'), ('preview.db', workspace / 'preview.db', 'db'),
-           ('ticks', cfg['status_dir'] / ops_collect.TICKS_DIR, 'dir'), ('bundle', Path(bundle), 'dir')]
-    auth = cfg.get('auth', {})
-    for key, name in (('users_file', 'auth/users.json'), ('secret_file', 'auth/session.key')):
-        if auth.get(key):
-            out.append((name, ops_collect._path(auth[key]), 'file'))
-    if cfg.get('personas', {}).get('ledger_dir'):
-        out.append(('ledger', cfg['personas']['ledger_dir'], 'dir'))
-    out += [(f'side/{n}', workspace / n, 'file') for n in SIDE_FILES if (workspace / n).is_file()]
-    return out
-
-
-def pack_entries(root):
-    """Same entries read back from a pack folder."""
-    root = Path(root)
-    names = json.loads((root / MANIFEST).read_text(encoding='utf-8'))['entries']
-    return [(n, root / n, k) for n, k in names.items()]
-
-
-def describe(items):
-    """{'dbs': {name: table stats}, 'files': {name: sha256}} for the entries; a missing source is an error."""
-    dbs, files = {}, {}
-    for name, path, kind in items:
-        path = Path(path)
-        if kind == 'dir':
-            if not path.is_dir():
-                raise ValueError(f'missing folder: {name}')
-            found = [(f'{name}/{p.relative_to(path).as_posix()}', p) for p in sorted(path.rglob('*'))
-                     if p.is_file() and not p.name.endswith(SKIP_SUFFIXES)]
-        elif path.is_file():
-            found = [(name, path)]
-        else:
-            raise ValueError(f'missing file: {name}')
-        for rel, p in found:
-            if p.suffix == '.db':
-                dbs[rel] = table_stats(p)
-            else:
-                files[rel] = sha256(p)
-    return {'dbs': dbs, 'files': files}
-
-
-def method_sha():
-    return sha256(ROOT / METHOD_FILE)
-
-
-def differences(expected, actual):
-    """Human-readable list of what differs between two describe() results (empty = identical)."""
-    bad = []
-    for kind in ('dbs', 'files'):
-        for name in sorted(set(expected[kind]) | set(actual[kind])):
-            if expected[kind].get(name) != actual[kind].get(name):
-                bad.append(f'{kind[:-1]} differs or is missing: {name}')
-    return bad
-
-
-def copy_db(source, dest):
-    dest.parent.mkdir(parents=True, exist_ok=True)
-    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(dest)) as out:
-        src.backup(out)
-
-
-def copy_file(source, dest):
-    if Path(source).suffix == '.db':
-        copy_db(source, dest)
-    else:
-        dest.parent.mkdir(parents=True, exist_ok=True)
-        shutil.copyfile(source, dest)
-
-
-def pack(cfg, bundle, out):
-    out = Path(out)
-    if out.exists() and any(out.iterdir()):
-        raise ValueError('Output folder must be new or empty')
-    kinds = {}
-    for name, source, kind in entries(cfg, bundle):
-        source = Path(source)
-        if kind == 'dir':
-            if not source.is_dir():
-                raise ValueError(f'missing folder: {name}')
-            for p in sorted(source.rglob('*')):
-                if p.is_file() and not p.name.endswith(SKIP_SUFFIXES):
-                    copy_file(p, out / name / p.relative_to(source))
-            (out / name).mkdir(parents=True, exist_ok=True)
-        elif not source.is_file():
-            raise ValueError(f'missing file: {name}')
-        else:
-            copy_file(source, out / name)
-        kinds[name] = kind
-    manifest = {'schema': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(), 'entries': kinds,
-                'method_binding_sha256': method_sha(), **describe(pack_entries_from(out, kinds))}
-    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
-    return manifest
-
-
-def pack_entries_from(root, kinds):
-    return [(n, Path(root) / n, k) for n, k in kinds.items()]
-
-
-def verify(pack_dir, cfg=None, bundle=None):
-    """List of differences; [] means the pack (or, with cfg, the installed copies) match the manifest."""
-    manifest = json.loads((Path(pack_dir) / MANIFEST).read_text(encoding='utf-8'))
-    if manifest.get('schema') != SCHEMA:
-        raise ValueError('Unknown manifest schema')
-    if cfg is None:
-        items, bad = pack_entries(pack_dir), []
-    else:
-        have = {n: (n, p, k) for n, p, k in entries(cfg, bundle)}
-        items = [have[n] for n in manifest['entries'] if n in have]
-        bad = [f'not configured or missing on this host: {n}' for n in manifest['entries'] if n not in have]
-    try:
-        actual = describe(items)
-    except ValueError as error:
-        return [str(error)]
-    bad += differences(manifest, actual)
-    if manifest['method_binding_sha256'] != method_sha():
-        bad.append('baseline method-binding file differs from this checkout')
-    return bad
-
-
-def main(argv=None):
-    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
-    parser.add_argument('mode', choices=['pack', 'verify'])
-    parser.add_argument('--config', type=Path)
-    parser.add_argument('--bundle', type=Path)
-    parser.add_argument('--out', type=Path)
-    parser.add_argument('--pack', type=Path)
-    args = parser.parse_args(argv)
-    try:
-        cfg = ops_collect.load_config(args.config) if args.config else None
-        if args.mode == 'pack':
-            if not (cfg and args.bundle and args.out):
-                raise ValueError('pack needs --config, --bundle and --out')
-            manifest = pack(cfg, args.bundle, args.out)
-            print(json.dumps({'status': 'packed', 'databases': {n: {t: v['rows'] for t, v in s.items()} for n, s in manifest['dbs'].items()},
-                              'files': len(manifest['files'])}))
-            return 0
-        if not args.pack or bool(cfg) != bool(args.bundle):
-            raise ValueError('verify needs --pack, and --config together with --bundle for the installed copies')
-        bad = verify(args.pack, cfg, args.bundle)
-        print(json.dumps({'status': 'verified' if not bad else 'differences', 'differences': bad}))
-        return 1 if bad else 0
-    except Exception as error:  # kind only: messages could carry paths
-        print(json.dumps({'status': 'stopped', 'error_kind': type(error).__name__,
-                          'detail': str(error) if isinstance(error, ValueError) else ''}))
-        return 1
-
-
-if __name__ == '__main__':
-    raise SystemExit(main())
+"""Move the operational stores between hosts (laptop <-> cloud server) without a raw file copy.
+
+  python scripts/cloud_migrate.py pack   --config ops.json --bundle <pinned AE v2 bundle dir> --out <new folder>
+  python scripts/cloud_migrate.py verify --pack <folder>                                   (transfer intact?)
+  python scripts/cloud_migrate.py verify --pack <folder> --config ops.json --bundle <dir>  (installed copies equal?)
+
+pack copies every SQLite file with the backup API (consistent even while the source is in WAL mode), plain files
+byte for byte, and writes migrate-manifest.json: per table row count and max(id) for SQLite stores, sha256 of every
+packed file (databases included), and the sha256 of the baseline method-binding file in this checkout. verify
+recomputes the same and exits 1 on any difference, on a missing REQUIRED entry, on any unlisted file in the pack, and
+on any symlink or path leaving its folder. Prints counts and names only, never file contents. Run pack only after the collector has drained.
+"""
+from __future__ import annotations
+
+import argparse
+from contextlib import closing
+from datetime import datetime, timezone
+import hashlib
+import json
+from pathlib import Path
+import shutil
+import sqlite3
+import sys
+
+ROOT = Path(__file__).resolve().parents[1]
+if str(ROOT) not in sys.path:
+    sys.path.insert(0, str(ROOT))
+from scripts import ops_collect  # noqa: E402
+
+MANIFEST = 'migrate-manifest.json'
+SCHEMA = 'argus_cloud_migrate_v1'
+METHOD_FILE = 'config/baseline_method_v1_2.json'
+SIDE_FILES = ('system-accounts.json', 'workload-groups.json')  # small workspace settings next to preview.db
+SKIP_SUFFIXES = ('-wal', '-shm', '.lock', '.tmp')
+REQUIRED = ('events.db', 'preview.db', 'ticks', 'bundle')  # fixed: a pack missing any of these is never valid
+
+
+def sha256(path):
+    digest = hashlib.sha256()
+    with Path(path).open('rb') as handle:
+        for block in iter(lambda: handle.read(1 << 20), b''):
+            digest.update(block)
+    return digest.hexdigest()
+
+
+def table_stats(path):
+    """{table: {'rows', 'max_id'}} for every user table (max_id None when the table has no id column)."""
+    uri = Path(path).resolve().as_uri() + '?mode=ro&immutable=1'  # immutable: never creates -wal/-shm beside a pack file
+    with closing(sqlite3.connect(uri, uri=True)) as db:
+        stats = {}
+        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
+            quoted = '"' + name.replace('"', '""') + '"'
+            has_id = any(col[1] == 'id' for col in db.execute(f'PRAGMA table_info({quoted})'))
+            rows, top = db.execute(f'SELECT count(*), {"max(id)" if has_id else "NULL"} FROM {quoted}').fetchone()
+            stats[name] = {'rows': rows, 'max_id': top}
+        return stats
+
+
+def entries(cfg, bundle):
+    """(name inside the pack, path on a host, kind) for every store; names are the same on both hosts."""
+    s = cfg['supervisor']
+    workspace = ops_collect._path(s['workspace_dir'])
+    out = [('events.db', cfg['live_state_dir'] / 'events.db', 'db'), ('preview.db', workspace / 'preview.db', 'db'),
+           ('ticks', cfg['status_dir'] / ops_collect.TICKS_DIR, 'dir'), ('bundle', Path(bundle), 'dir')]
+    auth = cfg.get('auth', {})
+    for key, name in (('users_file', 'auth/users.json'), ('secret_file', 'auth/session.key')):
+        if auth.get(key):
+            out.append((name, ops_collect._path(auth[key]), 'file'))
+    if cfg.get('personas', {}).get('ledger_dir'):
+        out.append(('ledger', cfg['personas']['ledger_dir'], 'dir'))
+    out += [(f'side/{n}', workspace / n, 'file') for n in SIDE_FILES if (workspace / n).is_file()]
+    return out
+
+
+def walk_files(root):
+    """Regular files under root, sorted. Refuses symlinks/junctions and anything resolving outside root."""
+    root = Path(root)
+    real = root.resolve()
+    found = []
+    for p in sorted(root.rglob('*')):
+        if p.is_symlink() or getattr(p, 'is_junction', lambda: False)() or not p.resolve().is_relative_to(real):
+            raise ValueError(f'link or path outside its folder: {p.relative_to(root).as_posix()}')
+        if p.is_file():
+            found.append(p)
+    return found
+
+
+def pack_entries(root):
+    """Same entries read back from a pack folder."""
+    root = Path(root)
+    names = json.loads((root / MANIFEST).read_text(encoding='utf-8'))['entries']
+    for n in names:
+        if not (root / n).resolve().is_relative_to(root.resolve()):
+            raise ValueError(f'manifest name leaves the pack: {n}')
+    return [(n, root / n, k) for n, k in names.items()]
+
+
+def describe(items):
+    """{'dbs': {name: table stats}, 'files': {name: sha256}} for the entries; a missing source is an error."""
+    dbs, files = {}, {}
+    for name, path, kind in items:
+        path = Path(path)
+        if kind == 'dir':
+            if not path.is_dir():
+                raise ValueError(f'missing folder: {name}')
+            found = [(f'{name}/{p.relative_to(path).as_posix()}', p) for p in walk_files(path)
+                     if not p.name.endswith(SKIP_SUFFIXES)]
+        elif path.is_symlink():
+            raise ValueError(f'link instead of a file: {name}')
+        elif path.is_file():
+            found = [(name, path)]
+        else:
+            raise ValueError(f'missing file: {name}')
+        for rel, p in found:
+            if p.suffix == '.db':
+                dbs[rel] = table_stats(p)
+            files[rel] = sha256(p)
+    return {'dbs': dbs, 'files': files}
+
+
+def method_sha():
+    return sha256(ROOT / METHOD_FILE)
+
+
+def differences(expected, actual):
+    """Human-readable list of what differs between two describe() results (empty = identical)."""
+    bad = []
+    for kind in ('dbs', 'files'):
+        for name in sorted(set(expected[kind]) | set(actual[kind])):
+            if expected[kind].get(name) != actual[kind].get(name):
+                bad.append(f'{kind[:-1]} differs or is missing: {name}')
+    return bad
+
+
+def copy_db(source, dest):
+    dest.parent.mkdir(parents=True, exist_ok=True)
+    with closing(sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)) as src, closing(sqlite3.connect(dest)) as out:
+        src.backup(out)
+
+
+def copy_file(source, dest):
+    if Path(source).suffix == '.db':
+        copy_db(source, dest)
+    else:
+        dest.parent.mkdir(parents=True, exist_ok=True)
+        shutil.copyfile(source, dest)
+
+
+def pack(cfg, bundle, out):
+    out = Path(out)
+    if out.exists() and any(out.iterdir()):
+        raise ValueError('Output folder must be new or empty')
+    kinds = {}
+    for name, source, kind in entries(cfg, bundle):
+        source = Path(source)
+        if kind == 'dir':
+            if not source.is_dir():
+                raise ValueError(f'missing folder: {name}')
+            for p in walk_files(source):
+                if not p.name.endswith(SKIP_SUFFIXES):
+                    copy_file(p, out / name / p.relative_to(source))
+            (out / name).mkdir(parents=True, exist_ok=True)
+        elif source.is_symlink() or not source.is_file():
+            raise ValueError(f'missing file or link: {name}')
+        else:
+            copy_file(source, out / name)
+        kinds[name] = kind
+    manifest = {'schema': SCHEMA, 'created_utc': datetime.now(timezone.utc).isoformat(), 'entries': kinds,
+                'method_binding_sha256': method_sha(), **describe(pack_entries_from(out, kinds))}
+    (out / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
+    return manifest
+
+
+def pack_entries_from(root, kinds):
+    return [(n, Path(root) / n, k) for n, k in kinds.items()]
+
+
+def verify(pack_dir, cfg=None, bundle=None):
+    """List of differences; [] means the pack (or, with cfg, the installed copies) match the manifest."""
+    manifest = json.loads((Path(pack_dir) / MANIFEST).read_text(encoding='utf-8'))
+    if manifest.get('schema') != SCHEMA:
+        raise ValueError('Unknown manifest schema')
+    bad = [f'required entry missing from manifest: {n}' for n in REQUIRED if n not in manifest['entries']]
+    if not any(n.startswith('bundle/') for n in manifest['files']):
+        bad.append('required entry empty: bundle')
+    try:
+        if cfg is None:
+            items = pack_entries(pack_dir)
+            listed = set(manifest['files']) | {MANIFEST}
+            bad += [f'unlisted file in pack: {p.relative_to(pack_dir).as_posix()}' for p in walk_files(pack_dir)
+                    if p.relative_to(pack_dir).as_posix() not in listed]
+        else:
+            have = {n: (n, p, k) for n, p, k in entries(cfg, bundle)}
+            items = [have[n] for n in manifest['entries'] if n in have]
+            bad += [f'not configured or missing on this host: {n}' for n in manifest['entries'] if n not in have]
+            bad += [f'configured here but absent from manifest: {n}' for n in have if n not in manifest['entries']]
+        actual = describe(items)
+    except ValueError as error:
+        return bad + [str(error)]
+    bad += differences(manifest, actual)
+    if manifest['method_binding_sha256'] != method_sha():
+        bad.append('baseline method-binding file differs from this checkout')
+    return bad
+
+
+def main(argv=None):
+    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
+    parser.add_argument('mode', choices=['pack', 'verify'])
+    parser.add_argument('--config', type=Path)
+    parser.add_argument('--bundle', type=Path)
+    parser.add_argument('--out', type=Path)
+    parser.add_argument('--pack', type=Path)
+    args = parser.parse_args(argv)
+    try:
+        cfg = ops_collect.load_config(args.config) if args.config else None
+        if args.mode == 'pack':
+            if not (cfg and args.bundle and args.out):
+                raise ValueError('pack needs --config, --bundle and --out')
+            manifest = pack(cfg, args.bundle, args.out)
+            print(json.dumps({'status': 'packed', 'databases': {n: {t: v['rows'] for t, v in s.items()} for n, s in manifest['dbs'].items()},
+                              'files': len(manifest['files'])}))
+            return 0
+        if not args.pack or bool(cfg) != bool(args.bundle):
+            raise ValueError('verify needs --pack, and --config together with --bundle for the installed copies')
+        bad = verify(args.pack, cfg, args.bundle)
+        print(json.dumps({'status': 'verified' if not bad else 'differences', 'differences': bad}))
+        return 1 if bad else 0
+    except Exception as error:  # kind only: messages could carry paths
+        print(json.dumps({'status': 'stopped', 'error_kind': type(error).__name__,
+                          'detail': str(error) if isinstance(error, ValueError) else ''}))
+        return 1
+
+
+if __name__ == '__main__':
+    raise SystemExit(main())
diff --git a/scripts/tests/test_argus_supervisor.py b/scripts/tests/test_argus_supervisor.py
index e9907da..a607194 100644
--- a/scripts/tests/test_argus_supervisor.py
+++ b/scripts/tests/test_argus_supervisor.py
@@ -138,27 +138,46 @@ def test_workspace_components_endpoint_reads_health(monkeypatch, tmp_path):
         sign_in(client, tmp_path / 'auth' / 'users.json')
         body = client.get('/workspace/components').json()
     assert body['available'] and [c['name'] for c in body['components']] == ['collector']
-
-
-def test_drift_daily_spawns_once_per_myt_day_and_never_raises(tmp_path):
-    started = []
-    tick = sup.drift_daily('py', tmp_path / 'preview.db', spawn=lambda argv, **kw: started.append(argv))
-    tick(1_700_000_000.0); tick(1_700_000_060.0)
-    assert len(started) == 1 and started[0][1:3] == ['-m', 'backend.drift_monitor']
-    tick(1_700_000_000.0 + 86400)
-    assert len(started) == 2
-
-    def broken(argv, **kw):
-        raise OSError('no python')
-    sup.drift_daily('py', tmp_path / 'x.db', spawn=broken)(1_700_000_000.0)  # swallowed
-
-
-def test_run_survives_a_failing_daily_hook():
-    calls = []
-
-    def daily(now):
-        calls.append(now)
-        raise RuntimeError('boom')
-    ticks = iter([False, False, True])
-    sup.run([], None, spawn=None, clock=lambda: 0.0, sleep=lambda s: None, until=lambda: next(ticks), daily=daily)
-    assert len(calls) == 2
+
+
+def test_drift_daily_spawns_once_per_myt_day_and_never_raises(tmp_path):
+    started = []
+    tick = sup.drift_daily('py', tmp_path / 'preview.db', spawn=lambda argv, **kw: started.append(argv))
+    tick(1_700_000_000.0); tick(1_700_000_060.0)
+    assert len(started) == 1 and started[0][1:3] == ['-m', 'backend.drift_monitor']
+    tick(1_700_000_000.0 + 86400)
+    assert len(started) == 2
+
+    def broken(argv, **kw):
+        raise OSError('no python')
+    sup.drift_daily('py', tmp_path / 'x.db', spawn=broken)(1_700_000_000.0)  # swallowed
+
+
+def test_run_survives_a_failing_daily_hook():
+    calls = []
+
+    def daily(now):
+        calls.append(now)
+        raise RuntimeError('boom')
+    ticks = iter([False, False, True])
+    sup.run([], None, spawn=None, clock=lambda: 0.0, sleep=lambda s: None, until=lambda: next(ticks), daily=daily)
+    assert len(calls) == 2
+
+
+def test_only_collector_and_personas_children_get_provider_credentials(tmp_path, monkeypatch):
+    secrets = {'AWS_SHARED_CREDENTIALS_FILE': 'x', 'AWS_PROFILE': 'x', 'AWS_ACCESS_KEY_ID': 'x', 'AWS_SECRET_ACCESS_KEY': 'x',
+               'GH_TOKEN': 'x', 'GITHUB_TOKEN': 'x', 'CLOUDFLARE_API_TOKEN': 'x'}
+    for k, v in secrets.items():
+        monkeypatch.setenv(k, v)
+    cfg = make_config(tmp_path)
+    cfg['live_state_dir'].mkdir(parents=True)
+    with sqlite3.connect(cfg['live_state_dir'] / 'events.db') as db:
+        db.execute('CREATE TABLE events(id INTEGER)')
+    cfg['supervisor'] = {'workspace_dir': str(tmp_path / 'workspace'), 'workspace_api_port': 8021, 'web_ui_port': 3016,
+                         'python': sys.executable, 'node': 'node', 'frontend_dir': str(tmp_path / 'frontend')}
+    cfg['auth'] = {'users_file': str(tmp_path / 'auth' / 'users.json'), 'secret_file': str(tmp_path / 'auth' / 'session.key')}
+    by_name = {c.name: c for c in sup.components(cfg, tmp_path / 'ops.json')}
+    for name in ('collector', 'personas'):
+        assert all(by_name[name].env.get(k) == 'x' for k in secrets), name
+    for name in ('ingest-api', 'mirror', 'workspace-api', 'notifier', 'web-ui'):
+        assert not [k for k in by_name[name].env if k.upper() in secrets], name
diff --git a/scripts/tests/test_cloud_deploy.py b/scripts/tests/test_cloud_deploy.py
index 1f367bf..66ee767 100644
--- a/scripts/tests/test_cloud_deploy.py
+++ b/scripts/tests/test_cloud_deploy.py
@@ -1,242 +1,306 @@
-"""R3 cloud deploy: Linux secret loading, portable lock, null AWS profile, cloud_migrate pack/verify, deploy/ files.
-Temp folders and fixture values only. Windows-only and Linux-only branches skip on the other platform."""
-import json
-import os
-from pathlib import Path
-import re
-import sqlite3
-from types import SimpleNamespace
-
-import pytest
-
-from scripts import cloud_migrate, collect_live, linux_compat, ops_collect, ops_personas
-from scripts.tests.test_ops_collect import make_config
-
-ROOT = Path(__file__).resolve().parents[2]
-DEPLOY = ROOT / 'deploy'
-posix_only = pytest.mark.skipif(os.name == 'nt', reason='Linux branch')
-
-
-# ---- secrets ----------------------------------------------------------------------------------------------
-
-def stat(mode, uid=1000):
-    return SimpleNamespace(st_mode=mode, st_uid=uid)
-
-
-def test_secret_file_rule_is_owner_and_mode_0600_only():
-    linux_compat.check_secret_file(stat(0o100600), 1000)
-    for bad in (stat(0o100644), stat(0o100640), stat(0o100700), stat(0o100400), stat(0o100600, uid=0), stat(0o040600)):
-        with pytest.raises(PermissionError):
-            linux_compat.check_secret_file(bad, 1000)
-
-
-def test_secret_names_cannot_escape_the_folder(tmp_path):
-    for name in ('', '../x', 'a/b', '.hidden', 'a\\b'):
-        with pytest.raises(ValueError):
-            linux_compat.read_secret(name, base=tmp_path)
-
-
-@posix_only
-def test_secret_file_with_mode_0644_is_refused_and_0600_is_read(tmp_path):
-    secret = tmp_path / 'persona-01'
-    secret.write_text('  fixture-value\n')
-    secret.chmod(0o644)
-    with pytest.raises(PermissionError):
-        linux_compat.read_secret('persona-01', base=tmp_path)
-    secret.chmod(0o600)
-    assert linux_compat.read_secret('persona-01', base=tmp_path) == 'fixture-value'
-
-
-def pilot_config(state):
-    (state / 'pilot-config.json').write_text(json.dumps({
-        'host': 'argus-machine-lab.test.workers.dev', 'tokens': {'persona-01': {'id': 'tid', 'client_id': 'cid.access'}}}))
-
-
-@posix_only
-def test_persona_loader_reads_the_secret_file_on_linux(tmp_path, monkeypatch):
-    state = tmp_path / 'state'
-    state.mkdir()
-    pilot_config(state)
-    secret = tmp_path / 'persona-01'
-    secret.write_text(json.dumps({'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'}))
-    secret.chmod(0o600)
-    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
-    assert ops_personas.cf_loader(state, 'persona-01') == ('argus-machine-lab.test.workers.dev', 'cid.access', 'fixture')
-    secret.chmod(0o644)
-    with pytest.raises(PermissionError):
-        ops_personas.cf_loader(state, 'persona-01')
-
-
-@pytest.mark.skipif(os.name != 'nt', reason='Windows branch')
-def test_windows_persona_loader_still_uses_dpapi(tmp_path, monkeypatch):
-    from scripts import github_lab_app
-    pilot_config(tmp_path)
-    seen = []
-    monkeypatch.setattr(github_lab_app, 'load_secret',
-                        lambda p: seen.append(Path(p).name) or {'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'})
-    assert ops_personas.cf_loader(tmp_path, 'persona-01')[2] == 'fixture' and seen == ['persona-01.dpapi']
-
-
-@posix_only
-def test_cloudflare_collector_reads_its_api_token_from_the_secret_file(tmp_path, monkeypatch):
-    from scripts import setup_cloudflare
-    secret = tmp_path / 'cloudflare-api-token'
-    secret.write_text('fixture-token')
-    secret.chmod(0o600)
-    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
-    seen = {}
-
-    class Api:
-        def __init__(self, account, token):
-            seen['token'] = token
-
-        def call(self, *a, **k):
-            return []
-
-    monkeypatch.setattr(setup_cloudflare, 'Cloudflare', Api)
-    monkeypatch.setattr(collect_live, 'forward', lambda *a, **k: {'malformed': 0, 'retained': 0})
-    collect_live.collect_cloudflare(SimpleNamespace(account_id='a' * 32, app_id='x'), None)
-    assert seen['token'] == 'fixture-token'
-
-
-# ---- portable lock ----------------------------------------------------------------------------------------
-
-def test_lock_fails_fast_while_held_and_releases(tmp_path):
-    path = tmp_path / 'x.lock'
-    with linux_compat.lock(path):
-        with pytest.raises(OSError):
-            with linux_compat.lock(path):
-                pass
-    with linux_compat.lock(path):  # free again
-        pass
-
-
-# ---- null AWS profile -------------------------------------------------------------------------------------
-
-def test_null_aws_profile_means_the_default_credential_chain(tmp_path, monkeypatch):
-    cfg = make_config(tmp_path)
-    cfg['providers']['aws']['profile'] = None
-    seen = []
-    monkeypatch.setattr(collect_live, 'collect_aws', lambda args, backend: seen.append(args.profile) or {})
-    ops_collect.run_aws(cfg, None)
-    assert seen == [None]
-    cfg['providers']['aws'].pop('profile')
-    ops_collect.run_aws(cfg, None)
-    assert seen[-1] == 'argus-collector'  # unchanged default when the key is absent
-
-
-# ---- cloud_migrate ----------------------------------------------------------------------------------------
-
-def build_store(tmp_path):
-    """A small operational layout plus its config (WAL-mode databases, like the live store)."""
-    live, status, work = tmp_path / 'connected', tmp_path / 'ops', tmp_path / 'workspace'
-    ledger, auth, bundle = tmp_path / 'ledger', tmp_path / 'auth', tmp_path / 'bundle-v2'
-    for d in (live, status / 'ticks', work, ledger, auth, bundle):
-        d.mkdir(parents=True)
-    for path, rows in ((live / 'events.db', 5), (work / 'preview.db', 3), (ledger / 'ledger.db', 2)):
-        db = sqlite3.connect(path)
-        db.execute('PRAGMA journal_mode=WAL')
-        db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, v TEXT)')
-        db.execute('CREATE TABLE noid(k TEXT)')
-        db.executemany('INSERT INTO events(v) VALUES(?)', [(f'r{i}',) for i in range(rows)])
-        db.commit()
-        db.close()
-    (ledger / 'ops-ledger.json').write_text('{"schema":"x"}')
-    (status / 'ticks' / '2026-11-17-ticks.jsonl').write_text('{"ok":true}\n')
-    (auth / 'users.json').write_text('{}')
-    (auth / 'session.key').write_text('fixture')
-    (work / 'system-accounts.json').write_text('{"labels":[]}')
-    (bundle / 'manifest.json').write_text('{"m":1}')
-    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
-    cfg = make_config(tmp_path, live_state_dir=str(live), status_dir=str(status),
-                      personas={'enabled': False, 'start_local': '2026-11-16', 'ledger_dir': str(ledger)},
-                      supervisor={'workspace_dir': str(work)},
-                      auth={'users_file': str(auth / 'users.json'), 'secret_file': str(auth / 'session.key')})
-    return cfg, bundle
-
-
-def test_pack_then_verify_round_trip_and_a_deleted_row_is_caught(tmp_path):
-    cfg, bundle = build_store(tmp_path)
-    out = tmp_path / 'pack'
-    manifest = cloud_migrate.pack(cfg, bundle, out)
-    assert manifest['dbs']['events.db']['events'] == {'rows': 5, 'max_id': 5}
-    assert manifest['dbs']['events.db']['noid'] == {'rows': 0, 'max_id': None}
-    assert 'bundle/model.pt' in manifest['files'] and 'ticks/2026-11-17-ticks.jsonl' in manifest['files']
-    assert manifest['method_binding_sha256'] == cloud_migrate.method_sha()
-    assert cloud_migrate.verify(out) == []
-    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 0
-    assert cloud_migrate.verify(out, cfg, bundle) == []  # installed copies (here: the source itself) equal the pack
-    db = sqlite3.connect(out / 'preview.db')  # one row lost in transfer
-    db.execute('DELETE FROM events WHERE id=3')
-    db.commit()
-    db.close()
-    assert any('preview.db' in d for d in cloud_migrate.verify(out))
-    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1
-
-
-def test_verify_catches_a_changed_file_and_a_missing_installed_store(tmp_path):
-    cfg, bundle = build_store(tmp_path)
-    out = tmp_path / 'pack'
-    cloud_migrate.pack(cfg, bundle, out)
-    (bundle / 'model.pt').write_bytes(b'tampered')
-    assert any('bundle/model.pt' in d for d in cloud_migrate.verify(out, cfg, bundle))
-    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
-    (tmp_path / 'ledger' / 'ledger.db').unlink()
-    assert any('ledger' in d for d in cloud_migrate.verify(out, cfg, bundle))
-
-
-def test_pack_refuses_a_used_output_folder_and_leaves_the_source_unchanged(tmp_path):
-    cfg, bundle = build_store(tmp_path)
-    out = tmp_path / 'pack'
-    out.mkdir()
-    (out / 'x').write_text('1')
-    with pytest.raises(ValueError):
-        cloud_migrate.pack(cfg, bundle, out)
-    before = cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db')
-    cloud_migrate.pack(cfg, bundle, tmp_path / 'pack2')
-    assert cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db') == before
-
-
-# ---- deploy/ files ----------------------------------------------------------------------------------------
-
-def test_iam_policy_has_no_wildcard_resource_and_no_iam_writes():
-    policy = json.loads((DEPLOY / 'iam-instance-policy.json').read_text())
-    for statement in policy['Statement']:
-        resources = statement['Resource'] if isinstance(statement['Resource'], list) else [statement['Resource']]
-        assert all(r != '*' and '*' not in r.replace('/migrate/*', '') for r in resources), statement['Sid']
-        actions = statement['Action'] if isinstance(statement['Action'], list) else [statement['Action']]
-        assert not any(a == '*' or a.endswith(':*') or a.startswith('iam:') for a in actions)
-    assume = next(s for s in policy['Statement'] if s['Action'] == 'sts:AssumeRole')
-    assert len(assume['Resource']) == 6 and all(re.search(r'-persona-0[1-6]$', r) for r in assume['Resource'])
-
-
-def test_tunnel_example_routes_only_the_ui_and_the_workspace_api():
-    text = (DEPLOY / 'cloudflared-config.example.yml').read_text()
-    services = re.findall(r'^\s*-?\s*service:\s*(\S+)', text, re.M)
-    assert services == ['http://127.0.0.1:8017', 'http://127.0.0.1:3013', 'http_status:404']
-    assert '8013' not in re.sub(r'^\s*#.*$', '', text, flags=re.M)
-
-
-def test_linux_ops_example_uses_the_instance_role_and_the_right_ports():
-    cfg = json.loads((DEPLOY / 'ops.linux.example.json').read_text())
-    assert cfg['schema'] == 'argus_ops_v1' and cfg['providers']['aws']['profile'] is None
-    assert cfg['providers']['cloudflare']['app_ids'] == ['<LAB_ACCESS_APP_ID>']  # the Access app's own id never listed
-    assert cfg['supervisor']['workspace_api_port'] == 8017 and cfg['supervisor']['web_ui_port'] == 3013
-    assert cfg['backend_url'].endswith(':8013')
-    assert cfg['live_state_dir'].startswith('/') and cfg['status_dir'].startswith('/')
-
-
-def test_instance_role_label_marks_it_as_infrastructure(tmp_path):
-    from workspace_next import system_accounts as sa
-    (tmp_path / sa.FILE).write_text((DEPLOY / 'system-accounts.example.json').read_text())
-    labels = sa.declared(tmp_path / 'preview.db')
-    assert sa.is_infrastructure('argus-ops-instance', 'role', 'aws_cloudtrail', labels)
-    assert not sa.is_infrastructure('argus-ueba-actors-persona-01', 'role', 'aws_cloudtrail', labels)
-
-
-def test_trust_statement_adds_one_principal_and_the_service_unit_is_gated():
-    trust = json.loads((DEPLOY / 'persona-trust-statement.json').read_text())
-    assert trust['Action'] == 'sts:AssumeRole' and trust['Principal']['AWS'].endswith(':role/<INSTANCE_ROLE_NAME>')
-    unit = (DEPLOY / 'argus.service').read_text()
-    assert 'ConditionPathExists=/var/lib/argus/CUTOVER_OK' in unit and 'Restart=always' in unit
-    assert 'scripts/argus_supervisor.py' in unit
+"""R3 cloud deploy: Linux secret loading, portable lock, null AWS profile, cloud_migrate pack/verify, deploy/ files.
+Temp folders and fixture values only. Windows-only and Linux-only branches skip on the other platform."""
+import json
+import os
+from pathlib import Path
+import re
+import shutil
+import sqlite3
+from types import SimpleNamespace
+
+import pytest
+
+from scripts import cloud_migrate, collect_live, linux_compat, ops_collect, ops_personas
+from scripts.tests.test_ops_collect import make_config
+
+ROOT = Path(__file__).resolve().parents[2]
+DEPLOY = ROOT / 'deploy'
+posix_only = pytest.mark.skipif(os.name == 'nt', reason='Linux branch')
+
+
+# ---- secrets ----------------------------------------------------------------------------------------------
+
+def stat(mode, uid=1000):
+    return SimpleNamespace(st_mode=mode, st_uid=uid)
+
+
+def test_secret_file_rule_is_owner_and_mode_0600_only():
+    linux_compat.check_secret_file(stat(0o100600), 1000)
+    for bad in (stat(0o100644), stat(0o100640), stat(0o100700), stat(0o100400), stat(0o100600, uid=0), stat(0o040600)):
+        with pytest.raises(PermissionError):
+            linux_compat.check_secret_file(bad, 1000)
+
+
+def test_secret_names_cannot_escape_the_folder(tmp_path):
+    for name in ('', '../x', 'a/b', '.hidden', 'a\\b'):
+        with pytest.raises(ValueError):
+            linux_compat.read_secret(name, base=tmp_path)
+
+
+@posix_only
+def test_secret_file_with_mode_0644_is_refused_and_0600_is_read(tmp_path):
+    secret = tmp_path / 'persona-01'
+    secret.write_text('  fixture-value\n')
+    secret.chmod(0o644)
+    with pytest.raises(PermissionError):
+        linux_compat.read_secret('persona-01', base=tmp_path)
+    secret.chmod(0o600)
+    assert linux_compat.read_secret('persona-01', base=tmp_path) == 'fixture-value'
+
+
+def pilot_config(state):
+    (state / 'pilot-config.json').write_text(json.dumps({
+        'host': 'argus-machine-lab.test.workers.dev', 'tokens': {'persona-01': {'id': 'tid', 'client_id': 'cid.access'}}}))
+
+
+@posix_only
+def test_persona_loader_reads_the_secret_file_on_linux(tmp_path, monkeypatch):
+    state = tmp_path / 'state'
+    state.mkdir()
+    pilot_config(state)
+    secret = tmp_path / 'persona-01'
+    secret.write_text(json.dumps({'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'}))
+    secret.chmod(0o600)
+    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
+    assert ops_personas.cf_loader(state, 'persona-01') == ('argus-machine-lab.test.workers.dev', 'cid.access', 'fixture')
+    secret.chmod(0o644)
+    with pytest.raises(PermissionError):
+        ops_personas.cf_loader(state, 'persona-01')
+
+
+@pytest.mark.skipif(os.name != 'nt', reason='Windows branch')
+def test_windows_persona_loader_still_uses_dpapi(tmp_path, monkeypatch):
+    from scripts import github_lab_app
+    pilot_config(tmp_path)
+    seen = []
+    monkeypatch.setattr(github_lab_app, 'load_secret',
+                        lambda p: seen.append(Path(p).name) or {'id': 'tid', 'client_id': 'cid.access', 'client_secret': 'fixture'})
+    assert ops_personas.cf_loader(tmp_path, 'persona-01')[2] == 'fixture' and seen == ['persona-01.dpapi']
+
+
+@posix_only
+def test_cloudflare_collector_reads_its_api_token_from_the_secret_file(tmp_path, monkeypatch):
+    from scripts import setup_cloudflare
+    secret = tmp_path / 'cloudflare-api-token'
+    secret.write_text('fixture-token')
+    secret.chmod(0o600)
+    monkeypatch.setattr(linux_compat, 'SECRET_DIR', tmp_path)
+    seen = {}
+
+    class Api:
+        def __init__(self, account, token):
+            seen['token'] = token
+
+        def call(self, *a, **k):
+            return []
+
+    monkeypatch.setattr(setup_cloudflare, 'Cloudflare', Api)
+    monkeypatch.setattr(collect_live, 'forward', lambda *a, **k: {'malformed': 0, 'retained': 0})
+    collect_live.collect_cloudflare(SimpleNamespace(account_id='a' * 32, app_id='x'), None)
+    assert seen['token'] == 'fixture-token'
+
+
+# ---- portable lock ----------------------------------------------------------------------------------------
+
+def test_lock_fails_fast_while_held_and_releases(tmp_path):
+    path = tmp_path / 'x.lock'
+    with linux_compat.lock(path):
+        with pytest.raises(OSError):
+            with linux_compat.lock(path):
+                pass
+    with linux_compat.lock(path):  # free again
+        pass
+
+
+# ---- null AWS profile -------------------------------------------------------------------------------------
+
+def test_null_aws_profile_means_the_default_credential_chain(tmp_path, monkeypatch):
+    cfg = make_config(tmp_path)
+    cfg['providers']['aws']['profile'] = None
+    seen = []
+    monkeypatch.setattr(collect_live, 'collect_aws', lambda args, backend: seen.append(args.profile) or {})
+    ops_collect.run_aws(cfg, None)
+    assert seen == [None]
+    cfg['providers']['aws'].pop('profile')
+    ops_collect.run_aws(cfg, None)
+    assert seen[-1] == 'argus-collector'  # unchanged default when the key is absent
+
+
+# ---- cloud_migrate ----------------------------------------------------------------------------------------
+
+def build_store(tmp_path):
+    """A small operational layout plus its config (WAL-mode databases, like the live store)."""
+    live, status, work = tmp_path / 'connected', tmp_path / 'ops', tmp_path / 'workspace'
+    ledger, auth, bundle = tmp_path / 'ledger', tmp_path / 'auth', tmp_path / 'bundle-v2'
+    for d in (live, status / 'ticks', work, ledger, auth, bundle):
+        d.mkdir(parents=True)
+    for path, rows in ((live / 'events.db', 5), (work / 'preview.db', 3), (ledger / 'ledger.db', 2)):
+        db = sqlite3.connect(path)
+        db.execute('PRAGMA journal_mode=WAL')
+        db.execute('CREATE TABLE events(id INTEGER PRIMARY KEY, v TEXT)')
+        db.execute('CREATE TABLE noid(k TEXT)')
+        db.executemany('INSERT INTO events(v) VALUES(?)', [(f'r{i}',) for i in range(rows)])
+        db.commit()
+        db.close()
+    (ledger / 'ops-ledger.json').write_text('{"schema":"x"}')
+    (status / 'ticks' / '2026-11-17-ticks.jsonl').write_text('{"ok":true}\n')
+    (auth / 'users.json').write_text('{}')
+    (auth / 'session.key').write_text('fixture')
+    (work / 'system-accounts.json').write_text('{"labels":[]}')
+    (bundle / 'manifest.json').write_text('{"m":1}')
+    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
+    cfg = make_config(tmp_path, live_state_dir=str(live), status_dir=str(status),
+                      personas={'enabled': False, 'start_local': '2026-11-16', 'ledger_dir': str(ledger)},
+                      supervisor={'workspace_dir': str(work)},
+                      auth={'users_file': str(auth / 'users.json'), 'secret_file': str(auth / 'session.key')})
+    return cfg, bundle
+
+
+def install(out, cfg):
+    """Stand-in for the owner's copy step: write the packed databases over the configured stores."""
+    shutil.copyfile(out / 'events.db', cfg['live_state_dir'] / 'events.db')
+    shutil.copyfile(out / 'preview.db', ops_collect._path(cfg['supervisor']['workspace_dir']) / 'preview.db')
+    shutil.copyfile(out / 'ledger' / 'ledger.db', cfg['personas']['ledger_dir'] / 'ledger.db')
+
+
+def test_pack_then_verify_round_trip_and_a_deleted_row_is_caught(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    manifest = cloud_migrate.pack(cfg, bundle, out)
+    assert manifest['dbs']['events.db']['events'] == {'rows': 5, 'max_id': 5}
+    assert manifest['dbs']['events.db']['noid'] == {'rows': 0, 'max_id': None}
+    assert 'bundle/model.pt' in manifest['files'] and 'ticks/2026-11-17-ticks.jsonl' in manifest['files']
+    assert manifest['method_binding_sha256'] == cloud_migrate.method_sha()
+    assert cloud_migrate.verify(out) == []
+    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 0
+    install(out, cfg)
+    assert cloud_migrate.verify(out, cfg, bundle) == []  # installed copies equal the pack
+    db = sqlite3.connect(out / 'preview.db')  # one row lost in transfer
+    db.execute('DELETE FROM events WHERE id=3')
+    db.commit()
+    db.close()
+    assert any('preview.db' in d for d in cloud_migrate.verify(out))
+    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1
+
+
+def test_verify_catches_a_changed_file_and_a_missing_installed_store(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    cloud_migrate.pack(cfg, bundle, out)
+    (bundle / 'model.pt').write_bytes(b'tampered')
+    assert any('bundle/model.pt' in d for d in cloud_migrate.verify(out, cfg, bundle))
+    (bundle / 'model.pt').write_bytes(b'\x00\x01\x02')
+    (tmp_path / 'ledger' / 'ledger.db').unlink()
+    assert any('ledger' in d for d in cloud_migrate.verify(out, cfg, bundle))
+
+
+def edit_cell_same_ids(path):
+    db = sqlite3.connect(path)
+    db.execute("UPDATE events SET v='tampered' WHERE id=2")
+    db.commit()
+    db.close()
+
+
+def test_edited_cell_with_unchanged_ids_and_counts_is_caught_in_pack_and_after_install(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    cloud_migrate.pack(cfg, bundle, out)
+    install(out, cfg)
+    edit_cell_same_ids(cfg['live_state_dir'] / 'events.db')  # installed copy altered
+    assert any('events.db' in d for d in cloud_migrate.verify(out, cfg, bundle))
+    edit_cell_same_ids(out / 'events.db')  # packed copy altered in transit
+    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1
+
+
+def test_deleting_a_store_and_its_manifest_entries_is_caught(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    cloud_migrate.pack(cfg, bundle, out)
+    (out / 'events.db').unlink()
+    path = out / cloud_migrate.MANIFEST
+    manifest = json.loads(path.read_text())
+    for key in ('entries', 'dbs', 'files'):
+        manifest[key].pop('events.db')
+    path.write_text(json.dumps(manifest))
+    assert any('events.db' in d for d in cloud_migrate.verify(out))
+    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1
+
+
+def test_an_extra_unlisted_file_in_the_pack_is_caught(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    cloud_migrate.pack(cfg, bundle, out)
+    (out / 'bundle' / 'extra.bin').write_bytes(b'x')
+    assert any('extra.bin' in d for d in cloud_migrate.verify(out))
+    assert cloud_migrate.main(['verify', '--pack', str(out)]) == 1
+
+
+def test_symlink_in_a_bundled_directory_is_refused(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    outside = tmp_path / 'outside-secret.txt'
+    outside.write_text('fixture')
+    try:
+        (bundle / 'link.txt').symlink_to(outside)
+    except (OSError, NotImplementedError):
+        pytest.skip('cannot create symlinks without privilege here')
+    with pytest.raises(ValueError):
+        cloud_migrate.pack(cfg, bundle, tmp_path / 'pack')
+
+
+def test_pack_refuses_a_used_output_folder_and_leaves_the_source_unchanged(tmp_path):
+    cfg, bundle = build_store(tmp_path)
+    out = tmp_path / 'pack'
+    out.mkdir()
+    (out / 'x').write_text('1')
+    with pytest.raises(ValueError):
+        cloud_migrate.pack(cfg, bundle, out)
+    before = cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db')
+    cloud_migrate.pack(cfg, bundle, tmp_path / 'pack2')
+    assert cloud_migrate.table_stats(cfg['live_state_dir'] / 'events.db') == before
+
+
+# ---- deploy/ files ----------------------------------------------------------------------------------------
+
+def test_iam_policy_has_no_wildcard_resource_and_no_iam_writes():
+    policy = json.loads((DEPLOY / 'iam-instance-policy.json').read_text())
+    for statement in policy['Statement']:
+        resources = statement['Resource'] if isinstance(statement['Resource'], list) else [statement['Resource']]
+        assert all(r != '*' and '*' not in r.replace('/migrate/<PACK_ID>/*', '') for r in resources), statement['Sid']
+        actions = statement['Action'] if isinstance(statement['Action'], list) else [statement['Action']]
+        assert not any(a == '*' or a.endswith(':*') or a.startswith('iam:') for a in actions)
+    # option A: persona runner uses its own key file, so the instance role cannot assume anything
+    assert not any('sts:' in str(s['Action']) for s in policy['Statement'])
+    s3 = next(s for s in policy['Statement'] if s['Action'] == 's3:GetObject')
+    assert s3['Resource'].endswith('/migrate/<PACK_ID>/*')
+
+
+def test_tunnel_example_routes_only_the_ui_and_the_workspace_api():
+    text = (DEPLOY / 'cloudflared-config.example.yml').read_text()
+    services = re.findall(r'^\s*-?\s*service:\s*(\S+)', text, re.M)
+    assert services == ['http://127.0.0.1:8017', 'http://127.0.0.1:3013', 'http_status:404']
+    assert '8013' not in re.sub(r'^\s*#.*$', '', text, flags=re.M)
+
+
+def test_linux_ops_example_uses_the_instance_role_and_the_right_ports():
+    cfg = json.loads((DEPLOY / 'ops.linux.example.json').read_text())
+    assert cfg['schema'] == 'argus_ops_v1' and cfg['providers']['aws']['profile'] is None
+    assert cfg['providers']['cloudflare']['app_ids'] == ['<LAB_ACCESS_APP_ID>']  # the Access app's own id never listed
+    assert cfg['supervisor']['workspace_api_port'] == 8017 and cfg['supervisor']['web_ui_port'] == 3013
+    assert cfg['backend_url'].endswith(':8013')
+    assert cfg['live_state_dir'].startswith('/') and cfg['status_dir'].startswith('/')
+
+
+def test_instance_role_label_marks_it_as_infrastructure(tmp_path):
+    from workspace_next import system_accounts as sa
+    (tmp_path / sa.FILE).write_text((DEPLOY / 'system-accounts.example.json').read_text())
+    labels = sa.declared(tmp_path / 'preview.db')
+    assert sa.is_infrastructure('argus-ops-instance', 'role', 'aws_cloudtrail', labels)
+    assert not sa.is_infrastructure('argus-ueba-actors-persona-01', 'role', 'aws_cloudtrail', labels)
+
+
+def test_trust_statement_adds_one_principal_and_the_service_unit_is_gated():
+    trust = json.loads((DEPLOY / 'persona-trust-statement.json').read_text())
+    assert trust['Action'] == 'sts:AssumeRole' and trust['Principal']['AWS'].endswith(':role/<INSTANCE_ROLE_NAME>')
+    unit = (DEPLOY / 'argus.service').read_text()
+    assert 'ConditionPathExists=/var/lib/argus/CUTOVER_OK' in unit and 'Restart=always' in unit
+    assert 'scripts/argus_supervisor.py' in unit
