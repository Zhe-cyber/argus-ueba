# Codex review of Claude's W33 engineering handoff

30 October 2026. Reviewed the implementation in the active
`clue-benchmark-replay/fyp-ueba` worktree. The supplied OneDrive handoff path does
not exist; its actual file is `docs/CLUE_AE_V2_ENGINEERING_HANDOFF.md` here.
No real CLUE records were opened during this review. Synthetic fixtures only.

## Verdict

Accept the reader/feature/export/report engineering layer after the corrections
below. This is not training approval evidence, a completed model, a final freeze
or reserved-test release. Existing access foundation remains unchanged. No live
runtime, source pins or W33 method definition changed in this review.

Claude's 67 focused tests independently passed. A further synthetic reproduction
found a cohort-file binding defect not covered by them. After the fixes, all
74 focused tests passed; changes to wording/test names do not change semantics.

## Corrections applied by Codex after ownership returned

1. **Cohort file checksum:** the manifest hashed canonical JSON without its
   trailing newline, but wrote a newline to the file. The checksum therefore
   differed from the actual bytes and would fail downstream binding. Hash and
   write the same byte string; regression assertion checks the actual file hash.
2. **Availability-before-export guard:** the real export CLI now requires
   `--availability`. It checks the exact allowed fields, same reader receipt,
   six strictly positive integer monthly totals, and a nonnegative integer
   parse/error total. Absent required monthly coverage is no-go, never a split
   shift. Availability artifacts remain preserved if the check fails. The
   export binds the availability file's SHA256. Six fixture cases test the
   success and rejection paths. This implements the existing W33 coverage gate;
   it does not introduce a data-selected threshold.
3. **Validation file integrity:** the report wrapper rejects any non-validation
   row in `rows-validation.jsonl`, even when its hash matches the manifest.
   It cannot silently skip misfiled calibration/fitting observations. The pure
   descriptive helper can still select validation observations from an explicit
   mixed fixture; the production validation-file boundary is stricter.
4. **Accurate boundary wording:** Python JSON parsing reads the boundary object;
   only the time field is consumed, and no boundary row is yielded to features,
   retained in outputs or logged. Do not claim that non-time fields were never
   parsed. The renamed test and docstrings state what is actually enforced.

## Handoff assumptions resolved without changing W33

- Cohort eligibility counts observed original fitting active dates, as W33
  section 3 states, while score/history eligibility uses usable days. Accounts
  selected but later unusable are excluded/reported, not replaced.
- Invalid-day exclusion follows W33. A must use its own frozen W23 extraction
  and history in the later evaluator. B's corresponding five feature meanings
  use W33 history; do not present A/B as a pure volume-only causal experiment.
- Structural malformations fail closed. No new malformed-event salvage rule.
- Retain the existing 60-million-event streaming bound. A bound failure is a
  recorded no-go or a new prospective amendment, never an automatic increase.
- Parse/error total covers the scanned timestamp-check range, including rows
  before the first reported month; it reveals no account details. Monthly
  totals alone still do not prove per-account or reserved-day coverage.
- Descriptive medians use `higher` per W33 section 8. The feature-6 history
  median and C-norm median retain their separately specified midpoint rule.
- Export manifests bind outputs; the later training preregistration and final
  evaluator release still need their own exclusive receipts. They are not
  implemented or replaced by this export manifest.
- Training, C-norm references, BL, thresholds and the new-cohort scenario adapter
  remain pending. Do not modify frozen W23 `pairs()` to remove its 55-account
  constraint; later W33 code needs a separately bound adapter with the same
  declared pairing algorithm.

## Corrected first real-run sequence — not executed by this review

1. Verify the unchanged foundation.
2. Bind the reviewed reader to a new receipt. This rehashes archive bytes but
   decodes no events.
3. Run the approved aggregate-only availability check and inspect its exit code.
   No account-level or feature output is permitted from this scan.
4. Export only after successful availability, using:

~~~powershell
& $py scripts/export_clue_v2.py --reader-receipt data/processed/clue-ae-v2/reader-access-v1.json --availability data/processed/clue-ae-v2/availability-v1.json --out data/processed/clue-ae-v2/pretest-export-v1
~~~

5. Check export gates before training; generate the validation-only report.
   Stop on any failure, preserving evidence and keeping dates unchanged.

The original handoff command omitted the now-required availability argument;
use the corrected command above. No actual scan, extraction, cohort selection,
training or reserved evaluation has been performed by this review. The 15 Nov
23:59 MYT freeze and 16–17 Nov single evaluation remain unchanged.
