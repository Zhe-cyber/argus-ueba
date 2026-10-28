# aws_lab_daily_v1: audited daily AWS workload export

Version1,29 October2026. Engineering feature contract, not a trained model or
detector preregistration. Existing CERT71, CLUE10 and legacy cloud12 artifacts,
extractors and thresholds are unchanged and incompatible with this new profile.

## Unit and inputs

One restricted machine-role / Malaysia-local-day row, selected only from audited
ordinary actions in30Oct-5Nov fitting,6-7Nov validation or8-10Nov calibration.
The readiness audit rechecks exact frozen plans and unique native receipts in the
same native DB read transaction used to collect evidence. Default report-only
audit behaviour is unchanged. Setup,28Oct commissioning,29Oct warm-up,11Nov
reconciliation and12-13Nov cases never enter this normal-data exporter.

Only closed local days meeting the existing90% planned coverage and no unresolved
claim gate are exported. Whole incomplete days are excluded, not partially used
as normal samples. Per-role/multi-day gates remain in the readiness report and
must pass separately; a usable row need not yet have sufficient history for a
model. Future or current partial dates are not samples. No synthetic idle rows.

## Ordered numeric vector

All eight values are nonnegative integer counts. No scaling, clipping, score,
label, baseline fitting or threshold is applied by the exporter.

| Feature | Exact meaning |
| --- | --- |
| event_count | Number of selected, verified native events in this role/day |
| get_object_count | Exact GetObject action count |
| head_object_count | Exact HeadObject action count |
| get_bucket_location_count | Exact GetBucketLocation action count |
| unique_resources | Number of distinct mapped toy buckets touched |
| unique_valid_ips | Distinct canonical parsed IPv4/IPv6 addresses; no inferred IPs |
| off_hours_events | Native event outside Mon-Fri08:00inclusive-20:00exclusive MY; all weekend events counted |
| confidential_bucket_reads | Selected operations against the toy confidential bucket |

The last feature denotes the fixture bucket's name, not actual sensitive-data
access. Missing/invalid IPs are excluded from unique_valid_ips and separately
counted in ip_observability. They never imply safe geography or known coverage.
The timestamps must be zoned and consistent with the audited local date. Only
the three exact operations and seven fixed lab buckets are accepted. Raw IPs,
ARNs, provider account IDs, principal/request IDs and bucket names are not exported.

## Account context preserved outside the vector

Each row also carries action_counts, resource_counts and local_hour_counts.
Resources use exact toy aliases p01-p06/confidential. These are raw descriptive
counts; p01 is not proof of ownership or legitimate access. There is no personal
novelty score, peer baseline or online reference update in this export.

Count vectors can be identical after a resource substitution. The categorical
resource counts preserve that distinction for a separately specified personal
baseline. A future model must fit any vocabulary/reference on fitting data only,
freeze it before validation, and define treatment of unseen values in its annex.
No later-day evidence changes an earlier feature vector or its context.

Eight is a feature width, not evidence of detection quality or sufficient sample
size. In this toy workload several counts are correlated and may be constant.
The fitting/validation review must report that limitation. Preserving context
does not establish that a model can detect intent or distinguish matched cases.

## Output and reproducibility

`scripts/export_live_daily.py --pilot-config <private-config> --out <fresh-dir>`
writes three files: dataset.json, feature_contract.json and manifest.json. It uses
read-only ledger/native snapshots, never providers or the application event_store,
and refuses existing output or the active project model directory. A private
staging directory is renamed only after all outputs are complete. Sources are
hashed before/after; drift refuses export. Source DBs are never modified.

Rows contain role labels, local dates, fixed partition labels, features/context,
coverage denominators and an evidence digest. Provenance binds generator profile,
source code, canonical scope/evidence and contract hashes. Manifest dataset and
feature-contract SHA256 values match the exact saved bytes. No raw receipt IDs or
metadata are published. Exclusions/future/incomplete states remain in readiness.

Status is empty_dataset if no rows qualify, partial_dataset while normal windows
are still open, otherwise normal_windows_complete. The latter means dates have
closed; it does not mean complete coverage or a qualified model. Manifest exposes
history_gates_pass separately and always reports trained=false,activated=false.
An early empty real export is a pipeline check, never a training dataset or a
reason to reuse setup/warm-up. Synthetic test exports are not pilot evidence.

Any change to vector order, definitions, source semantics or history use requires
a new profile/version and new compatible artifacts. The full method annex,
model/scorer, fitting hyperparameters, calibration rule and release decision
remain separate, due before validation under protocolV2. This change does not
train or activate a model, edit the analyst dashboard or alter the running pilot.
