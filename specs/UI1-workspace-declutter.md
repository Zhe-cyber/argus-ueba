# Spec: UI1-workspace-declutter — less text around the facts, same facts

**Branch:** `ui-declutter` (worktree `C:\Users\yyzhe\argus-worktrees\ui-declutter`, based on `l15-eval-report` 097a472)
· **Executor:** executor (sonnet) · **Written:** 22 Nov 2026 (owner go, same day)

## Goal
The workspace reads in 60–90 seconds at a competition booth (25–26 Nov) and in the demo video. Keep every score and
fact visible. Move secondary text (drift, autoencoder drivers, explanatory sub-lines) behind one click, and shorten
repeated labels. **Presentation only.** After this task, the same data renders in fewer words.

## Non-goals (scope fence)
- No backend, API, scoring, feature, database or method change. `backend/`, `workspace_next/*.py`, configs: untouched.
  The fact strings produced by `backend/baseline_scorer.py` stay byte-identical (method binding v1.2 is frozen).
- No change to Method & limits (`pages/about.js`), the Cases pages or the Connections page.
- No new npm dependency, no `npm install`, no deletion of any information: everything hidden must be one click away.
- Nothing is committed or pushed (the owner commits). Do not touch the running live site (ports 8013/8017/3013),
  `C:\Users\yyzhe\argus-worktrees\l1-live-baseline\data\live\live-v1-preview\` or any live database.

## Files in scope
- `workspace_next/frontend/components/BaselinePanel.js`
- `workspace_next/frontend/components/LiveFeed.js`
- `workspace_next/frontend/pages/workspace.js` (the queue summary line only)
- `workspace_next/frontend/pages/entities.js` (the workload panel's fact tags only)
- NEW `workspace_next/frontend/lib/factFormat.mjs` (pure functions) + NEW `scripts/tests/fact-format.test.mjs`
  (same style as `scripts/tests/diagnostic-privacy.test.mjs`, run with `node --test`).

## Approach (planner-decided)
1. **`lib/factFormat.mjs`:** export two pure functions.
   - `shortFact(text)` rewrites the known fact strings and returns any other string unchanged:
     - `"<n> action kind(s) never seen in the last 28 days: X"` → `{ group: 'new', text: '<n> new action(s): X' }`
     - `"<n> resource(s) never seen in the last 28 days: X"` → `{ group: 'new', text: '<n> new resource(s): X' }`
     - `"<n> sensitive resource(s) not seen before: X"` → `{ group: 'new', text: '<n> new sensitive resource(s): X' }`
     - `"<p>% of today's events fall outside this account's usual hours (MYT)"` → `{ group: 'pattern', text: '<p>% outside usual hours' }`
     - `"<n> events today; median active day is <m> (<r>x)"` → `{ group: 'pattern', text: '<n> events · <r>× a usual day (median <m>)' }`
     - `"This account showed new <label> on <h> of <n> recent active days, so novelty is discounted."` → `{ group: 'note', text: 'Novelty discounted: new <label> on <h> of <n> recent days' }`
     - anything else → `{ group: 'other', text }` (verbatim).
   - `sourceTag(text)` turns a leading `[aws_cloudtrail] `, `[cloudflare_access] ` or `[github_audit] ` (any
     `[name] ` prefix) into `{ source: 'AWS' | 'Cloudflare' | 'GitHub' | <name>, text: <rest> }`; no prefix → `{ source: null, text }`.
   Regexes are anchored and tolerate the `x`/`×` and the `(s)` forms exactly as `backend/baseline_scorer.py` lines 240–273 emit them.
2. **BaselinePanel (finding panel):**
   - Facts: render under two small headings, **"New in the last 28 days"** (group `new`) and **"Today's pattern"**
     (group `pattern`), then `note`/`other` items as plain bullets. Each item shows `display(shortFact(f).text)`.
     Keep `display()` (privacy masking) on every string. The empty-facts message is unchanged.
   - Behaviour drift and the 14-day bars: move inside one `<details>` with summary **"More: drift and last 14 days"**
     (collapsed by default). Content unchanged.
   - `MlScoreRow`: headline becomes `Second opinion (autoencoder) · <score.toFixed(2)> · above normal` / `· within normal`
     (rose/emerald as now), keep the existing `Info` tooltip. Move the "driven by …" drivers and the 5%-setting line
     into a `<details>` with summary "Why". Keep `data-testid="ml-score-row"` and `data-testid="ml-score-secondary"`.
     Non-scored statuses render exactly as today.
3. **Work queue summary line** (the "`N to review first · … · K from the learning period`" sentence near line 122):
   render the same numbers as small rounded chips: **N to review** (emphasised), `automation K`, `office hours K`,
   `infrastructure K`, `learning K`. Keep the existing `Info` explanation and the "matching findings · groups" text.
   Counts and their sources are unchanged.
4. **Workload panel (entities.js):** each fact line renders `sourceTag(display(f))`: a small grey source chip
   ("AWS"/"Cloudflare"/"GitHub") followed by `shortFact(rest).text`. The merged timeline is unchanged.
5. **LiveFeed (Overview):** each source card shows the 3 newest items. If there are more, add a
   "Show N more" button that toggles the rest. Counts line and the status dot are unchanged.

## Acceptance checks (all must pass, runnable as written)
- [ ] `node --test scripts/tests/fact-format.test.mjs` → all pass. It must cover: every rule in step 1 using the exact
      strings from `baseline_scorer.py` (for example `'1 action kind(s) never seen in the last 28 days: ListObjects'`,
      `'35 events today; median active day is 4 (8.8x)'`, `'100% of today\'s events fall outside this account\'s usual hours (MYT)'`),
      an unknown string passes through verbatim, and `sourceTag` with and without a prefix.
- [ ] `node --test scripts/tests/diagnostic-privacy.test.mjs` → still passes.
- [ ] `$env:DATABASE_URL="sqlite-local"; & C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest workspace_next scripts/tests -q -x --ignore=scripts/tests/test_live_eval_report.py`
      → no new failures compared with a run on an untouched checkout of 097a472. Report both counts.
- [ ] `git diff --stat` lists only the files in scope.
- [ ] **Build check (isolated, not live):** create `C:\Users\yyzhe\argus-worktrees\ui-declutter-site\frontend` by copying
      `C:\Users\yyzhe\argus-worktrees\l1-live-baseline\data\live\live-v1-preview\frontend` **without** `.next`
      (robocopy `/XD .next`; `node_modules` included), overlay this worktree's `workspace_next/frontend/{pages,components,lib}`,
      then run `next build` there with `$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8019"`
      (`node node_modules/next/dist/bin/next build`). The build must succeed. Do NOT start any server.

## Risk notes
- **Evaluation window:** 22 Nov is the last evaluation day. Nothing in this task may touch the live site, the collector,
  `preview.db`, `events.db` or the scheduled tasks. The planner starts the isolated preview (API 8019 / UI 3015 on a
  copied database) after the build.
- **Privacy:** `display()` / `maskEmail()` must still wrap every account label and fact string. Do not print or commit
  account IDs, emails, IPs or tokens.
- **Frozen strings:** if a fact string doesn't match a rule, show it verbatim. Never edit backend text to make a rule match.
- **Windows/OneDrive:** work only under `C:\Users\yyzhe\argus-worktrees\`.

## Escalation triggers
Stop and report instead of pushing on if: the build needs `npm install` or a new package; any check needs a backend
or API change; the pytest baseline itself fails differently from the known failures (L7b spec, date-dependent,
Cloudflare provisioning); or a component's data shape differs from what this spec assumes.
