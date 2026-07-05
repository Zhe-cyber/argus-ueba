# Spec: W0-tests-ci — Repair drifted test suite + gate deploys on green tests

**Branch:** `w0-tests-ci` · **Executor:** executor (sonnet) · **Written:** 2026-07-03

## Goal
`pytest backend/tests -q` passes with 0 failures locally, and the GitHub Actions
workflow runs the suite on every push/PR, blocking deploy on red.

## Non-goals
- No product-code behaviour changes. If a test fails because the API is *wrong* (not
  merely drifted), report it — do not "fix" the API in this task.
- No new tests, no coverage push, no lint setup. Repair + gate only.

## Files in scope
- backend/tests/test_api.py (primary — ~12 drifted assertions)
- backend/tests/test_normalizer.py (verify; likely fine)
- .github/workflows/deploy.yml (add test job)

## Approach (planner-decided)
1. Run the suite first to get the true failure list:
   `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q`
2. Known drift class: tests assert legacy field names (e.g. `value`) where the API now
   returns `shap_value`. The API response models in backend/models.py are the source of
   truth — update the TESTS to match the models, never the reverse.
3. For each failure: confirm against the live response model in backend/models.py,
   then fix the assertion. If any failure is NOT explainable as field-name/schema drift,
   stop and list it in the report (see escalation).
4. In .github/workflows/deploy.yml: add a `test` job (python 3.11+, install
   backend/requirements.txt + pytest + httpx, env `DATABASE_URL: "sqlite-local"`,
   run `python -m pytest backend/tests -q`); make the deploy job `needs: test`.
5. Do not modify deploy steps themselves.

## Acceptance checks (all must pass, runnable as written)
- [ ] `$env:DATABASE_URL="sqlite-local"; .venv\Scripts\python.exe -m pytest backend/tests -q` → `57 passed` (or current total, 0 failed)
- [ ] `git diff master --stat` touches ONLY the three in-scope files
- [ ] deploy.yml parses (YAML valid) and deploy job has `needs: test`
- [ ] PR opened via `gh pr create` with the pytest output in the body; if `gh` is not
      authenticated, push the branch and put the PR body text in the final report instead

## Risk notes
- LESSONS.md rules 1, 2, 6, 6b apply (SQLite env var, PS 5.1 quirks, ASCII-only ps1).
- `.env` holds the production Neon URL — never delete/edit it; only override the env var
  per-process.
- Some "errors" (vs failures) in past runs were remote-Postgres connection attempts —
  they disappear under sqlite-local; don't chase them.

## Escalation triggers
- Any test failure that implies a real product bug (not schema drift) → stop, report.
- More than 20 failing tests after env fix (would mean the drift diagnosis was wrong).
- deploy.yml uses a structure where adding `needs:` would break matrix/conditions.
