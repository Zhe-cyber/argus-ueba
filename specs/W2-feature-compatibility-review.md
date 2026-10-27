# W2: Cloud feature compatibility review

27 October 2026. Stacked on PR #13. Review source observability and the frozen
12-feature implementation against AWS, Cloudflare Access, GitHub Events and
the inspected CLUE schema. Produce an evidence-backed model/data decision and
an implementation-ready follow-up contract, not a silent semantic change.

Use offline counterexamples and bounded existing public samples; never send
fixtures to live ingestion. Document metadata errors, resource granularity,
unavailable IPs, action naming, pseudonymised sensitivity, UTC-day/history and
partial-day limits. Preserve both frozen model contracts and checkpoint files.
Only review tools, isolated diagnostic tests and documentation may change.

Acceptance: repeatable feature probes; explicit supported/unsupported source
matrix; separation of missing telemetry from observed zero; a clear data/model
path and gates before retraining. No cloud changes, model training, activation,
provider identity inference or new production normalizer in this task. Run tests
with sqlite-local and open a draft PR; human merge and independent review remain.
