# Shared-core v1: exact projection and scenario rules

30 October 2026. Fixed definitions for the first isolated training preregistration.
This document does not release the reserved evaluator or activate live scores.
Implementation: shared_core_features.py, shared_core_scenarios.py and
shared_core_reader.py. No previous contracts are modified.

## CLUE resource contract

Every event supplies zero or one primary target namespace. Paths remain literal;
take the first nonempty slash-separated component, then hash source, dataset
scope, namespace kind and that component. Never inject uid into a resource key.
The target is not claimed to be a verified container, bucket or owner.

| Native action family | Primary target field |
|---|---|
| file_copied, file_renamed | params.newpath (destination) |
| restored_from_trashbin | params.filePath (destination) |
| shared/unshared email, group, link, user | params.fileTarget |
| file_accessed, created, deleted, updated, written | params.path |
| permission_changed; version_deleted/restored; deleted_from_trashbin | params.path |
| comment_added/deleted; public_share_accessed/update_permission | params.path |
| public_share_expiration_date_changed/password_changed | params.path, if unavailable the day is incompatible |
| Remaining recognised account/session/admin actions | optional params.path when supplied; otherwise resource-free |

For every path-required event, an absent/empty/unusable field invalidates the
whole account-day. Do not substitute run, itemSource, user, uidOwner or numeric
file identifiers for a path namespace. Fitting inspection found run-only created
and written events; this is a declared observability exclusion, not zero activity.
Copy/rename counts destination only, not two resources; restore ignores trashPath.
Recognised action vocabulary is the exact KNOWN_ACTIONS dependency in the frozen
clue_features.py, including the observed logout_occured spelling. Unknown actions
invalidate the day. All event/action types keep their native meanings.

Fitting-only shape audit: 834,907 events, 664,034 with params.path. Additional
path fields are visible in copy/rename/restore/share events. 6,827 created and
6,827 written fitting events have no usable params.path. Resource failure counts
also include the path-less public-share configuration events. None were hidden
or filled with invented resources.

## Live projection contract

Require native source namespace, source-scoped account_key, event_id and payload
digest. Preserve missing IP; IP is not an input to these five features.

- GitHub: fixed inverse of the current normalizer display map. Exact labels
  match first, including PR review; then Code push (N commit[s]), PR action and
  Issue action formats. Unrecognised labels invalidate the day, rather than
  disappearing from its event count. Resources require a repository owner/name.
- Cloudflare: retain native login/logout/allow/deny kind, removing the parser's
  denied suffix as an access outcome. Bare access is ambiguous with the parser's
  missing-action default and invalidates the day. Require application domain.
  The missing allowed boolean does NOT block native login-kind features: the
  five-feature core does not use success/failure. Never infer authentication
  success or recover access decisions from an unsuffixed label.
- AWS: action is eventSource:eventName. Initial reliable resource projection
  supports S3 GetObject, HeadObject, GetBucketLocation, ListObjects, ListObjectsV2
  and ListBucket using the adapter's bucket-level identifier. ListBuckets,
  STS GetCallerIdentity and sign-in ConsoleLogin are resource-free. Other
  service/resource semantics invalidate the account-day. Never hash a stringified
  request-parameter dictionary as if it were a stable target identifier.

AWS support is deliberately limited; this is NOT all-service AWS compatibility.
The live audit must report this gap. Expanding this rule later requires a new
contract/candidate, not silently changing the trained feature interpretation.
Provider projections converge on one Event representation, Day feature reducer
and History policy. This does not establish equal real-world distributions.

## History and boundaries

Only prior observed active days count towards k=5, including observed warm-up
activity on the capture-start date. No capture-start day is scored; warm-up is
7–12 July. A resource-incompatible day can still contribute observed known
actions/history, but never a model vector. Unknown/default-ambiguous action kinds
are not learned as native kinds. No unobserved idle days are fabricated.
All variants use the same start-of-day state. Commit the original day's actions
once after its variants; never commit injections. Same-day/reversed commits fail.
Timing is time-of-day only, including weekends: daily 07:00–19:00 UTC for CLUE;
daily 08:00–20:00 Asia/Kuala_Lumpur for live. Start inclusive, end exclusive.

## Exact scenario selection and bounds

Use every eligible target-day in the fixed test window, subject only to the
declared scenario preconditions and safety cap. No score-based day selection.
Hash is SHA256 of canonical JSON (sorted keys, compact separators, ASCII escaped).
Rank input: [42, family, account_pseudonym, UTC_day, str(native_event_id)].
Switch pairing sorts all 55 fitting-selected pseudonyms by rank with family
account_switch, empty day/reference, tie by pseudonym; pair adjacent entries.
First is target, second donor. One account is unpaired; no reused pair members.
Donor must have a scorable same-date original day; no replacement donor search.

Mass access appends four unchanged copies per file_accessed (five times reads).
Off-hours sorts by UTC instant then str(native ID), and remaps event i of n into
midnight + floor(i*(6h in microseconds - 1)/n) microseconds. Already all-night days
are excluded by the declared precondition. Permission novelty appends five events
from the lowest-hash valid resource-bearing template, sets type permission_changed
and params.path to that primary path, preserving time. It requires that kind to
be absent from target prior history. Switch replaces the whole target day with
donor events, changes uid only (plus synthetic provenance), retaining target history.

Synthetic IDs are sim:SHA256([42,family,account,day,original_id,ordinal]); only an
explicit synthetic projector accepts them. Native ZIP intake rejects synthetic IDs.
Maximum 1,000,000 events per original or modified account-day. Exceeding it makes
the case ineligible, never clipped. No-file, no-template, known-permission,
already-night, inactive/unscorable donor and cap exclusions are reported.
Feature-identical switch cases remain positive cases and are reported as zero
feature change; do not discard them to improve detection metrics.

## Training and release boundary

One CPU AE 5-16-8-3-8-16-5, LeakyReLU slope 0.1 hidden, linear output; MSE over
all five transformed/standardised inputs. Counts log1p, fraction unchanged;
StandardScaler fitted only on 13–26 July. Adam 0.001, batch 64, seed 42, max 100
epochs, validation-loss patience 10 (27–31 July), restore best checkpoint. Both
AE and maximum-positive-deviation comparator consume the same float32 scaled
inputs. Scaler is plain JSON, weights load weights_only=True; require exact saved
score parity. Calibration 1–4 August only; minimum 100 eligible days; quantile
method higher at nominal 1% and 5%, strict greater-than alert, report ties/rates.

The training preregistration binds data, source and protocol hashes before fitting.
It does not authorise reserved access. A separate immutable evaluator release
must bind the final model, scaler, thresholds and evaluator before 11–24 August
can be opened. No post-result architecture, threshold or injection tuning.
