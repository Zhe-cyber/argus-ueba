# Cloudflare tick status correction — 4 November 2026

Implemented and installed in the existing pilot. Source pin updated under the machine-pilot lock after confirming all other source pins and the prior config hash were unchanged. Backups and release hashes: `data/live/cf-status-fix-20261104/`.

A healthy tick reports `completed` even when older `claimed_unknown` rows exist. `action_states` remains the complete all-time ledger tally; `historical_unknown` and `new_unknown` distinguish pre-existing uncertainty from newly unresolved claims. Exceptions retain the existing stopped/nonzero behavior. Nothing retries or relabels an uncertain request. Collection failure remains a failure.

All five historical unknown rows remain unchanged. No ledger edits or provider calls were made for installation. No schedule, budget, resource, credential, AWS study source or model changed. The next ordinary scheduled tick will consume the updated pin; its completion has not yet been observed at installation.

Verification: 18 Cloudflare/GitHub pilot tests passed, including preserved timeout claims, no retries, a later successful request with an older unknown, source/scope validation and expired-pilot guards. The first sandbox attempt failed to create pytest temporary directories; rerunning with a workspace temporary directory passed.

GitHub was reviewed and intentionally left unchanged: unresolved claims and identity-pending writes actively prevent subsequent writes, so its attention status reports an operational block. Clearing that status would conceal the block. Cloudflare does not have that cross-request write dependency.

The dashboard preview is running at http://127.0.0.1:3011/workspace (isolated data copy). Historical gaps remain visible and must not be reported as verified or as negatives.
