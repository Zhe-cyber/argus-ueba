# Spec: L5-product-polish — make the workspace read as a product, not a prototype

**Branch:** `l1-live-baseline` (continue in `C:\Users\yyzhe\argus-worktrees\l1-live-baseline`, uncommitted) · **Executor:** executor (sonnet) · **Written:** 2026-11-11

## Goal
Every page of the workspace reads like a finished security product: no developer wording, no
"unavailable" placeholders, no mode toggle. Caveats stay true and reachable, but live in one
"Method & limits" page and in small info tooltips instead of on every screen.

## Non-goals
Frontend wording/layout only, plus the two small API items named below. No scoring, triage, data or
API-shape change. No `backend/` or frozen-file edits. No commit/push. Pilot checkouts read-only.
The rehearsal site must still be clearly marked as simulated (smaller, not removed).

## Files in scope
`workspace_next/frontend/components/*.js`, `workspace_next/frontend/pages/**/*.js`, new
`pages/about.js`, `pages/_app.js` or `_document.js` only if needed for page titles;
`workspace_next/finding_context.py` (display title text only). Mirror every changed tracked file
into both preview frontends (`data/live/live-v1-preview/frontend`, `data/live/live-v1-rehearsal/frontend`).

## Approach (planner-decided)
1. **Remove presentation mode.** Delete the toggle and its read-only state. Masking becomes
   permanent in the UI: email-shaped text renders as `[email hidden]`, any 12-digit run as
   `<account>`, everywhere (lists, selects, timelines, facts, dialogs). Action buttons always work.
   Clear any stored presentation flag on load so old browser state cannot disable buttons.
2. **Header.** Left: `Argus` wordmark + page title. Right: navigation. Under the title, one small
   status pill instead of the sentence:
   - `Live · updated Ns ago` (green) when `mirror-status.json` is younger than 5 minutes;
   - `Data as of <time> MYT` (grey) otherwise;
   - on the rehearsal site, an additional amber pill `Simulated scenario` (replaces the full-width
     bar; must be visible on every page, including in the top viewport).
   Remove "workspace preview · isolated data copy" and "live mirror of collected data (read-only source)".
3. **Browser tab titles:** `Argus — <page>` on every page (currently empty).
4. **Connections.** Replace "Operational snapshot: … Refresh reloads this snapshot. [Refresh snapshot]"
   with `Last checked <time> MYT` and a compact `Refresh` button; auto-refresh every 60 s.
   Rows with no data are hidden instead of saying "No status available" / "Time unavailable" /
   "Activity schedule unavailable" / "Daily workload history unavailable.".
5. **Wording** (apply everywhere the phrase occurs):
   | Now | Becomes |
   |---|---|
   | First-seen action outside the UTC rule window | New action outside business hours |
   | Baseline risk score v1 — compared with this account's own last 28 days. Heuristic; not a validated accuracy claim. | Risk score · compared with this account's last 28 days ⓘ |
   | recorded: High | rule severity: High |
   | Triage is display context only; recorded severity and detection are unchanged. | (removed from the line; in ⓘ) |
   | Context: automation or service account / inside Malaysian office hours / monitoring infrastructure | Automation account / Office hours / Monitoring infrastructure |
   | Declared lab mapping, not identity proof. Combined score = … | Combined risk across this workload's accounts ⓘ |
   | Observed activity only; completeness is unknown. | (in ⓘ) |
   | Mappings require recorded approval. An approved owner does not prove who performed an action. | (in ⓘ) |
   | Sources needing review at capture | Sources needing attention |
   | Learning (n of 5 days) | Learning · n of 5 days |
   | Unavailable (any stat card) | — |
   Any other sentence that explains internals to the analyst ("legacy signal", "retained finding
   snapshot", "Exact triggering events are not bound…", "at capture") gets the same treatment:
   shorten to product language and move the caveat into ⓘ. List every string you changed in the report.
6. **ⓘ tooltips.** A small accessible info control (button with `aria-label`, text shown on
   hover/focus/click; no library) carrying the original caveat text verbatim.
7. **Method & limits page** (`/about`, linked from a footer on every page: `Method & limits`):
   plain sections — how the risk score works (signals, weights, tiers, 28-day history, learning
   period), where data comes from, what "provider-confirmed" means, and a "Limits" list containing
   every caveat removed from the pages (heuristic not validated accuracy; lab workloads not people;
   workload mapping declared not identity proof; completeness unknown; rule severity unchanged by
   triage; autoencoder diagnostic hidden until evaluated). Content from `docs/LIVE_BASELINE_SCORE_V1.md`.
8. **Empty states.** "No active cases." → `No open cases` with a `Go to work queue` link; the
   Overview top-accounts box, when empty: `No account above Low today`.
9. Build both frontends (no npm install), restart 3013 and 3014 only (and 8017/8018 only if
   `finding_context.py` changed); keep the mirror loop running.

## Acceptance checks
- [ ] `$env:DATABASE_URL="sqlite-local"; C:\Users\yyzhe\OneDrive\Documents\fyp-ueba\.venv\Scripts\python.exe -m pytest backend/tests scripts/tests -q` → 0 failures (before: 1082 passed, 1 skipped). If a test pins a display string you changed in `finding_context.py` and the test lives under `scripts/` (not editable), keep that API string and change the wording in the frontend only.
- [ ] Browser DOM, every page on 3013 (Overview, Work queue, a finding dialog, Cases, a case, Entities ×3 tabs, Connections, About): none of these substrings appears: `Presentation mode`, `isolated data copy`, `workspace preview`, `Unavailable`, `unavailable`, `snapshot`, `UTC rule window`, `not a validated`, `legacy signal`; no email address; no 12-digit number; no "Application error"
- [ ] 3014: `Simulated scenario` pill present on every page; the old full-width bar is gone
- [ ] Finding actions and case create/close still work (buttons enabled) — exercise once on 3014, not on 3013
- [ ] Tab titles read `Argus — …`
- [ ] `git diff --stat origin/six-role-commissioning -- backend/ scripts/` → empty

## Risk notes
Caveats must not be deleted, only relocated: every removed sentence must appear in a tooltip or on
`/about`. Guard tab-switch renders in `entities.js`. Counts-only output; no secrets.

## Escalation triggers
Stop and report if removing a string requires changing API behaviour, or the same step fails twice.
