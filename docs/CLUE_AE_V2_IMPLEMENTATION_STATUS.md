# W33 implementation status

30 October 2026. The approved W33 method and its prospective date amendment are
in `specs/W33-clue-ae-v2.md`. They are not a completed model or test release.

## Completed: access binding foundation

- `scripts/clue_v2_access.py` records exact partitions, no date shifts, amended
  15 November 23:59 MYT freeze, 16–17 November execution window and 17 November
  reporting deadline. Its plan explicitly refuses reserved access/activation.
- Pure date guards reject reserved days for pre-test processing and non-validation
  days for the descriptive report. These guards still need integration into the
  actual streaming readers; their tests alone do not establish reader isolation.
- An exclusively created private receipt binds W33, this access module, its tests,
  the archive manifest, and a fresh checksum of the compressed archive bytes.
  No ZIP member or event was decoded. The original verified archive matched.
- Receipt: ignored `data/processed/clue-ae-v2/access-plan-v1.json`;
  content binding `1e67b87930e4c7faac5a839a35157e3c9c7784e0985ec86bbc06e72e8f3c4ee9`.
- 18 synthetic-file tests passed, including source/archive/manifest/receipt
  mutation rejection, exclusive output, private output bounds and date barriers.
  Verification of the real binding also passed. No live runtime files changed.

## Reader/feature layer added and reviewed

Claude returned the separate reader, nine-feature pipeline, two-pass exporter
and validation-only report generator with synthetic tests. Codex independently
ran the original 67 focused tests, reproduced and fixed a cohort-file checksum
bug, added the bound availability-before-export check and stricter validation
file integrity, and ran 74 focused tests successfully. No W33 real-data scan
was performed. Full review and corrected export command:
`reviews/W33_CLAUDE_ENGINEERING_CODEX_REVIEW_2026-10-30.md`.

The streaming boundary object is JSON-parsed internally, but only its time is
consumed and no reserved row is passed to feature/report code. This is not a
claim that boundary fields are never parsed.

## Real pre-test export and validation report now present

Subsequent artifacts supplied for review on 30 October include reader-access-v2,
availability-v2, pretest-export-v1 and the validation feature report. Codex
verified their source/data/receipt bindings and reproduced the report exactly.
The export passes its declared engineering gates: 74 selected accounts and
3,468 fit / 275 validation / 510 calibration common nine-feature account-days.
The reader/availability v1 artifacts are retained as earlier bindings, not
silently overwritten. This updates the earlier not-yet-run status below.

Report review: `reviews/W33_VALIDATION_FEATURE_REPORT_CODEX_REVIEW_2026-10-30.md`.
Resource novelty is sparse and 45 otherwise valid validation days lack resources;
no feature changes or model-selection decisions were made from those findings.
B/C training, C-norm references, BL, thresholds and the final evaluator remain
pending in the reviewed artifacts. No live model activation.

## Original next-step record, superseded by the export above

Bind the reviewed timestamp-only availability scanner and bounded pre-test
reader implementations and tests in a new prospective receipt referencing the
foundation. Do not overwrite it or pretend the foundation already binds these
new files. The exporter now requires the successful availability artifact from
that same reader receipt before its production invocation can process records.

Then run the declared availability check; if it fails, stop without moving dates.
Actual feature extraction, cohort selection, B/C training, C-norm references,
validation descriptives, December thresholds and final evaluator release are
all pending; having their engineering pipeline is not having their real outputs.
No January account-level data or scores were inspected. AWS dates are unchanged.

## Commit preparation

The manual checklist now covers backend implementation, frontend, infrastructure,
new scripts/specs and the aggregate offline result artifacts. It explicitly
excludes handovers and private state and warns that ignored metrics CSVs need
individual review/staging. No files were staged, committed or pushed by this work.
The existing worktree still has substantial uncommitted work; its safety is not
established merely by recording a content hash. A local commit preserves Git
history; an authorised push or another backup is needed for an off-device copy.
