# Continuation prompt for Claude

Continue your Argus-owned work autonomously through the highest-priority ready
items in `docs/SUSTAINED_WORK_PLAN_2026-10-31.md`. Read the latest handoff and
`reviews/C2_LIVE_COVERAGE_CODEX_REVIEW_2026-10-31.md` first.

Start with the three C2 integration corrections; build C1's receipt schema and
synthetic fixtures in parallel where independent, then its generator, followed
by W33 synthetic result packaging. C6 documentation cleanup is done. Preserve
ownership: Codex implements AWS V3/live system/UI; you own the W33/coverage/
explanation/receipt/packaging files and their tests. Put optional independent
tests for Codex interfaces in new files only after the interface is handed over.

Complete and test one milestone, write a reviewable handoff, then continue to
the next independent task without repeatedly asking whether to continue. Re-run
tests when changes or unresolved concerns justify them, not to use remaining
tokens. Respect pending review dependencies and do not edit Codex's source.

Do not train B/C again, change frozen W33 sources/artifacts, open the reserved
window, or perform release/evaluation early. Your single W33 evaluation belongs
to 16–17 November MYT with its verified release; AWS V3 single-use steps belong
to Codex. Keep experimental live diagnostics unactivated and labelled.

Use available session capacity for useful work. Before context/usage limits,
write `reviews/CLAUDE_WORK_CHECKPOINT.md` using the plan's format so the next
session can resume safely. Stop when ready work is complete, a required human/
date/access gate blocks remaining work, or usage limits require it. Never claim
to run after your session has ended or to notify while the only host is offline.

No automatic Git commits/pushes, global power changes, unknown-action retries,
backfilling, invented evidence or new model/dataset scope. Return concrete review
packages in handoff files; the user passes them between sessions unless an
explicitly authorized communication channel is established.
