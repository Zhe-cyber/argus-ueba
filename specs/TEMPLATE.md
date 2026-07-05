# Spec: W<N>-<slug> — <one-line title>

**Branch:** `w<N>-<slug>` · **Executor:** executor (sonnet) | heavy (opus) · **Written:** <date>

## Goal
<One paragraph. What exists after this task that doesn't exist now.>

## Non-goals
<What this task deliberately does NOT do — scope fence.>

## Files in scope
<Explicit list. Anything outside it needs a reported reason.>

## Approach (planner-decided)
<Numbered steps. Algorithmic/math decisions are made HERE, not by the executor.>

## Acceptance checks (all must pass, runnable as written)
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q` → 0 failures
- [ ] <task-specific command → expected output>
- [ ] <...>

## Risk notes
<What NOT to touch and why. Known traps from LESSONS.md that apply here.>

## Escalation triggers
<Conditions under which the executor must stop and report instead of pushing on.>
