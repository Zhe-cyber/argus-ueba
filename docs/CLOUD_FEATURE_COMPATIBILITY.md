# Cloud feature compatibility and training decision

27 October 2026. Code review and offline counterexamples, not detection accuracy.
The 71-feature CERT model, frozen 12-feature extractor/scorer and both existing
checkpoints are unchanged. The projection below is not a registered live source,
an approved training adapter or a new input contract.
Dataset attribution, pinned downloads and sample limitations are recorded in
[PUBLIC_CLOUD_DATA_AUDIT.md](PUBLIC_CLOUD_DATA_AUDIT.md).

## Decision

Do not train the existing 12-feature cloud AE on CLUE-LDS by filling unobserved
AWS/IP/error fields with zero. Keep CERT as the existing research benchmark,
build a separately named CLUE behavioural benchmark, and validate AWS monitoring
on genuinely observed AWS activity. Shared normalisation and verified identity
correlation remain the product foundation; they do not require one identical
model and calibration for observably different sources.

For the competition, retain experimental/Unknown status wherever a source has
no validated model. Do not present an AWS-only checkpoint as validated GitHub,
Cloudflare or multi-cloud person-level detection. Establish source/account
identity mappings before any person-level score or combined behavioural window.

## Current observability matrix

"Conditional" means a count can be computed but its interpretation or required
telemetry needs review; it is not a normal/benign assurance.

| Frozen feature | AWS CloudTrail | Cloudflare Access feed | GitHub Events feed | CLUE-LDS sample |
| --- | --- | --- | --- | --- |
| event_count | API events, including machines | Authentication/access events only | Published activity events, not all account actions | Storage/authentication events |
| unique_actions | API names | Access action names | Display strings can include commit count | Native event types |
| unique_resources | Often bucket, not object key | Protected app domain | Repository | Path on only some events |
| unique_ips | Conditional: literal IPs vs service/redacted strings | Available when supplied | Not provided by this feed | No IP field on named-user sample |
| after_hours_events | Fixed UTC calendar rule | Same UTC rule | Same UTC rule | Same UTC rule; not verified local work hours |
| sensitive_events | Resource-name regex heuristic | Domain-name regex only | Repo-name regex only | Pseudonymised paths can match coincidental keywords |
| error_events | errorCode metadata ignored | Denial suffix is recognised | Failures not exposed by this activity feed | login_attempt is not a verified failure |
| new_action_count | Needs prior-day history | Needs history and coverage | Display-string changes can look like new actions | Needs prior-day history |
| iam_sts_events | Conditional: action/resource regex ignores eventSource | IAM/STS activity unobserved | AWS IAM/STS activity unobserved | AWS IAM/STS activity unobserved |
| data_exfil_events | Read-like calls, not proof of exfiltration | In-app reads/downloads unobserved | Not a complete download/read log | file_accessed not recognised by frozen regex |
| admin_events | Conditional API-name regex | Administrative changes unobserved in this feed | Partial activity; not org security audit | permission_changed not recognised |
| assume_role_events | Selected API names recognised | Role-assumption telemetry unobserved | Role-assumption telemetry unobserved | AWS role-assumption telemetry unobserved |

The current StandardScaler is not a [0,1] feature transform despite the extractor
docstring. The score formula clips normalised reconstruction error to [0,1];
it is not a probability of account compromise. No math/docstring semantics were
silently changed in this review.

## Repeatable observations

scripts/probe_cloud_contract.py uses offline fixtures with no provider calls:

* GetObject success and GetObject with AccessDenied both produce error_events=0.
  Cloudflare denied login produces error_events=1. Equivalent outcome concepts
  therefore have source-dependent feature treatment.
* Two GetObject events on different keys in the same bucket produce
  unique_resources=1 because the normalizer prefers bucketName. A CLUE file path
  would be a different resource granularity; a naive count is not comparable.
* GetCallerIdentity with eventSource=sts.amazonaws.com produces iam_sts_events=0
  because the frozen regex sees only action and resource.
* GitHub Events has no IP field, while its frozen unique_ips value is zero.
  That zero means unavailable telemetry, not evidence of a stable source IP.
* file_accessed projected from CLUE produces data_exfil_events=0. Renaming it
  to an AWS API just to activate a feature would fabricate source semantics.
* An action on the first observed day counts as new; the same action with prior
  history does not. Neither a new identity nor missing earlier logs establishes
  behavioural novelty relative to a genuine established baseline.

On the previously downloaded bounded CLUE prefix, a diagnostic projection of
96,465 named-user events produces 134 user-day vectors. Six frozen columns are
constant zero: unique_ips, error_events, iam_sts_events, data_exfil_events,
admin_events and assume_role_events. Only 42,263 named-user events have a path
in params.path; no named-user sample event has an IP-address field. Resource
keyword matching fires on 52 user-days, but pseudonymised names do not establish
actual resource sensitivity. These are sample diagnostics, not full-dataset
statistics, training vectors or a performance evaluation.

Reproduce without writing raw records or any model input file:

```powershell
python scripts/probe_cloud_contract.py --clue-prefix data/live/public/clue-7119953/clue-prefix.zip.part --out data/live/public/clue-7119953/NEW-feature-review.json
```

## Follow-up contract for a separate CLUE benchmark

Use a new source/model profile (for example clue_behavior_v1) and separate
artifact names; never overwrite cloud_ae_v1.pt or the CERT checkpoint. Reuse the
AE approach, not the assumption that the old 12 inputs describe this source.
An initial reviewable ten-feature profile is:

1. Total events.
2. Distinct native action types.
3. Distinct observed params.path values.
4. Fixed UTC off-hours event count, explicitly labelled a temporal convention.
5. Newly observed native action types relative to strictly earlier days.
6. file_accessed events (accesses, not bytes or proven exfiltration).
7. login_attempt events (attempts, not proven failures).
8. login_successful events.
9. Sharing events from an explicit, documented native event-type allow-list.
10. permission_changed events.

Before implementation, review the full event catalogue/author documentation and
fixture mappings. Unmapped event types remain counted in total/unique actions
and coverage reports; never silently coerce them into a supported category.
Do not use pseudonym sensitivity, fabricated IPs, inferred failure, roles,
scenario labels or chosen compromise times as input features.

Keep outside the model vector: source/profile version, field coverage fractions,
history length, first-observed/cold-start status, partial-day/gap indicators,
native event provenance and dataset split/ground truth. A missing value cannot
silently become an observed zero. Exclude a window or mark its score unavailable
when required coverage is inadequate; document any imputation in a new contract.

Select named identities and population eligibility from the fitting period only.
Use genuine chronological warmup/training, validation, calibration and later
held-out windows. Report source gaps and treat first/last capture days as partial
unless coverage is established. Any author-style account-switch experiment is
an offline simulated hijacking with labels withheld, never a real breach or a
native AWS event. Preserve unswitched normal controls and benign unusual loads.

## AWS/live path remains separate

Continue collecting audited normal AWS role activity across real days. Review
a versioned outcome/resource/action contract before correcting errorCode use,
eventSource classification, object-level resource scope or stable identity
handling. Semantic changes require the repository's replay/evaluation process;
do not rename a new model as though it were the old frozen contract.

Eventually use source-appropriate validated AE profiles/calibration under one
shared investigation interface. A verified person mapping can connect accounts
and timelines, but raw reconstruction errors from different models are not
directly comparable and must not be averaged into a compromise probability.
Any combined person score needs its own documented aggregation, missing-source
handling and held-out false-alert evaluation before activation.

No new model was trained or deployed in this review. The next implementable
slice is the isolated CLUE profile/export and chronological data-readiness
report, while AWS collection continues separately. Automatic retraining is not
part of this plan.
