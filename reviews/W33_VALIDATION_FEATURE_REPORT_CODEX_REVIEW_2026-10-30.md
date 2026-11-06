# W33 validation feature report review

30 October 2026. Reviewed the report in the active worktree:
`results/clue-ae-v2/validation-feature-descriptives.md`.
The supplied OneDrive path was absent; the active-worktree report was present.

## Verification

The report reproduced exactly from the bound original validation export using
the current report generator. Verified export source hashes, actual cohort file
hash, all partition-file hashes, feature contract, reader/foundation bindings and
the successful availability artifact. No new archive records were decoded by
this review; the archive was only rehashed by binding verification.

The export reports 74 fitting-selected accounts, below the cap of 500, with
3,468 common nine-feature fitting days, 275 validation days and 510 normal
calibration days. All declared export engineering gates pass. These are
coverage/engineering results, not a trained-model or detection result.

Validation includes 326 original observed account-days across 61 accounts:
320 pass day quality and six are invalid. Forty-five of the 320 valid days have
no resource today and therefore cannot supply feature 7; they remain excluded
from the nine-feature common rows, never zero-filled. Nine-feature validation
coverage is 275/326 observed days, across 57 accounts.

## Interpretation, without changing the method

| Feature | Observation | Interpretation |
|---|---|---|
| Volume log ratio | 287 distinct values; median -0.0165 | Has normal variation around the account's historical median; no detection claim |
| New-resource share | 17 distinct values; 85.8% zero and 1.82% one among 275 available days | Sparse normal novelty, not the previous all-one ceiling; does not establish takeover sensitivity |
| Action-mix JS distance | 304 distinct values; median 0.234; no values at one | Not constant/saturated at the upper bound; still only normal-day variation |
| Hour-profile JS distance | 311 distinct values; median 0.647 | Substantial distance occurs on normal days; a high raw distance is not inherently suspicious |

Daily volume/sample size, smoothing, event-weighting and genuine day-to-day
variation can affect histogram distances. Do not infer the cause of the hour
distance distribution or tune the features after reading this report.

## Decision and next model step

Accept this descriptive report as the pre-freeze W33 deliverable. Retain the
declared features, preprocessing, missingness, denominator and gates unchanged.
The report shows computable, nonconstant inputs and known coverage loss; it does
not show attack discrimination or validated live transfer.

Next implement/review training and its exclusive preregistration binding these
actual artifacts, then fit B and C once. Implement the declared C-norm reference,
BL and calibration thresholds without scenario labels. Freeze the evaluator and
all required artifacts by 15 November 23:59 MYT; the single reserved evaluation
remains 16–17 November with reporting by 17 November. No live activation follows
from this report. AWS study dates remain unchanged.

Report export-manifest SHA256:
`b430d536676baa0031de84a649689611d36239d6a8d1d4c374718dc7e9011086`.
Validation-file SHA256:
`6e12a957307ee0b1a79ebc639bebb2ef341ae9ea72a96f208be1743ae3ed8e3d`.
