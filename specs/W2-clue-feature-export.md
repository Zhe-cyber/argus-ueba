# W2: Isolated CLUE profile and chronological export

27 October 2026. Stacked on PR #14. Implement clue_behavior_v1 independently of
the frozen CERT/cloud runtime. No live source registration, scoring or training.

Use the reviewed ten-feature profile: total/native-action/path diversity,
fixed UTC off-hours, strictly prior-day action novelty, file_accessed,
login_attempt, login_successful, explicit sharing actions, permission_changed.
Unknown native actions still contribute total/diversity and coverage counters.
Do not infer failures, IPs, sensitivity, human roles or AWS API categories.

Stream a bounded official archive prefix (maximum 32 MiB compressed, 1 GiB
expanded, 2 million records) without extraction or upstream code execution.
Validate JSON shape, native IDs and chronological UTC timestamps; preserve real
dates. Exclude IP-based/anonymous identities; drop first/last capture dates and
mark interior days as bounded-subset candidates, not guaranteed complete source
coverage. Keep metadata gaps/partial dates explicit.

Write pseudonymised feature JSON and provenance to new gitignored paths. Select
eligible identities using warmup/fitting activity only; never inspect later
activity to choose the population. Explicit disjoint UTC cutoffs define warmup,
fit, validation, normal calibration and held-out evaluation. Report operational
readiness/minimum coverage and per-split counts, not performance or independent
benign verification. Keep labels/coverage outside the ten-feature vector.

Test exact category mappings, novelty/history isolation, anonymous exclusion,
real UTC boundaries, unknown action coverage, split/selection leakage refusals,
stream/archive limits and output non-overwrite. Run SQLite-isolated tests; open
draft PR, human merge and independent review pending. No model activation or
changes to frozen features; the existing AWS lab training gate stays separate.

Observed-data refinement: native IDs increase, but the larger prefix contains
one-second timestamp reversals within the same UTC day. Preserve and count these;
group windows by true UTC date rather than assuming arrival order. Block readiness
on cross-day reversals pending review. Never sort/shift timestamps to invent
history. Failed/incomplete range downloads stay separate from verified prefixes.
