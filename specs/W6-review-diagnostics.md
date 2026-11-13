# W6 review: reporting diagnostics, not a revised detector

28 October 2026. The user supplied Claude's six-file review manually. No
correctness/leakage blocker was reported; mathematical/reporting limitations
need clarification. Do not change the frozen W6 score, > rule, calibration,
reference, cases or original report. Write a separate supplementary artifact.

Use the existing hash-pinned report/reference/calibration/manifest/native prefix.
Check the scorer/projection/resource adapter source hashes against the report.
No downloads, provider calls, new fitting/calibration, live actions or source
transfer to Claude. Original report SHA remains
966622ad25ce51b3081f4fc5778543d5ecb0195e6910907956b91462914b276c.

Diagnostics fixed before executing them:
- Count scores within absolute 1e-12 of each fixed threshold, plus exact ties,
  strict positives, and near-above/near-below counts. This tolerance changes
  reporting only. Saved normal/switched scores stay untouched. Calibration
  per-day scores were not saved; replay ONLY their inference from the persisted
  reference and original native projection, checking row digest and original
  threshold/alert-count reproduction. Do not recalibrate or rescore switches.
- Split unavailable coverage into no resource activity, resources all globally
  unseen, and other history/coverage states. Keep original statuses too.
- For the six already-positive days, report fitting-known resources absent
  from the recipient and seen only under the donor in the 55-account fitting
  population. Distinguish globally unseen resources. This is literal-token
  exclusivity in the inspected sample, not ownership or granted permission.
- Independently report how many positive-day distinct resource tokens have a
  first nonempty literal slash-delimited path component seen only under the
  donor during fitting. No path normalization or guessed username matching.
  This crude prefix proxy does not establish a home directory or common global
  namespace; shared generic prefixes cannot disprove deeper namespace effects.
  Emit aggregate per-case/day counts only, never paths/components/hashes/IDs.

Correct the prose: pooled popularity cancels exactly for tokens never used by
the account. All observed positives are saturated days. The approximate
foreign-resource-fraction rule assumes previously seen tokens contribute zero;
it is not a necessary condition for every possible day. Equal-history v2 may
remove this ceiling disparity but raw bounded novelty already saturated in a
previous diagnostic; check that hypothesis on development data first, rather
than consume an untouched evaluation window to discover it again.
