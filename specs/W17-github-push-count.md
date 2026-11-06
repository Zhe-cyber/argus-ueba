# W17: Preserve unknown GitHub push counts

## Goal
Stop presenting an absent or invalid GitHub PushEvent payload.size as zero commits.

## Scope and rules
- backend/normalizer.py and focused normalization tests.
- A nonnegative integer, excluding bool, is a known count; retain the count label and metadata.commits.
- Missing, null or invalid counts produce Code push and metadata.commit_count_status=unknown, without metadata.commits.
- Known PushEvent counts carry commit_count_status=known. Never infer totals from a possibly incomplete commits array.
- Preserve raw payloads, native IDs and deduplication behavior. No stored-event migration, model changes or credentials changes.
- Pause the owned local collector/backend before changing pinned runtime files; back up config, permit only this file's hash to change, validate and restart with health verification.
- User commits and pushes manually.

## Acceptance
- Missing/null/boolean/negative/string/float counts remain unknown; explicit zero, one and positive integers remain known.
- Raw payload is preserved. Other event types remain unaffected.
- SQLite backend tests pass; pilot runtime source validation and health pass after release.
