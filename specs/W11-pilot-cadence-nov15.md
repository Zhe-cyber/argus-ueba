# W11: prospective daily workload cadence and 15 November finalisation

Goal: apply the user's approved daily cadence before ordinary collection, retain
the original verified probe and global call budgets, stop actors after 13 November
and collect late receipts through 14 November. Final sign-off is 15 November.

Scope: versioned persona profile, plan/runner version binding, local pilot date
guards, explicit pre-collection ledger migration, owned Windows task expiry,
tests, protocol V2 and shared status notes.

Acceptance: V1 file hash unchanged; V2 differs only in version/provenance and
activity probabilities; all six roles planned daily; bounded SDK forecast;
migration rejects ordinary histories and preserves every action/run/receipt;
14 November only collects, 15 November performs no I/O; source pin/health checks
and local SQLite suite pass. Inspect actual task identity before updating its
expiry. Back up configuration, ledger and task XML before migration/restart.

Non-goals: no new IAM permissions, account creation, paid service, model training
or activation; no updates to frozen CLUE or CERT artifacts; no production writes.
Scenario execution remains a separate tested release before the freeze date.
Human merges draft PR. Claude review packet is sent manually by the user.
