# Spec: L1-live-baseline-score — per-account baseline risk score on all three clouds, shown in the workspace

**Branch:** `l1-live-baseline` (off `origin/six-role-commissioning`) · **Executor:** executor (sonnet); heavy only on escalation · **Written:** 2026-11-10

## Goal
The analyst workspace shows a transparent 0–100 **baseline risk score** for every account-day on
AWS, GitHub and Cloudflare, computed from that account's own history, with a tier
(High / Medium / Low / Learning), the plain facts behind it, and findings ranked by it. Phase B
adds a cross-cloud **workload group** view (one actor's accounts on several clouds, one combined
score). This is the system shown in the monitoring-week live demo (week of 16 Nov 2026).

## Non-goals
- No change to `backend/`, to any file in `scripts/reserved_study.py::SOURCE_FILES`, or to
  `scripts/train_clue_v2.py::TRAINING_SOURCES`. Import read-only if needed; never edit.
- No change to the AE diagnostic gate (`experimental_diagnostics_approved` stays False). The AE
  stays hidden until W33 is evaluated; the baseline score is a separate, labelled panel.
- No new model, no training, no threshold tuning on observed results.
- No writes to the live database, no cloud calls, no touching the running pilot or its worktree.
- No stored-severity rewrite: recorded finding severity stays as recorded.
- No commits, pushes or PRs. The user commits. Leave the work uncommitted in the worktree.

## Files in scope
New:
- `workspace_next/baseline_score.py` (pure scoring + SQLite read)
- `workspace_next/workload_groups.py` (Phase B)
- `backend/tests/test_baseline_score.py`, `backend/tests/test_workload_groups.py` (Phase B)
- `workspace_next/frontend/components/BaselinePanel.js`
- `docs/LIVE_BASELINE_SCORE_V1.md` (method note, one page)

Edited:
- `workspace_next/app.py` (mount routes only)
- `workspace_next/queries.py` (attach `baseline` to each finding's context)
- `workspace_next/frontend/pages/workspace.js`, `pages/entities.js`

Runtime (untracked, outside git): preview root `data/live/live-v1-preview/`.

## Approach (planner-decided)

### Setup
1. Create the worktree at `C:\Users\yyzhe\argus-worktrees\l1-live-baseline` (LESSONS 14: never
   under Temp or OneDrive) from `origin/six-role-commissioning`, run from the repo at
   `C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba`. Do not modify any file in
   that source checkout: it is the live pilot. Python: `C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe`.
2. Check the `events` table shape on a read-only connection to a **copy** first (step 9) and
   confirm: `timestamp` format, `source`, `action`, `resource`, `account_key`, `account_label`,
   `account_kind`. If a column is missing, stop (escalation).

### Phase A — score, API, display (must-have)

3. **Unit of scoring.** One score per `(account_key, MYT calendar day)`. MYT = UTC+08:00, no DST.
   Events with NULL `account_key` are ignored.

4. **History.** For day `d`: the account's events on its previous active days (days with at
   least 1 event) inside the 28 calendar days before `d`. If fewer than **5** prior active days →
   no score, tier `Learning`, reason `"n of 5 days of history"`.

5. **Signals**, each in [0, 1] (`today` = events on `d`, `hist` = history events):
   | Signal | Weight | Definition |
   |---|---|---|
   | `new_action` | 0.25 | k = distinct `(source, action)` today not in hist. 0 → 0; 1 → 0.6; ≥2 → 1.0 |
   | `new_resource` | 0.25 | Over today's events with non-empty `resource`: k = distinct resources not in hist. 0 → 0; 1 → 0.6; ≥2 → 1.0. No resource-bearing event today → signal **unavailable** |
   | `unusual_hours` | 0.20 | usual hours = MYT hours holding ≥ 5% of hist events. s = share of today's events outside them; signal = min(1, s / 0.5) |
   | `volume` | 0.15 | r = count(today) / median(daily counts over hist active days). signal = clip(log2(r) / 3, 0, 1) (8× → 1; drops are 0) |
   | `sensitive_new` | 0.15 | 1 if any resource today matches `backend.rarity_scorer.SENSITIVE_PATTERNS` (import, do not copy) and that resource is not in hist; else 0 |
6. **Score** = round(100 × Σ wᵢsᵢ / Σ wᵢ over available signals). **Tier:** ≥ 60 High; 30–59
   Medium; < 30 Low. Weights and cut-offs are fixed here; do not tune them.
7. **Facts.** Each scored day returns plain sentences for every signal with a non-zero value,
   with the numbers (e.g. `"1 action kind never seen in the last 28 days: s3:GetBucketLocation"`,
   `"12 events today; median active day is 4 (3.0×)"`), plus `history_days`, `events_today`,
   and `partial: true` when `d` is today in MYT.
8. **API** (read-only, in `workspace_next`):
   - `GET /workspace/baseline?account=<account_key>&days=14` → newest-first list of
     `{day, score, tier, signals{name: value|null}, facts[], history_days, events_today, partial}`.
   - `GET /workspace/baseline/summary?day=YYYY-MM-DD` (default: latest day with events) →
     all accounts that day, sorted by score desc, with `account_label`, `account_kind`, `source`.
   - `queries.py`: each finding gains `context.baseline = {score, tier}` for the finding's
     account on the finding's MYT day (or `{tier: "Learning"}`).
   Cache per `(db path, db mtime)`; the tables are small — no new dependency.
9. **Preview root.** Build `data/live/live-v1-preview/` inside the new worktree with
   `scripts/prepare_workspace_preview.py` from the live DB
   `C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live\connected\events.db`
   (read-only source; the script copies and writes the `workspace-copy.json` marker).
   **Study guard:** until 16 Nov 2026 00:00 MYT the copy must contain no events dated
   14 Nov 2026 MYT or later. Take the copy before 14 Nov, or delete those rows **from the copy**
   after copying. Never from the source.
   Frontend: copy `data/live/workspace-case-preview-20261030-v1/frontend` (with `node_modules`,
   without `.next*`) from the pilot checkout into the new preview root, overlay the tracked
   `workspace_next/frontend` files, `next build` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8017`.
   Serve API on **8017** and UI on **3013** (3011/8015 stay as they are). No `npm install`.
10. **Frontend.**
    - `BaselinePanel.js`: for a selected account — today's score as a large number with tier
      colour, the facts list, and the last 14 days as a row of small tier-coloured bars
      (plain divs, no chart library). Header text: `Baseline risk score v1 — compared with this
      account's own last 28 days. Heuristic; not a validated accuracy claim.`
    - `entities.js`: render `BaselinePanel` above the existing Model diagnostic panel.
    - `workspace.js`: show a score chip and tier per finding; default sort = baseline score
      desc, then created desc; show recorded severity as secondary text `recorded: High`. Add a
      tier filter (All / High / Medium / Low / Learning). Keep the existing triage filters.
    - `pages/index.js` (overview) is out of scope unless trivial: one line
      `Highest baseline score today: <label> <score>`.
11. **Tests** (`backend/tests/test_baseline_score.py`, temp SQLite, no fixtures from live data):
    cold start (< 5 days → Learning); a quiet normal day → Low; one new action → `new_action`
    0.6; new sensitive resource → `sensitive_new` 1 and tier ≥ Medium; 8× volume → `volume` 1;
    no-resource day → `new_resource` unavailable and weights renormalised; MYT day boundary
    (an event at 16:30 UTC belongs to the next MYT day); NULL `account_key` ignored; API returns
    newest-first; finding context carries `baseline`.
12. **Sanity report.** `python -m workspace_next.baseline_score --db <copy> --report` prints, per
    MYT day and per source, counts of High / Medium / Low / Learning account-days. Counts only:
    no account labels, keys, IPs or emails in the output.
13. `docs/LIVE_BASELINE_SCORE_V1.md`: the table in step 5, the formula, tiers, what it is not
    (not trained, not validated, not the V3 study method), and the step-12 counts.

### Phase B — cross-cloud workload groups (start only after Phase A acceptance passes)
14. `identity_links.approve()` refuses AWS principals and service tokens by design; do not change
    it. Instead read a declared mapping `workload-groups.json` in the preview root:
    `[{"group": "persona-02", "label": "Batch reporter", "members": ["acct_…", "acct_…"]}]`.
    The executor generates it for the six lab personas by matching `account_label`
    (`argus-ueba-actors-persona-0N` AWS role) and the Cloudflare service token of the same
    persona (mapping source: `scripts/cloudflare_machine_pilot.py` plan/persona config and the
    Cloudflare machine ledger, read-only). GitHub lab activity is one shared bot account: list
    it as its own group, not per persona. If the Cloudflare token ↔ persona mapping cannot be
    established from local files, stop and report (escalation) — do not guess.
15. `GET /workspace/groups?day=` → per group: members with their account-day scores, and
    `group_score = min(100, max(member scores) + 10 if ≥ 2 different sources have score ≥ 30
    that day else max(member scores))`, tier as in step 6, facts merged and prefixed by source.
    Label every response `"basis": "declared lab mapping, not identity proof"`.
16. `entities.js`: a third tab `Workloads` beside Accounts / People: group list sorted by
    `group_score`; selecting one shows a merged MYT timeline of today's events across its
    member accounts (reuse the existing timeline rendering) and each member's `BaselinePanel`.
17. Tests: group score rule (single source; two sources ≥ 30 → +10; cap 100); unknown account
    key in the file is reported, not crashed on.

## Acceptance checks (all must pass, runnable as written, from the new worktree)
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures (baseline: 747 passed, 1 skipped on Windows before this change)
- [ ] `git -C C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba status --porcelain` shows no change caused by this task (the spec file itself is expected)
- [ ] `git diff --stat origin/six-role-commissioning -- backend/ scripts/` in the new worktree lists only the new test files
- [ ] Step-12 report runs on the copy and prints counts; High ≤ 10% of scored account-days over 1–10 Nov
- [ ] `http://127.0.0.1:3013/entities` → selecting `argus-ueba-actors-persona-02` shows a score, tier, facts and 14 day-bars; `http://127.0.0.1:3013/workspace` shows score chips and sorts by score
- [ ] The preview copy has zero events on or after 14 Nov 2026 MYT (query the copy, print the count)
- [ ] Phase B only: `/entities` Workloads tab lists the persona groups with a combined score

## Risk notes
- **The pilot is live until 15 Nov.** Its checkout and `argus-cloud-live/.../connected/events.db`
  are read-only for this task. Open SQLite sources with `?mode=ro`.
- LESSONS 10: tests must not write to real state — temp SQLite only.
- LESSONS 11: this spec file is untracked in the pilot checkout; read it from
  `C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba\specs\L1-live-baseline-score.md`
  and copy it into the new worktree's `specs/`.
- Product rule: no Anthropic API anywhere in product code.
- Never print or log account IDs, emails, IPs, tokens or raw events. Reports are counts only.
- `rarity_scorer` has two off-hours windows by design; do not "fix" or reuse its off-hours flag.
  Step 5's `unusual_hours` is the account's own profile and is independent of both.
- Windows + OneDrive: keep everything under `C:\Users\yyzhe\argus-worktrees\`.

## Escalation triggers
Stop and report (do not push on, do not tune) if:
- the `events` copy lacks an expected column, or timestamps are not parseable as UTC;
- the step-12 report shows High on more than 10% of scored account-days for 1–10 Nov, or no
  account-day above Low at all (the planner decides what to do; the weights are not yours to change);
- any acceptance check needs an edit under `backend/` (other than the new test file) or to a frozen file;
- the frontend cannot be built without `npm install` / network access;
- the Cloudflare token ↔ persona mapping (step 14) cannot be derived from local files;
- the same step fails twice.
