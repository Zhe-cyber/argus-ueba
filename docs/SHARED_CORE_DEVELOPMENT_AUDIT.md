# Shared-core development audit, 29 October 2026

Read-only audit of the existing inspected 27 MiB prefix and frozen 55-account
fitting population. No new download, training, scoring, injections or reserved
test inspection contributed. Namespace statistics use fitting dates only.

| Partition | Observed days | k=3 eligible | k=5 eligible | k=7 eligible |
|---|---:|---:|---:|---:|
| Fitting | 605 | 591 | 543 | 454 |
| Validation | 188 | 188 | 188 | 188 |
| Normal calibration | 169 | 169 | 169 | 168 |
| Inspected development | 191 | 191 | 191 | 191 |

Eligibility here means prior observed active-day count only, not full feature
validity. Select k=5 as a documented coverage/history compromise: retains 89.8%
of fitting days and all 169 calibration days before other validity filters.
Neither this comparison nor the choice used attack recall. This is not proof
that five days provides sufficient behavioural history in live systems.

Fitting namespace findings:
- 834,907 events, 664,034 with nonempty usable paths; 170,873 without paths.
  These missing-path events are not automatically invalid: many actions are
  resource-free. An action-specific expected-resource table is still required.
- 186,882 distinct full paths versus 1,503 first-component namespaces.
- Median distinct values per path-bearing account-day: 21 full paths versus
  2 namespaces; maxima 140,947 versus 285.
- First component equals the actor pseudonym in only 8 path events. Lexical
  inequality does not establish ownership or container meaning.

Decision: retain literal first-component namespace as the proposed coarsening,
and never call it a verified bucket/container equivalent. This audit establishes
its granularity and variability, not its semantic equivalence to live resources.
Large differences between account-day counts also remain a training limitation;
do not assume pooled population scaling is account-conditioned detection.

Private machine-readable report: data/processed/shared-core-v1/development-audit-20261029.json.
Reproduce with scripts/audit_shared_core_development.py using the frozen prefix
and manifest. Both hashes are checked before the audit. Three focused tests
pass: prior active days, later-date/unselected-account exclusion, fitting-only
namespace coarsening. No existing model or collector changed.

Remaining before freeze: resource validity table, canonical action mappings,
exact generator details, versioned streaming extraction, leakage/parity tests.
