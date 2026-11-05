# Dashboard walkthrough response — 4 November 2026

## Installed in preview 3011 / API 8015

- D1: refreshed the isolated copy at 20:18 MYT from a consistent read-only live database transaction. Appended 1,907 events and 21 findings. Connections now shows AWS 4,911, Cloudflare 29 and GitHub 83 stored events at capture. Its workload line reads Recorded day, not Today. Refresh snapshot still reloads a saved capture; no automatic refresh task or live case-writer switch has been installed.
- D2: shared presentation formatter now masks AWS role/user unique IDs, including session suffixes, in addition to account IDs, emails and IPv4 addresses. Presentation mode must be enabled for screenshots; normal analyst mode intentionally retains native evidence. This is visual masking only, not API/URL redaction. GitHub usernames are not automatically anonymised; use a reviewed screenshot or further aliasing before a public demo.
- D4: missing account labels show Account unavailable.
- D5: the rule window includes 15:00–03:00 next day MYT, with the original UTC weekday restriction explicit. Rule logic and severity are unchanged.
- D3 remains open: recorded High severity is not a model verdict. Existing categories and history context remain; no detector retuning or bulk regrouping was done.

## Preservation and validation

New scripts/refresh_workspace_copy.py appends only events and alerts. Every existing row must match exactly or the whole transaction rolls back. Case, audit, request-idempotency and identity tables are untouched. A SQLite backup is taken before every refresh. The destination must be explicitly marked as an isolated preview; source is opened read-only.

Real-copy rehearsal verified case and identity preservation plus backup restoration before the actual preview refresh. Rehearsal: data/live/dashboard-refresh-rehearsal-20261104/. Actual backup and refresh receipt are beside preview.db. Nine targeted tests passed, including conflict rollback, idempotence and backup restoration. Presentation masking checks passed. Production Next build succeeded. HTTP checks returned 200 for queue, entities, connections and the live collector. API check found no empty account labels and confirmed the MYT rule hint. A fresh interactive browser walkthrough is still requested; no new browser-console result is claimed.

No model activation, numeric score display, native record edits or pilot schedule changes. Remaining D1 work: durable scheduled refresh and/or controlled live workspace cutover before the competition. The current preview is a newly refreshed recorded copy, not a continuously live workspace.
