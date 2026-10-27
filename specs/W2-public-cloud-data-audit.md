# W2: Public cloud dataset suitability audit

27 October 2026. Stacked on PR #12. Inspect the ArielCyber/cloud_log_sampling
release at an immutable revision before admitting it to cloud AE training.

Download only bounded ZIP/README files from pinned official public URLs into
gitignored data/live/public. Do not execute upstream code or extract arbitrary
archive paths. Verify hashes, JSON shape, native IDs, timestamps, identity
coverage, labels, duplicates/conflicts, cross-file overlaps and UTC identity-day
coverage through the unchanged shared normalizer/extractor. Distinguish AWS
machine principals from application/human users. Never forward public events
to live ingestion or use labels/scenario metadata as model inputs.

Produce a reproducible offline audit script, isolated malformed/overlap tests,
and a tracked suitability report with aggregate evidence only. Inspect licensing
and chronological split feasibility. If terms or data quality do not support
training, fail readiness and explain the exact limitation; do not relax training
gates or manufacture identities/days. Preserve CERT/live models and cloud state.
Run isolated tests with DATABASE_URL=sqlite-local, open draft PR, human merge only.

Fallback scope after inspecting Ariel: read CLUE-LDS's official licence metadata
and at most a 4 MiB ZIP prefix/100,000 JSON events. Add a bounded prefix-audit
helper and tests. Report the sample's limitations; no full download, training
export, new source normalizer or frozen feature changes in this task.
