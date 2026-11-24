# R3 cloud deploy: security re-review (Claude, standing in for Codex)

Base HEAD `1a82311`, fixes uncommitted in the working tree (`git diff HEAD`). Static review only. No deploys, no provider
calls, no edits beyond this file. Accepted residual risks (one shared OS user; unsigned manifest) are not raised again.

## Original findings

1. **Migration verification can bless altered or incomplete evidence: FIXED.**
   `scripts/cloud_migrate.py:35` hard-codes the required inventory (`events.db`, `preview.db`, `ticks`, `bundle`) in the
   checkout, not in the transferred manifest. `:183-185` rejects a manifest that is missing any of them or has an empty bundle.
   `:117` gives every packed file, databases included, a sha256 digest, so an edited cell with unchanged ids and counts fails
   (test `test_edited_cell_with_unchanged_ids_and_counts...`). `:189-191` rejects unlisted extra files. In installed mode,
   `:193-196` takes the inventory from the trusted `ops.json` and flags entries that are configured here but absent from the
   manifest. The byte digest also covers installed copies, because the runbook installs by plain copy.
2. **The cutover gate cannot fence the old SQS consumer: FIXED.**
   `deploy/README.md:103-106` (step 14) removes the laptop identity's queue access at AWS before `CUTOVER_OK` and proves it
   with one denied receive. `:107-109` says the marker is local only. `:126-128` gives the reverse order for rollback. The
   laptop identity is distinct from the server identities (`argus-collector` in `scripts/local_pilot.py:190,310`, versus the
   instance role and the `argus-simulator` runner), so fencing it does not disable the server. Note: the marker still sits
   under the argus-owned `/var/lib/argus` (`README.md:45`), so it is not root-controlled. That no longer matters for the
   cross-host scenario this finding described.
3. **Web processes get collector and runner credentials: FIXED (within the accepted shared-UID residual).**
   `scripts/argus_supervisor.py:32-33,97-98,107-108,118-119,146`: AWS, GitHub and Cloudflare variables are scrubbed from
   ingest-api, mirror, workspace-api, notifier, web-ui and the drift child. Only the collector and personas keep them. The
   residual risk is disclosed at `README.md:157-160`. The test `test_only_collector_and_personas_children_get_provider_credentials`
   covers this.
4. **Pack paths can leave the source or verification folder: FIXED.**
   `cloud_migrate.py:75-85` rejects symlinks and junctions, and any entry that resolves outside its root, while walking for
   pack, verify and the unlisted-file scan. `:92-94` rejects manifest names that resolve outside the pack. `:108-109,163`
   rejects symlinked single-file entries. Minor gap: a FIFO or device node is skipped silently rather than rejected (`:83`).
   It cannot be packed or hashed, so this is not exploitable here.
5. **Instance role keeps migration and persona permissions: FIXED.**
   `deploy/iam-instance-policy.json` has no `sts:AssumeRole`. S3 read is limited to `migrate/<PACK_ID>/*` (`:19`).
   `README.md:110` (step 16) removes the statement and deletes the pack after cutover. The grant is scoped and temporary,
   although it sits on the instance role and not on a separate role.
6. **Tunnel can publish the app before Access is enforced: PARTIALLY FIXED.**
   The ordering is fixed: `README.md:77-80` creates Access and its policy first, then the tunnel and DNS route, then checks an
   unauthenticated request. The second requirement is not met. `deploy/cloudflared-config.example.yml:7-12` has no
   `originRequest.access` block (`required: true`, `teamName`, `audTag`) on either ingress rule. Failure scenario: someone
   later deletes the Access application, narrows its hostname, or changes it to a mismatched path. The connector then serves
   `/api/*` (the workspace login and health) and the UI to the public internet with no origin-side check. The one-time check
   in step 8(c) would not catch this. Fix: add `originRequest: {access: {required: true, teamName: <TEAM>, audTag: [<AUD>]}}`
   to both `argus.<domain>` rules and a test asserting it.

## New defects introduced by the fix diff

None found with confidence.

## Tests

`pytest scripts/tests/test_cloud_deploy.py scripts/tests/test_argus_supervisor.py -q` (DATABASE_URL=sqlite-local, Windows):
**26 passed, 4 skipped.** The skipped tests are Linux-only.

## Verdict

Findings 1-5 are closed. Finding 6 is still missing the connector-side Access JWT validation that the original finding
asked for. It is a small config change.

REQUEST_CHANGES

## Follow-up re-check (2026-11-22): finding 6

**Finding 6: now FIXED.**
- `deploy/cloudflared-config.example.yml:14-18,21-25`: both `argus.<domain>` rules (`/api` to 8017, and the UI on 3013)
  now carry `originRequest.access` with `required: true`, `teamName` and `audTag` as a list. The key names and shape match
  cloudflared's origin-side Access JWT validation. The placeholder flow list `[<ACCESS_AUD_TAG>]` is valid YAML. No routed
  hostname is left without the check. The catch-all rule only returns `http_status:404`, and 8013 is still not routed.
- `deploy/README.md:77-82` (step 8): the owner creates the Access app and its policy, copies the AUD tag and team name into
  both blocks, and only then creates the tunnel and DNS route. The unauthenticated-request check stays. If the Access app
  is later deleted or its hostname changes, cloudflared now rejects the request instead of serving the app.
- `scripts/tests/test_cloud_deploy.py` `test_tunnel_example_routes_only_the_ui_and_the_workspace_api` asserts the access
  block on exactly the two hostname routes.
- The other change, README step 4 also copying `workspace_next/frontend/lib`, is a build-only fix with no security impact.
  The diff stats for `cloud_migrate.py`, `argus_supervisor.py` and the IAM policy are unchanged since the first re-check.

Tests: 26 passed, 4 skipped (Linux-only), Windows, DATABASE_URL=sqlite-local.

All six original findings are now closed. No confident new defects.

APPROVE
