# C2 live coverage policy review — 31 October 2026

Reviewed `scripts/live_coverage_policy.py`, its eight tests, updated handoff and
the existing native matcher. **Eight tests passed independently.** The policy's
direction is approved, but fix the three reproduced integration issues below
before using it to populate live explanation receipts. C1 schema/synthetic work
can proceed meanwhile. Claude retains implementation ownership.

No real model inference, fitting, release, reserved-test access, provider call or
live store/ledger change occurred in this review. Synthetic probe artifacts are
under `data/live/c2-review-20261031/` (ignored).

## 1. Excluded case days are validated as ordinary days before exclusion

`persona_day_coverage()` validates every row against `planned_actions()` before
assigning `excluded_case_date`. On 14 November, a real V3 target action changes
bucket/symbolic_bucket to p06. That differs from the ordinary frozen generator,
so the policy raises `ValueError: Stored action differs from the frozen plan`
before it can exclude the case date.

Reproduced with one synthetic 14-Nov persona-01 GetObject changed to the declared
p06 resource. The entire policy run aborts, including prior otherwise valid days.
The existing future-date exclusion test contains no actual substituted rows, so
it does not catch this.

Required: partition excluded case-date rows **before ordinary-plan validation**.
Return explicit excluded cells/provenance, without treating case actions as
ordinary history. Preserve strict validation for all non-excluded dates. Add
substituted-action tests on 14/15 Nov, including the unavailable persona-01 slot
on 15 Nov; no replacement action or target is allowed.

## 2. Native coverage must obey the same ingestion cutoff as the feature snapshot

Reusing `readiness.native_matches()` preserves the desired receipt checks, but
that helper checks event time against `now`, not native `ingested_at` availability.
The new policy can therefore accept receipts absent from the diagnostic snapshot
at its declared generation cutoff.

Synthetic reproduction: all successful native events have event times on 2 Nov,
but `ingested_at` one day after NOW (3 Nov). All **six** role-days still return
usable. The corrected live feature audit would exclude those future-ingested
rows, producing inconsistent coverage and features for the same receipt.

Required: keep the frozen matcher unchanged and add a live-policy availability
check for parseable, aware `ingested_at <= cutoff`, with explicit missing/late/
invalid evidence status. Use the same cutoff/snapshot binding for coverage,
account mapping and event features. Reject naive cutoffs instead of relying on
host-local `datetime.astimezone()` interpretation. Add future-ingestion and
offset/naive-cutoff regression tests. Do not equate a file-byte hash with an
atomic multi-file snapshot; retain the existing separate-snapshot limitation.

## 3. ARN mapping accepts null/non-native account keys

`persona_account_keys()` inserts any matching row's account_key into its set.
One unique `None` value passes the cardinality check and is returned as the
persona's key. Reproduced by setting all persona-01 event keys to NULL; the
function returns persona-01 -> None. The current synthetic fixture also uses
`acct_persona-01`, which is not a native scoped account key.

Required: enforce the actual `acct_[0-9a-f]{64}` account-key contract, valid native
assumed-role identity evidence, account namespace and the common cutoff. Missing
or invalid keys must produce an explicit unavailable/fail-closed mapping, never
an accepted `(None,day)` key. Preserve the existing ambiguity rejection. Update
fixtures to use deterministic valid scoped keys and add null/malformed-key tests.

## C1 integration requirements carried forward

- Use this live-only policy and code hashes outside the frozen W33 sources.
- Exclude incomplete/commissioning/case days before adding them to diagnostic
  history. Advance/report chronology without inventing empty active days.
- Bind coverage to the full scoped account/day key and the same cutoff as the
  feature snapshot. Include accepted prior-day keys and independently verified
  native references, not just aggregate counts or ledger status labels.
- Coverage is coverage of **planned controlled actions**. It does not prove the
  observed account had no other activity, nor that every log was collected.
  Keep observed-versus-planned counts explicit; do not silently remove unexpected
  genuine events or manufacture benign values to reconcile counts.
- Keep non-persona completeness unknown rather than imposing the planned-script
  denominator on human/service accounts with no declared plan.
- The 30-Oct start and commissioning exclusion are prospective diagnostic policy
  decisions. Preserve older diagnostic reports under their original bindings.
- Current-day scoring uses the same day-quality gate as history. Five prior
  accepted days permit mechanical input, not live transfer validation.

## Other coordination

C6 cleanup is visible in the main handoff. The history section still has old
wording intentionally, correctly marked as superseded.

C1 can be built now with eligible/ineligible/unsupported/zero-error fixtures and
an explicit receipt version. No need to wait for a forecasted real eligibility
date. Once C2 is corrected, hand over both interfaces for the UI consumer review.

AWS V3 remains Codex-owned. Its date amendments, slot handling, source bindings
and controlled release are separate pending work; this C2 review does not claim
they have already been installed. No global power settings were changed.
