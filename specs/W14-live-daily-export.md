# W14: daily-ledger exporter and separate AWS lab feature contract

Written29 October2026 before implementation. User explicitly requests implementing
the exporter now. Preserve all running source-pinned services, models and dates.

Refactor readiness audit only to optionally return its selected native evidence
from the same database transaction, retaining its default report-only API.
No second unverified receipt selection. Return evidence only for usable closed
ordinary days in the three fixed normal partitions, excluding warm-up and cases.

Create `aws_lab_daily_v1`, a NEW8-count feature profile:
event_count,get_object_count,head_object_count,get_bucket_location_count,
unique_resources,unique_valid_ips,off_hours_events,confidential_bucket_reads.
MY timezone, weekday08:00inclusive-20:00exclusive normal hours; weekend off-hours.
Allowed operations are exact lab SDK operations; resources are exact seven toy
buckets. Confidential denotes only the toy bucket label, not actual sensitive data.
Strict zoned timestamps, one role/day per row, no imputation or zero-event days.
Valid IPs counted by canonical parsed address; missing/invalid counts exposed
outside vector, never converted to benign evidence. This profile cannot load
CERT/CLUE/legacy12 model weights or reuse their thresholds.

Preserve actual action/resource/hour count dictionaries beside each vector so a
future account-conditioned method can use categorical identity context. These
are descriptive raw counts, not novelty scores or labels. No fitting-derived
feature or dynamic history: later days cannot change earlier rows. Models must
fit vocabulary/references on fitting only. Actual resource aliases p01-p06 and
confidential reveal toy scope, not ownership. Raw native evidence stays private;
export only per-row evidence hashes, source/code/contract/profile bindings,
role/day/partition, coverage and explicit exclusions/readiness. No raw account,
ARN, request/principal IDs, IPs or resources in exported file.

Export closed usable rows as partial_dataset or normal_windows_complete; readiness
gates retained separately, never claim training-ready/model-qualified. No observed
rows today => empty_dataset (with coverage), not fabricated samples. Fresh output
directory only, no overwrite or active models path; exclusive staging directory
then rename, finite JSON, source hashes checked before/after. CLI config from
existing pilot, read-only SQL, no providers or model libraries required.

Tests: same-snapshot receipt evidence parity, invalid evidence exclusion, exact
count/hour/IP/domain boundaries, future-partition independence, private identifiers
absent, existing provenance/history gates retained, no overwrites, empty early
export and unchanged DBs. Full SQLite suite and existing service pins/health.
Human-only merge; new feature contract is frozen by this commit but detector/
threshold/annex are not. No real neural fitting or risk activation in this slice.
