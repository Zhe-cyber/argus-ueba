# Local collector status in the source cards

30 October 2026. Read-only operational information, separate from model scores,
observed-event totals and proof of complete provider coverage.

The source cards show Collector and Workload checks from sanitized native job
receipts. A recent poll can coexist with missed or unresolved workload actions.
Pending receipts are not provider verification. An observed event count alone
does not make a check recent or successful.

Statuses: Recent check, Needs review, Stale check, No status, Ended. Unknown
write claims and pending identity verification require review. Counts preserve
missed and pending outcomes across the ledger's recorded scope; they are not
labelled as today's counts or independent users. Hover shows the receipt's
check time. A stale receipt keeps its unresolved/missed counts visible.

Data comes from the existing local/AWS tick (collector phases and actor status)
and separate Cloudflare/GitHub machine-pilot status files. The backend's owned
local-pilot launcher explicitly opts in with fixed receipt directories. Other
deployments/tests default to no local status context; they do not search this
laptop's files. No request can supply a filesystem path. Reads are bounded to
64 KiB, and only known statuses, validated counts and normalized timestamps are
returned. No token, account ID, raw error, path or native payload is exposed.

Local/AWS and Cloudflare heartbeat grace is 15 minutes; GitHub's is 35 minutes
for its 15-minute task. These are UI staleness conventions, not event-completeness
guarantees or proof that a Windows task is currently enabled. A failed/missing
provider phase cannot inherit a successful outer tick's status.

The original backend/collection tasks and both machine tasks were paused for
the reviewed release, configurations backed up, exact changed source pins
checked, backend identity verified and all affected jobs resumed. AWS workload
definitions, study dates and ledgers were not changed. No W33 artifact or model
was touched. Frontend was built against port 8013 and restarted hidden.

Validation: 218 backend tests passed for the status feature, followed by 32
targeted checks after explicit runtime opt-in/test-isolation hardening. The
production build passed (the repository build skips separate lint/type checks).
Headless analyst-workspace verification passed with mutations blocked. Live
event counts can change during a browser check; the check now proves no browser
mutations rather than assuming background collectors cannot update the store.
