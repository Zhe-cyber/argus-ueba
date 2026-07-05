# LESSONS.md — repo craft learned the hard way

*Executors read this before starting any spec. One line per rule, with origin.
Planners prune monthly: a rule that stopped earning its line gets deleted.*

## Rules

1. **Tests must run with `DATABASE_URL` forced non-postgres** (`sqlite-local`) — `.env`
   holds the production Neon URL and `config.py` loads it via dotenv. *(origin: test-run
   session 2026-07-03; 32 tests "errored" against remote PG before anyone noticed)*
2. **Test suite and API can drift silently — CI has no pytest gate yet.** Until W0 lands,
   never trust "tests passed last month". *(origin: 12 pre-existing failures found 2026-07-03,
   tests expected `value`, API returns `shap_value`)*
3. **Train/serve skew hides in default arguments.** `aggregate_window(history=None)` silently
   zeroed a trained feature in production. When serving code calls shared feature functions,
   verify every parameter against how training called it. *(origin: new_action_count bug,
   found in code grill 2026-07-03)*
4. **Docstrings here are trusted and therefore dangerous** — "last 7 days" claim was false,
   "5 flags" was 6, "r6.2" was r4.2. Verify docstring claims against code before relying on
   them in specs or the paper. *(origin: same grill)*
5. **Risk-tier thresholds live in ONE place now** (`_live_risk_tier` in backend/main.py).
   Never re-inline 0.7/0.4 comparisons. *(origin: dedup fix 2026-07-03)*
6. **PowerShell 5.1 quirks in this environment:** no `&&`, `$env:VAR=""` UNSETS the var
   (dotenv refills it), python stdout needs UTF-8 wrapping for em-dashes. *(origin: multiple
   sessions)*
6b. **`.ps1` files must be pure ASCII (or UTF-8 with BOM).** BOM-less UTF-8 em-dashes decode
   as cp1252 curly quotes and TERMINATE STRINGS, producing baffling parse errors. Keep all
   PowerShell scripts ASCII-only. *(origin: codex_review.ps1 parse failure, 2026-07-03)*
7. **The paper/report artifacts regenerate from `_build_*.py`** — edit sources of truth,
   not exported PDFs; the PDF goes stale silently when the docx changes. *(origin: paper
   edit session 2026-07-03)*

8. **Subagents can die mid-task on Pro quota — work must live in commits, not chat.**
   The W0 executor hit the session limit after finishing the code but before opening the
   PR; salvage was trivial ONLY because it had already committed in its worktree. Executors:
   commit as soon as acceptance checks pass, THEN do PR ceremony. *(origin: W0 run 2026-07-03)*

9. **Worktree agents may be cut from a stale base — verify before building.** The W2 heavy
   agent's worktree was one commit behind master (missed the W0 merge) and 12 "failures"
   masqueraded as regressions until it rebased. Executors/heavy: first step in any worktree,
   check `git log -1 master` in the ORIGINAL repo vs your base and rebase if behind.
   *(origin: W2 run 2026-07-04)*
10. **~~`test_get_stats_total_matches_n_users` is state-dependent~~ RESOLVED by W0.1**
   (branch `w0-1-test-hardening`): conftest.py now isolates the event store to a temp
   SQLite per test session. The real bug was worse than logged — the suite was MUTATING
   the developer's real `data/events.db` via `/ingest` across runs. Durable rule: **any
   test that exercises endpoints backed by file-based state needs an isolation fixture;
   check what a test WRITES, not just what it reads.** *(origin: W2 run 2026-07-04;
   resolved W0.1 2026-07-04)*

11. **Untracked working files don't exist inside fresh worktrees.** `scripts/aws_live_ingest.py`
   was untracked, so the W1-A worktree agent couldn't see it and had to copy it in from the
   original checkout — wasted setup. Before dispatching a worktree agent that must edit a
   file, confirm the file is committed (or tell the agent to source it from the original
   checkout path). *(origin: W1-A run 2026-07-04)*
12. **`/ingest` double-counts on duplicate eventID** (see UPGRADE_PLAN R10). Any ingest
   client that can retry (poller restart, SQS at-least-once) inflates scores. Client-side
   dedup is a band-aid; the durable fix is a server-side unique index on eventID. Don't ship
   the W1-B SQS consumer until that lands. *(origin: W1-A scout 2026-07-04)*

## Retro log (finding-count per merged PR — target: trending down)

| Date | PR | Claude findings | Codex findings | Lesson added? |
|------|----|----------------|----------------|---------------|
| 2026-07-03 | #1 (W0 tests+CI) | 1 (minor: envelope total/limit/offset untested) | skipped per §4 (test-only diff) | Yes — rule 8 |
| 2026-07-04 | w2-cloud-skew (local, unpushed) | 0 (planner line-review clean) | 0 — APPROVE (first automated codex run) | Yes — rules 9, 10 |
| 2026-07-04 | w0-1-test-hardening (local, unpushed) | 0 (planner line-review clean) | skipped per §4 (tests-only) | Rule 10 resolved + upgraded to durable form |
| 2026-07-04 | w1-a-poller-harden (local, unpushed) | 0 (scope clean; found real /ingest idempotency gap) | pending (scripts/, §4 rank 3) | Yes — rules 11, 12 + plan R10 |
