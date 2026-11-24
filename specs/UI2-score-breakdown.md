# UI2 — score breakdown bar (presentation only)

**Goal:** show how the five baseline signals add up to the 0–100 score on every scored finding, so the glass-box claim is visible at a glance.

- Data: `signals` already returned by `/workspace/baseline` (stored per account-day by `backend/baseline_scorer.py` score_day). No backend change.
- `lib/factFormat.mjs` `scoreParts(signals, score)`: points = 100·w·v / Σw over available signals (same renormalisation as the scorer); whole-number parts by largest remainder so they sum to the STORED score; `floor` = the v1.2 sensitive minimum top-up (only when sensitive_new ≥ 0.5). Learning → null.
- `BaselinePanel.js` `ScoreBreakdown`: 0–100 bar, one colour per signal, lines + labels at Medium 30 / High 60, legend "+n" per signal.
- Weights are copied from the frozen v1.2 scorer (ponytail note in code).

**Checks:** `node --test scripts/tests/fact-format.test.mjs` (8 pass). All 224 non-Learning rows in the live preview.db: parts + floor == stored score (0 mismatches).
