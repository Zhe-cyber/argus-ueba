# R3 cloud deployment security review

Base: `l15-eval-report`. Reviewed HEAD `1a82311bdf4d4081506597f0e2a55147e0885f6f`, including the deployment specification and runbook. Scope was static local review. No provider calls or commits were made.

## High

1. **Migration verification can bless altered or incomplete evidence.** `scripts/cloud_migrate.py:94–98,159–176`. SQLite verification compares table row counts and maximum IDs. Changing an existing finding or analyst decision without changing its ID passes that check. The verifier also derives the required inventory from the transferred manifest, so removing a required store and its manifest entries can pass verification. Require the expected inventory from trusted configuration, and verify exact content digests for completed SQLite backups and other artifacts against a manifest authenticated independently of the transfer. If installation intentionally rewrites a store, verify its canonical record digest.

2. **The cutover gate cannot fence the old SQS consumer.** `deploy/argus.service:9`, `deploy/README.md:83–85,99–100`, `scripts/ops_collect.py:298–310`. The local marker sits in a directory writable by the service account and survives restarts. If the laptop collector comes back while EC2 has the marker, each host can receive and delete different messages into its own database. The Linux lock only coordinates calls sharing its local lock path. Put the approval marker under root control and enforce exclusive queue ownership by disabling the old consumer's queue access before granting the new one, with the reverse order for rollback.

## Medium

3. **The deployment gives web processes access to collector and runner credentials.** `deploy/argus.service:12–21`, `scripts/argus_supervisor.py:93–120`. The unit loads the GitHub environment file and the supervisor forwards its environment to the web UI and workspace API. The same UID can read the option A long-lived AWS key file even at mode 0600. A compromised web process could reuse either credential within its provider permissions. Isolate the web processes and collectors under different UIDs, inject secrets only into the process that uses them, and replace the persistent runner key with a short-lived identity when supported.

4. **Pack paths can cross the intended source or verification directory.** `scripts/cloud_migrate.py:73–77,85–91,137–147`. Manifest filenames are joined directly to the pack root and the pack walker follows file symlinks. An accidentally symlinked file under a bundled directory can copy a readable local secret into a bundle destined for upload. Verification can also hash files outside the incoming directory. Require canonical relative names within an expected layout and reject symlinks and nonregular entries during pack and verification.

5. **The instance role keeps migration and persona permissions beyond the runtime requirement.** `deploy/iam-instance-policy.json:13–27`, `deploy/README.md:120–125,136–137`. The collector's instance role can read every object under the migration prefix and directly assume the six lab roles even though option A uses a separate runner for those roles. If the instance is compromised while these grants are attached, its credentials can retrieve any retained migration pack and assume the lab roles. Use a separate temporary grant for the exact migration objects and leave persona-role assumption out of the instance role under option A.

6. **The tunnel can publish the application before Access is enforced.** `deploy/cloudflared-config.example.yml:7–12`, `deploy/README.md:76–79`. The runbook routes the public hostname before creating the Access policy, and the connector has no Access token validation of its own. During setup or after an Access hostname mismatch, public requests can reach the workspace login and health routes, despite the EC2 security group allowing no inbound ports. Provision Access before routing the hostname and configure connector-side Access JWT validation on both routes using the expected application audience.

**REQUEST_CHANGES**

