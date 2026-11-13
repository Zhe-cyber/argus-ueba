# AWS controlled study V3 — prospective amendment

Recorded 31 October 2026, before 1 November fitting activity. Implements the
user's decision in `reviews/AWS_STUDY_V3_DECISION_2026-10-31.md` and the review
conditions in `reviews/AWS_STUDY_V3_CODEX_REVIEW_2026-10-31.md`.

V2 failed its coverage gates. That failure, its original protocol, source bytes,
configuration snapshots and database snapshots are preserved separately. V3 does
not repair, backfill, relabel or restart the existing ledger.

## Calendar (Malaysia time, UTC+08:00)

| Step | V3 date / boundary |
|---|---|
| Fitting | 1–7 November 2026 inclusive |
| Validation | 8–9 November inclusive |
| Normal calibration | 10–12 November inclusive |
| Bound source commit deadline | Strictly before 10 November 00:00; human commit by 9 November |
| Model release / freeze | 13 November only, after every unchanged gate passes |
| Unannounced resource change | 14 November |
| Approved resource change | 15 November |
| Native receipt arrival cutoff | 15 November 20:00 |
| Earliest final evaluation | 16 November 00:00 |
| Last actor date | 15 November |
| AWS pilot service expiry | 17 November 00:00 |

The 8 November engineering rehearsal runs **only on copies of fitting data**,
with explicitly synthetic later partitions and isolated outputs. Real validation
collection continues unchanged. Its clock stubs exist only in the engineering
harness; production release and evaluation retain real-date guards.

## Unchanged method and collection

`LIVE_METHOD_ANNEX_V1.md` remains the mathematical method. Features, profiles,
generator, seeds, resource domain, planned action IDs, 15-minute action grace,
receipt matching, history gates, 90% coverage, 5% calibration budget, strict `>`,
call caps and no-uncertain-retry policy remain unchanged. No extra cloud action
is introduced. V3 export, bundle and release identities must reject V2 artifacts.

V2's ordinary runner and V3 prescribe identical ordinary actions on 1–7 November.
Pure saved-plan comparisons cover the full action rows, including IDs, timing,
operation and resource. Thus a delayed software cutover alone does not contaminate
those dates. Failed collection still makes a day unusable under the same gates.
The first planned 1 November action is 08:20 MYT, not midnight.

## Reserved slot availability, declared before collection

| Date | Target | Available planned GetObject substitution? |
|---|---|---|
| 14 November | persona-01 | Yes |
| 14 November | persona-02 | Yes |
| 15 November | persona-01 | **No: no planned GetObject** |
| 15 November | persona-02 | Yes |

For an available slot, change only the first planned GetObject's resource to
p06, retaining its ID and time. The unavailable slot receives no replacement.
Its ordinary actions continue; the evaluator reports the target slot as
unavailable, never as a negative. It must not block other roles on that date.
Only persona-02 has a complete change/control pair. These are descriptive
controlled-workload cases, not an estimate of human attack recall.

## Source binding and operational release

The authoritative exact list is the V3 `reserved_study.SOURCE_FILES` tuple,
published with its SHA256 values after staged implementation and validation.
The list must include the V3 calendar policy, method, generator, exporter,
trainer, guarded case runner/evaluator and this amendment. Runtime pins are a
separate set and may include additional backend/collector files.

Claude's C1/C2 modules, their tests, the CLUE live audit/explainer, W33 sources,
dashboard files and handover documents are **not AWS bound study sources**.
The `live_history_readiness.native_matches` interface and matching semantics
remain unchanged. Its source hash changes with V3 dates; new diagnostic receipts
must bind the new hash. Old diagnostic outputs stay untouched.

No implementation or installation is claimed by this protocol document alone.
The runtime transition requires staged tests, exact before/after pin hashes,
configuration backups, health verification and a rollback path. No automatic
commit, global power-setting change or live scoring activation is authorized.
