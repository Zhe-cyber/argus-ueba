# GitHub observed daily history

`scripts/export_github_history.py` reads the existing connected SQLite store without importing backend configuration or making provider requests. Its `github_projection_daily_v2` contract describes stored projections, not complete native audit logs. See `specs/W18-provider-history-features.md` for the provider plan and evidence-retention correction.

Version 2 excludes the PR review label from the pull-request count; it remains unclassified. The first private v1 dataset/manifest remain unchanged, with their exact producing script preserved beside them. A one-repository feed makes unique_repositories effectively constant; it is descriptive context, not a justified scoring feature. Exporter hashes bind exact source bytes, including line endings. Each export records its own code hash; a changed checkout does not rewrite or invalidate the old data, but is a different producing artifact. Preserve exact producing bytes for reproduction.

Run with the existing Python environment:

```powershell
python scripts/export_github_history.py --database <events.db> --alias-key-file <private-32-byte-key-file> --output <fresh-private-directory>
```

The caller must create and privately retain a random key of at least 32 bytes. Reuse it for stable aliases across exports; do not put it in Git or share it with exported datasets. Account and repository aliases are HMAC-SHA256, scoped by provider account. Actor-ID and login-fallback identities remain separate. Pseudonymisation does not prevent all inference from timestamps/activity patterns; inspect exports before public sharing.

Outputs are `dataset.json` and `manifest.json`. A valid completed export requires both files and a matching dataset hash from the manifest. Never reuse an output directory; a failed write may leave an incomplete folder. Manifests bind the exporter code, contract and accepted projection snapshot. They do not verify unavailable raw payloads.

Daily rows use closed Asia/Kuala_Lumpur dates with observed events. Today's events are counted separately, not scored or silently assigned to yesterday. Missing days are absent. Labels determine explicit action-category counts; unclassified actions and missing repositories remain visible. Known commit sums include only valid nonnegative integer metadata values. Missing commit evidence is not zero commits, even if an older display label says zero.

The exporter provides no baseline, attack detection, review-priority tiers, peer comparison, account linking or coverage guarantee. Successful collection and a closed calendar date do not prove completeness. An empty export is insufficient observation, not evidence of normal activity. Bot suffixes are unverified hints. IP, country and sign-in evidence are unavailable from this source.

Read access is SQLite mode=ro with query_only and a consistent transaction. A live collector may independently append records while export runs, so an entire live DB file hash is not a valid before/after invariant; the exporter hashes its selected snapshot instead. Tests verify unchanged source bytes on an isolated database with no concurrent writer. The 100,000-record bound fails explicitly rather than producing a silently truncated dataset.
