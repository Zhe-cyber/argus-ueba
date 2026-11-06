# Claude task: W33 offline implementation while Codex handles the live system

User requested parallel work, 30 October 2026. This handover assigns engineering
work only; it does not authorise reserved-test access or live activation.

## Workspace and first reads

Work in this exact checkout, not the separate OneDrive checkout:

`C:/Users/yyzhe/.codex/worktrees/clue-benchmark-replay/fyp-ueba`

Read these local files first:

1. `specs/W33-clue-ae-v2.md` — approved method, including the prospective amendment.
2. `reviews/CLUE_AE_V2_CODEX_REVIEW_2026-10-30.md` — rationale and known failures.
3. `docs/CLUE_AE_V2_IMPLEMENTATION_STATUS.md` — implemented versus pending.
4. `scripts/clue_v2_access.py` and `scripts/tests/test_clue_v2_access.py`.
5. Frozen W23 resource/action semantics in `scripts/shared_core_features.py`,
   `docs/SHARED_CORE_RESOURCE_RULES.md`, and the existing native CLUE readers.

The existing private access-plan receipt is
`data/processed/clue-ae-v2/access-plan-v1.json`; its content binding is
`1e67b87930e4c7faac5a839a35157e3c9c7784e0985ec86bbc06e72e8f3c4ee9`.
It binds only the access foundation, not future reader/feature implementations.
Do not edit or overwrite it. The real archive has been rehashed without decoding
records. No W33 monthly check, extraction or training has run.

## Your deliverable: reader and feature pipeline, tested on synthetic fixtures

Build the following new files, keeping their ownership separate from Codex:

| File | Required work |
|---|---|
| `scripts/clue_v2_reader.py` | Bounded ZIP/line streaming; timestamp-only monthly availability output; pre-test reader/date barriers; source-bound reader-access receipt referencing the existing foundation |
| `scripts/clue_v2_features.py` | W33 nine-feature extraction, chronological history, eligibility and deterministic fitting-only cohort logic |
| `scripts/export_clue_v2.py` | Offline export orchestration with immutable input/source/cohort bindings and partition coverage; no training or evaluator invocation |
| `scripts/report_clue_v2_validation.py` | Exact validation-only descriptive report for features 6–9, including missingness, coverage, quantiles and saturation |
| `scripts/tests/test_clue_v2_reader.py` | Reader boundaries, permitted output, malformed/bounded input, hash mutation and synthetic reserved-data isolation |
| `scripts/tests/test_clue_v2_features.py` | Exact maths, cold start, bounded/expanding history separation, quality exclusions, same-day variants and cohort isolation |
| `scripts/tests/test_clue_v2_export.py` | Split/cohort/export guards and private/exclusive outputs |
| `scripts/tests/test_clue_v2_validation_report.py` | Correct statistics and refusal of non-validation observations |
| `docs/CLUE_AE_V2_ENGINEERING_HANDOFF.md` | Files changed, commands, test evidence, interfaces, limitations and any protocol ambiguity |

If a listed filename already exists when you start, stop editing that file and
report the ownership conflict; do not overwrite another worker's implementation.
Use shared existing frozen helpers by import where appropriate, without editing
them. New files must be inert on import: no archive reads, tasks or cloud calls.

### Important method details

- Freeze gate **15 November 2026, 23:59 MYT**; single reserved evaluation
  **16–17 November**, report by **17 November**. AWS dates are unchanged.
- Benchmark validation is **27 November–3 December 2017**, not client dates.
  Reserved test is **15–28 January 2018**. No shifts or replacement cohorts.
- Features 1–5 retain W23 meanings. Feature 5 uses expanding prior actions;
  features 6–9 use at most 28 usable prior original active days. At least five
  prior usable active days; resource-free feature 7 is unavailable, never zero.
- JS **distance**, base 2, event-weighted, total pseudocount mass 1 spread over
  the shared bins. Do not substitute old W29 divergence or drop unseen kinds.
- All variants use one start-of-day history snapshot; update once with original
  events only. Invalid original days are not partially salvaged into history.
- C-norm is already decided in W33. Do not change it or implement a different
  scoring design. Training code is a later task, not part of this assignment.
- Existing frozen core feature extraction may impose historical population,
  time or prefix bounds. Do not loosen those helpers; write a separate W33
  wrapper/reader implementing only the approved new bounds.
- Report values only for original validation rows; historical events may supply
  prior state. No scenario outcomes or score-driven decisions in descriptives.

### Archive and embargo safety

Use **synthetic small ZIP/JSON fixtures only** for this assignment. Do not scan,
extract or inspect the real archive, run monthly counts, compute real features,
select the real cohort, train, calibrate, or access reserved records. Codex will
review the implementation and new reader binding before the first actual scan.
Do not download datasets, authors' code or dependencies.

Make the availability scanner's only data-derived output the six approved
calendar-month event totals plus parse/error totals. Do not return raw rows,
IDs, event types, account aggregates or per-day counts through logs/callbacks.
The scanner may parse timestamps internally as W33 permits; that is not
permission to feed reserved fields to feature code.

Explicitly test the unavoidable streaming boundary: discovering a cutoff can
require reading a timestamp on the first out-of-range row. Never yield, retain,
log or inspect its account/action/resource fields. If the reader design cannot
meet W33's intended boundary, document the ambiguity before real use rather
than silently broadening access. Reject cross-day reversal/unsupported archive
shape and respect byte/line/event limits; avoid fully unpacking the archive.

Any binding of a reader must include the actual new reader/test/source files,
their transitive project dependencies and W33, not merely assert that the old
foundation already covers them. Fail on mismatch. Write a new receipt only on
explicit invocation; do not run the invocation against the real data now.

## Ownership: leave these to Codex

Do not edit backend, frontend, infrastructure, live collector/pilot scripts,
scheduled tasks, source pins, DPAPI state, cloud resources or databases. Do not
touch `local_pilot.py`, `collect_live.py`, GitHub/Cloudflare setup/workload files,
or AWS study implementation/specs. Codex owns live ingestion, bot round trips,
normalisation integration and dashboard work.

Do not edit W33, `clue_v2_access.py`, its tests, or any frozen W23/core/scenario/
training/evaluator source. Raise an ambiguity in your handoff instead. Do not
update Codex's implementation-status document while Codex owns it.

No Git reset, stash, checkout, branch switch, staging, commit, push or automated
cleanup. The checkout contains substantial uncommitted reviewed work. Preserve
it. No sending raw data/source to another external service or agent.

## Validation and return

Use the existing Python environment:

`C:/Users/yyzhe/OneDrive/Documents/fyp-ueba/.venv/Scripts/python.exe`

Set `DATABASE_URL=sqlite-local` for tests. Use a new workspace test directory
below `data/live/test-runs/`, never the real connected store. Keep files LF.
Run the 18 existing access tests and your new focused synthetic tests. If a
dependency/environment prevents a test, report that accurately; do not weaken
the test or substitute an unverified success.

Return one engineering handoff with changed paths, exact test command/results,
coverage of the access boundaries, unresolved assumptions, and proposed first
real-run commands **without executing them**. Then hand ownership back for Codex
review. Do not proceed to training or January evaluation on your own.
