# Dashboard P0 implementation — 30 October 2026

Source changes verified in an isolated frontend build. **Not deployed to the
running dashboard.** No backend, actor, normalization, scoring or stored record
changes were made for this increment.

## Delivered

- Replace the pulsing Live AE card and repeated unavailable live score panels
  with compact scoring readiness and the backend's actual reason. Preserve a
  supplied account score numerically; remove the unsupported percentage bar.
- Remove the empty SHAP fallback. Existing populated attribution panels remain;
  this does not implement or relabel them as reconstruction contributions.
- Default alert review to security findings; observations and unverified-origin
  signals have separate category selections. Status totals explicitly cover all
  signals. Navigation count has the same scope in its tooltip.
- Correct the post-escalation link label: it opens the account investigation,
  not a standalone case route that does not yet exist.
- Verified `backend/investigations.py` stores the literal Confirmed Insider
  status. Preserve that value and history; label it legacy in the investigation
  UI. Do not offer it for a new live decision. An existing legacy selection can
  remain unchanged when saving notes. Replacement dispositions require the new
  case API rather than a silent label substitution.
- Correct the plan's raw-MSE contribution definition and require supporting
  history/event evidence for behaviour facts.

## Verification

- Next.js production build passed in `data/live/workflow-p0-build/frontend`.
  The repository's build configuration skips lint/type validation; this was a
  production compilation check, not a claim that those checks ran.
- `scripts/tests/analyst-workspace-ui.mjs` passed against isolated port 3011:
  source overview, account identity, compact scoring, default security category,
  observation selection, escalation preview/cancel, investigations and demo
  redirect. Zero browser mutations and zero page errors.
- Isolated port is outside the live API CORS allowlist. The browser test served
  read-only API responses through its interceptor, without changing live CORS.
  It is not a new deployed origin or a public demonstration endpoint.
- Private browser receipt/screenshots: `data/live/workflow-p0-build/browser/`.

## Remaining

Category filtering still applies to at most the newest 100 fetched signals;
the UI explicitly states this. Server-side filtering, real case IDs, evidence
associations, edit protection and migration/rollback belong to the next increment,
built against a copy before the planned competition-runtime cutover. The current
readiness API is model-wide; do not invent per-account history counts.
