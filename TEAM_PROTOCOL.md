# TEAM_PROTOCOL.md — Multi-agent development system for Argus

*The full operating manual. CLAUDE.md carries only the always-loaded short rules;
this file is read when planning a work session or onboarding a new agent/session.*

---

## 1. The team

| Agent | Model | Role | Cost profile | Invoked how |
|---|---|---|---|---|
| **Planner/Orchestrator** | Fable 5 (or Opus when Fable unavailable) | Decompose workstreams into specs; algorithm & math design (AE loss changes, CUSUM, calibration statistics); arbitration when reviewers disagree | Most expensive — keep sessions short, plans written to disk so context can be dropped | You open a session and ask for planning |
| **Executor** | Sonnet | Implements one spec end-to-end: code + tests + branch + PR body | Cheap, fast — the default for ~80% of work | `/model sonnet` in a session, or `executor` agent (.claude/agents/executor.md) |
| **Heavy** | Opus | Escalation-only: task Sonnet failed twice, or high-blast-radius logic (scorers, identity resolution, auth) | Scarce on Pro — one task per invocation | `heavy` agent (.claude/agents/heavy.md) |
| **Scout** | Haiku | Fan-out searches, dependency tracing, "what would break if" reconnaissance | Nearly free | `scout` agent (.claude/agents/scout.md) |
| **Peer reviewer / security** | Codex (GPT — Go plan) | Independent review of every risky diff; security pass on auth/ingest; second-opinion implementation for isolated modules when quota allows | Limited Go-plan quota — spend per §4 | `scripts/codex_review.ps1` |
| **Researcher** | Sonnet + web tools | Outward product evaluation: competitor/SOTA/platform/dataset watch. One question per invocation → citable brief in `research/` | Cheap (web search is free; Sonnet synthesis) | `researcher` agent; questions live in research/QUESTIONS.md |
| **Evaluator** | Sonnet | Inward product evaluation: runs the benchmark suite, tracks metric deltas, keeps results/ ↔ paper ↔ slides consistent. Read-only on product code | Cheap–moderate (eval runs are compute, not tokens) | `evaluator` agent; summaries in research/eval-<date>.md |
| **Merge gate** | Human (you) | Merge PRs; approve destructive ops; own AWS credentials & supervisor comms | — | GitHub / terminal |

Division of labour rationale: cross-vendor review (Codex reviewing Claude-written code)
catches blind spots same-family review misses; Sonnet-by-default preserves the Pro quota;
the planner never types production code because plans survive on disk while context doesn't.

## 2. Session types (what to open, when)

- **Planning session (Fable/Opus, ≤30 min):** read UPGRADE_PLAN.md + LESSONS.md, pick next
  workstream slice, write/refresh `specs/W<N>-<slug>.md`, stop. No implementation.
- **Execution session (Sonnet):** open with the spec path as the first message.
  Executor implements, self-verifies (§5), pushes branch, opens PR, requests reviews.
- **Review round (mixed):** `/code-review` (Claude) + `codex_review.ps1` (Codex) on the PR
  diff. Findings go back to the executor session; CONFIRMED bugs block merge.
- **Retro (any cheap model, 10 min, after each merge):** append to LESSONS.md; tick
  UPGRADE_PLAN.md progress; update auto-memory if a durable decision was made.
- **Research round (researcher agent, before planning a workstream):** planner assigns
  the relevant open question from research/QUESTIONS.md; the brief lands before the spec
  is written. Precedent: the EventBridge finding (R2) rewrote W1 before a line was coded.
- **Evaluation round (evaluator agent):** mandatory after any merged scoring-path change
  and before any document that cites a number. Verdict format: IMPROVED / NO-CHANGE /
  REGRESSED + which paper/slide numbers must change.

## 3. Spec contract (the handoff artifact)

Every task crosses sessions as a file — never as chat history. `specs/TEMPLATE.md` defines:
Goal / Non-goals / Files in scope / Approach (planner-decided) / Acceptance checks
(runnable commands) / Risk notes (what NOT to touch) / Escalation triggers.

A spec must be executable by a fresh Sonnet session with zero conversation context.
If the executor needs to ask a question, the spec failed — route the question back to a
planning session and fix the spec, not the chat.

## 4. Codex quota policy (Go plan is limited — ranked spend)

1. **Always:** diffs touching `backend/ae_scorer.py`, `feature_extractor*`, `normalizer.py`,
   `event_store.py`, `main.py` ingest path — the scoring/data spine.
2. **Always:** W7 auth/tenancy code — full security review (`--security` flag of the script).
3. **When quota allows:** frontend and scripts diffs.
4. **Never:** docs, notebooks, paper edits (Claude `/code-review low` suffices).

If the CLI is not on PATH, `codex_review.ps1` writes a self-contained review packet to
`reviews/` for manual pasting into the Codex app; the PR waits for its verdict either way.
To enable automation: `npm i -g @openai/codex` then `codex login`.

## 5. Verification ladder (executor runs before opening any PR)

1. `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q` → 0 failures.
2. If scoring/feature code changed → `scripts/replay_eval.py` re-run; AUROC delta recorded in PR body.
3. If user-visible → `/verify` (preview tools) with screenshot in PR.
4. `/code-review` self-pass, fix CONFIRMED findings, then request Codex.

## 6. Automation (local-only, per decision)

- **Git pre-commit hook** (optional, `scripts/install_hooks.ps1` if adopted): pytest-fast + ruff.
  Free, runs always, no tokens.
- **`/loop`** during soak tests only (W1-B poller watching) — not for routine polling.
- **GitHub Actions:** the existing deploy.yml gains a pytest gate in W0 — that's CI, free tier,
  and it runs when the laptop is off even though we're not using cloud Claude agents.
- Nothing schedules Claude cloud runs (Pro budget decision). Revisit if plan upgrades.

## 7. Self-improvement loop (the system must get better, measurably)

- **LESSONS.md** is the team's long-term memory for *how to work on this repo*:
  every reviewer finding that reflects a pattern (not a typo) becomes a one-line rule.
  Executors read it first; planners prune it monthly (stale rules are deleted, not hoarded).
- **Metric:** count CONFIRMED review findings per PR (both reviewers). Target: trending down.
  Log the count in the retro line. If a rule in LESSONS.md would have prevented a finding,
  the retro says so — that's the signal the loop is working.
- **Auto-memory** (Claude's per-project memory) stores durable *decisions and user
  preferences*; LESSONS.md stores *repo craft*. Don't duplicate between them.
- **Escalation stats:** if Sonnet→Opus escalations exceed ~1 in 5 tasks, specs are too
  thin — fix at the planning layer, not by defaulting to Opus.
- **Full escalation ladder (human-approved 2026-07-04):** Sonnet (executor) → Opus
  (heavy, after 2 executor failures or scoring/auth code) → **Fable inline** (the
  orchestrator implements personally — last resort, smallest possible diff, only after
  heavy has failed or produced a regression it cannot explain). Each rung's failure
  report travels up with the task so no rung re-derives the diagnosis.

## 8. Guardrails

- No agent ever: commits to master, edits `.env`, touches Neon prod data, calls paid APIs,
  or pushes to the HF Space. Human-only.
- Fable/Opus planner sessions must end by writing state to disk (spec/plan/lessons) —
  assume the context is gone tomorrow.
- If Codex and Claude reviewers disagree, the planner arbitrates with evidence
  (failing test or trace), not authority.
