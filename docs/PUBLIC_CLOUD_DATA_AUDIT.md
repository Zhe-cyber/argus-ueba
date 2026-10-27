# Public cloud data suitability audit

27 October 2026. Offline inspection only. No model was fitted or activated and
no public record was forwarded to the connected event store. All downloads and
detailed local reports remain under gitignored data/live/public. Only inspection
code, tests and aggregate findings are committed.

## Ariel Cloud Log Sampling

Source: [ArielCyber/cloud_log_sampling](https://github.com/ArielCyber/cloud_log_sampling/tree/18d3f248f4def592f4e86152c3fcb54506fbcbf6),
revision 18d3f248f4def592f4e86152c3fcb54506fbcbf6. Approximately 9 MB of
archives downloaded from pinned raw.githubusercontent.com URLs. Upstream scripts
were not executed. scripts/audit_public_cloud.py pins all three archive SHA256s,
reads bounded JSON members without extraction, and uses the unchanged shared
AWS normalizer and 12-feature extractor. Observed raw counts match the publisher.

| Archive | Raw events | Duplicate native IDs | UTC dates | Usable identity-days from benign actions |
| --- | ---: | ---: | --- | ---: |
| base_a.zip | 16,495 | 9 | 18-20 February 2026 | 335 |
| train_labeled_a.zip | 4,216 | 0 | 27-28 April 2026 | 58 |
| labeled_cloudtrail_a.zip | 24,087 | 8 | 17-18 February and 4 April 2026 | 89 |

The base archive has 16,486 unique native events. 14,927 have sufficient account,
user and action fields for current normalisation, across 317 account-scoped
normalised identities. Of these, 307 appear on one date, two on two dates and
eight on three dates. Assumed-role events span ten role issuer ARNs; principal
sessions and application/infrastructure identities must not be counted as
independent human users. Application personas do not automatically yield distinct
IAM principals visible to CloudTrail.

Duplicate IDs are identical payloads in this release; no within-file conflicts
were found. Across files, no shared native IDs or account-scoped normalised
identity-days were found. This does not establish a chronological benchmark:
the supplied test does not follow the base in time, and the mixed training file
comes after the test. Do not silently pool/re-split the published test into fitting.

The mixed training/test archives each contain three identity-days that include
both benign and attack actions. Benign-only diagnostic vectors omit attacks;
they are not valid full-window evaluation inputs. A future evaluator must label
and score complete windows, not remove attack events and call that the same day.
Labels should_sample and attack_name are stripped before normalization and never
become detector inputs.

The error_events feature is constant zero in benign diagnostic vectors, while
the raw archives contain 255, 171 and 137 records with errorCode respectively.
The current frozen extractor examines action text rather than errorCode metadata.
Zero therefore does not establish absence of provider errors. Fixing that meaning
requires a versioned feature-contract review and evaluation, not a silent edit
in a dataset adapter. Thousands of addresses also fail literal IP parsing; do
not use anonymized/redacted address strings for real geolocation conclusions.

The pinned tree has no licence file, the README has no explicit reuse grant,
and GitHub's licence endpoint returned 404. Public visibility is not evidence
of an explicit training/redistribution permission. Permission remains unresolved;
no request was sent to the authors.

Verdict: **not admitted to training**. The benign-only source spans just three
UTC dates with very limited per-principal history, does not document closed-day
capture coverage and lacks explicit reuse terms. Five training dates plus later
validation/calibration cannot be created from this base without changing actual
timestamps or our operational gates. It may be useful for supplementary parser
and scenario tests once terms are clarified. More raw events would not solve
the short history or application-to-IAM identity mismatch.

Reproduce after downloading the pinned official files locally:

```powershell
python scripts/audit_public_cloud.py --directory data/live/public/ariel-18d3f248 --out data/live/public/ariel-18d3f248/NEW-audit.json
```

## CLUE-LDS preliminary fallback inspection

Source and attribution: Max Landauer, Florian Skopik, Georg Hoeld and Markus
Wurzenberger, AIT Austrian Institute of Technology, *Cloud-based User Entity
Behavior Analytics Log Data Set*, DOI [10.5281/zenodo.7119953](https://zenodo.org/records/7119953).
The [official record metadata](https://zenodo.org/api/records/7119953) declares
open access and CC BY 4.0. The full ZIP is 635,105,552 bytes with published MD5
9e318370f96b68077667e9cdc05f26a5. The publisher describes normal real-user hBOX/
Nextcloud activity across five years; that description is not an independent
verification that every event is benign.

Only the first 4 MiB was downloaded using a verified HTTP 206 range response.
scripts/audit_clue_prefix.py inspected at most 64 MiB expanded data and 100,000
complete JSON lines without extraction. Full-archive integrity cannot be verified
from a prefix; its SHA256 is recorded in the private report instead.

The inspected prefix covers 7 July 2017 08:57:57 UTC to 10 July 2017 11:08:16 UTC.
It contains 100,000 unique sample event IDs, 50 named pseudonyms and 134 named
identity-days. 96,465 sample events use named identities, while 3,535 use
IP-address identity types; anonymous/IP identities are not counted as people.
Observed event types include logins, file access/update/create/delete, sharing
and permission changes. These are partial-prefix observations, not full-corpus
statistics, complete-day coverage or a representative random sample.

Verdict: **promising behavioural benchmark, not a drop-in AWS training set**.
Its explicit terms, user routines and documented longer history make it worth
further review. It requires a dedicated source adapter and a review of meaningful
features; AWS IAM/STS semantics cannot simply be invented or filled in as though
they had been observed. Named pseudonyms cannot be linked to our cloud accounts.
Do not weaken the audited-lab input gate to accept it as fabricated AWS evidence.

Next work: review a source-specific cloud-storage feature/model contract and
larger chronological subsets, including declared normality, identity continuity,
coverage gaps and the authors' controlled hijacking evaluation method. Keep this
benchmark separate from AWS lab evidence and preserve the 71-feature CERT work.

Reproduce the prefix audit after obtaining the bounded official ZIP prefix:

```powershell
python scripts/audit_clue_prefix.py --prefix data/live/public/clue-7119953/clue-prefix.zip.part --out data/live/public/clue-7119953/NEW-audit.json
```
