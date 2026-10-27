# Isolated CLUE feature export

This implements the separately versioned clue_behavior_v1 profile from
CLOUD_FEATURE_COMPATIBILITY.md. It does not register a live provider, change
the frozen 71/12-feature contracts, train a model or activate scoring. The
existing AWS training notebook cannot accept this ten-feature dataset.

Source/attribution: Landauer, Skopik, Hoeld and Wurzenberger (AIT), CLUE-LDS
(2022), [DOI 10.5281/zenodo.7119953](https://zenodo.org/records/7119953), CC BY 4.0.
Event catalogue reviewed in Table III of the authors'
[paper](https://www.skopik.at/ait/2022_bigdata.pdf) and their repository at
revision 837bfcaf83c3bf36dec9756f19c20e76acf245e6. No upstream code is executed
or copied. Public dataset terms and upstream GPL code licensing are distinct.

## Profile

The ten inputs, in order, are event_count, unique_actions, unique_paths,
utc_off_hours_events, new_action_count, file_access_events,
login_attempt_events, login_success_events, sharing_events and
permission_change_events. They use exact native action names and params.path.
No inferred failures, IPs, resource sensitivity, roles, scenario labels or
AWS API categories are added. An attempted login is not assumed to have failed.

Sharing counts exactly shared/unshared email/group/link/user events. Public
share access and permission updates are not conflated with those eight actions.
Known-action coverage uses the paper's 49 types plus the observed native
logout_occured spelling. That spelling is tracked without rewriting the event.
Unknown types still contribute total/action diversity/novelty and are reported
outside the model; readiness blocks until their mapping is reviewed.

Required params.path coverage is checked for types documented as requiring it;
optional paths on file_created/file_written are not fabricated. The path feature
is specifically params.path diversity, not a claim to include oldpath/newpath,
fileTarget, or every possible file reference. Path values are hashed for set
counting and never emitted. User identifiers are pseudonymised consistently;
feature exports still require care and are not guaranteed anonymous.

Temporal convention is fixed weekday 07:00-19:00 UTC, explicitly not a claim
about actual working hours. Novelty compares distinct native action types with
strictly earlier observed UTC dates. Same-day arrival order cannot contaminate
history. Capture-start history is left-censored; warmup is explicit.

## Bounded streaming and provenance

scripts/export_clue_dataset.py reads only the first clue.json DEFLATE member
without extracting archive paths. Bounds are 32 MiB compressed prefix, 1 GiB
expanded data, two million native events, 10,000 identities, 200,000 identity-day
states and 256 KiB per JSON line. It stops at a whole record when a stream bound
is reached and excludes the capture's first/last dates from readiness. Native
IDs must be strictly increasing; duplicate IDs and invalid schemas fail closed.

The larger source contains small same-day timestamp reversals. They are counted
and preserved, never shifted. Grouping uses actual UTC dates; cross-day reversals
block readiness pending review. Prefix truncation does not establish full-day
source completeness, and a no-record date may be inactivity or a coverage gap.
The output explicitly records that uncertainty, original bounds and timestamps.

Prefix hashes, byte/event counts, source DOI/URL, attribution, code hashes and
coverage counters accompany the feature JSON. A partial prefix cannot establish
the full archive's published MD5 or ZIP CRC. Obtain it only from the official
HTTPS source with checked HTTP range responses; do not call it full-archive
integrity verification. Failed downloads remain separate. Exports and raw
prefixes live under gitignored data/live and never enter the live database.

```powershell
python scripts/export_clue_dataset.py --prefix data/live/public/clue-7119953/YOUR-VERIFIED-PREFIX.zip.part --out data/live/training/clue-v1/NEW-dataset.json --cutoffs WARMUP_END FIT_END VALIDATION_END CALIBRATION_END EVALUATION_END
```

Use real YYYY-MM-DD UTC cutoffs, strictly increasing. The exporter never
overwrites an existing dataset or readiness report. IP-based/anonymous identities
are excluded rather than linked to named users. Labels/coverage/history metadata
remain outside the nested ten-feature vector.

## Population and readiness

Select identities from warmup and fitting only: at least one warmup observation
and five active fitting days. Freeze that population before inspecting later
outcomes. Later-only users are reported outside the selected cohort, not silently
used to improve the benchmark. Report normal cold-start users separately in a
future evaluator. Boundary rows never enter any readiness partition.

Operational minimums: six fitting-eligible identities, 30 fitting rows and six
rows/users in each other partition. Missing required paths, unknown action types
and cross-day timestamp reversals block readiness. These minimums are not
statistical sufficiency, independently verified benign labels, proof of source
completeness or performance validation. Low activity on later dates may make a
cohort fail; do not select users using their evaluation activity to conceal it.

Only active identity-days are emitted; missing/idle days are not fabricated as
zero vectors. A cohort member without later observations remains in the frozen
population but contributes no scored window. Evaluation must report that absence,
not count it as a correctly classified normal day.

## Observed export on 27 October 2026

The official range download reached its time cap after 27 MiB of individually
verified contiguous ranges (32 MiB was the requested maximum). The resulting
prefix was closed before inspection; it is not represented as a full archive.
It contains 1,689,097 complete records and produces 1,640 active identity-days
across 100 named pseudonyms on 35 UTC dates, 7 July-10 August 2017.
Twenty-three events lie behind the previously seen timestamp by at most two
seconds, all within the same UTC day. These timestamps were preserved. No
unknown actions, missing required paths or cross-day reversals were found in
this bounded subset. This is not a full-corpus assurance.

The following split fixes 55 eligible identities using warmup/fitting only:

| Partition | Real UTC dates | Rows | Observed selected identities |
| --- | --- | ---: | ---: |
| Warmup | 8-12 July 2017 | 194 | 55 |
| Fit | 13-26 July 2017 | 605 | 55 |
| Validation | 27-31 July 2017 | 188 | 49 |
| Normal calibration | 1-4 August 2017 | 169 | 49 |
| Held-out normal evaluation | 5-9 August 2017 | 191 | 49 |

Eighty-six first/last capture-date rows and 207 interior rows from identities
outside the fitting-selected population are excluded from these partitions.
The operational readiness report passes. It does not establish detection
accuracy, independently verified normality or statistical sufficiency, and
does not select a model/threshold using the evaluation rows. No account-switch
scenario, real-cloud anomaly detection or model training has run.

The private feature artifact is data/live/training/clue-v1/colab-features.json;
its companion readiness report binds the exact dataset SHA256. Never upload raw
archive prefixes or credentials to Colab. A separate CLUE training notebook is
the next implementation slice.

Next: a separately named CLUE AE/scaler and Colab workflow consuming this exact
profile, with train-only scaling, independent normal calibration and a genuinely
held-out normal evaluation. A later account-switch experiment is an offline
simulation; its labels must stay outside the model and must never be passed off
as a native cloud breach. Neither artifact is suitable for installation as the
existing AWS cloud_ae_v1 checkpoint.
