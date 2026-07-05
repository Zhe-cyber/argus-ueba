# Argus — Team Operating Protocol (short rules; full detail in TEAM_PROTOCOL.md)

Argus: glass-box UEBA for SMEs (FYP2). FastAPI:8001 + Next.js:3000 + PyTorch AEs.
Roadmap: UPGRADE_PLAN.md (workstreams W0–W8). Strategy: FYP2_PLAN.md.

## Role routing (Pro-plan token discipline — strict)
- **Fable/Opus-planner session (expensive, rare):** planning, algorithm/math design,
  writing specs into `specs/`. Never bulk-edits code. Keep these sessions short.
- **Sonnet (default for ALL implementation):** run `/model sonnet` before executing a
  spec, or spawn the `executor` agent. Bulk code, tests, frontend, scripts.
- **Opus escalation:** only after Sonnet fails the same task twice, or for
  scoring/identity-resolution logic. Spawn `heavy` agent; one task, then back to Sonnet.
- **Haiku `scout` agent:** codebase searches / "where is X used" — never burn
  Sonnet/Opus context on fan-out searching.
- **Codex (peer reviewer, Go-plan quota — spend on):** every PR diff touching
  `backend/` scoring/ingest/auth; security pass after auth work. Invoke via
  `scripts/codex_review.ps1` (falls back to a handoff packet if CLI not on PATH).
- **Research team:** `researcher` agent (outward: competitors/SOTA/platforms —
  questions in research/QUESTIONS.md) and `evaluator` agent (inward: benchmark runs,
  metric deltas, results/↔paper consistency). Evaluator is mandatory after any
  scoring-path merge and before citing numbers in documents.

## Workflow (PR-gated — never commit to master)
1. Every task starts from a spec file in `specs/` (template: specs/TEMPLATE.md).
2. Work on a branch `w<N>-<slug>`; commit; `gh pr create`.
3. Before requesting merge: run pytest; run `/code-review`; run Codex review on the diff.
4. Only the human merges.

## Non-negotiable project rules
- AI features: Gemini/DeepSeek/Groq only — NEVER the Anthropic API in product code.
- The AE feature contracts are frozen (71-dim CERT, 12-dim cloud). Any change to
  feature semantics requires re-running `scripts/replay_eval.py` and updating results/.
- Two after-hours windows exist by design (07–18 AE frozen vs 07–19 rarity) — do not
  "fix" without reading rarity_scorer.py notes.
- `DATABASE_URL` in .env points at production Neon — tests must run with SQLite
  (`$env:DATABASE_URL="sqlite-local"`).
- Windows + OneDrive path: avoid long-path issues; use the venv at `.venv/`.

## Self-improvement (do this, don't skip)
- After every merged PR: append lessons (review findings, gotchas) to LESSONS.md.
- Read LESSONS.md before starting any spec; it overrides habit.
- Weekly: update UPGRADE_PLAN.md workstream status + auto-memory before the
  supervisor meeting (log: memory project_supervisor_meetings.md).
