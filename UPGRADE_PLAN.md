# Argus Upgrade & Implementation Plan (FYP2 execution layer)

*Companion to [FYP2_PLAN.md](FYP2_PLAN.md). That document says WHAT and WHY; this one says HOW —
concrete engineering steps, research-verified technical choices, acceptance checks, and an
AI-teammate operating model (Claude Code skills / agents / MCP) for each workstream.*

---

## 0. Research findings that change decisions (verified 2026-07)

| # | Finding | Impact on plan |
|---|---------|----------------|
| R1 | **CloudTrail → S3 delivery averages ~5 min, no SLA.** The S3 write is the bottleneck; SQS notification fires only after the file lands. | The FYP2 plan's "real way" (CloudTrail → S3 → SQS) **cannot reliably hit the < 60 s success criterion.** Demote it to the audit/backfill path. |
| R2 | **EventBridge receives CloudTrail management events in near-real-time (seconds to ~2 min).** Pattern: `AWS API Call via CloudTrail` rule → SQS target. No S3 storage cost. | **New primary live path: EventBridge → SQS → Argus poller.** This is the < 60 s demo architecture. SQS free tier: 1M requests/mo. |
| R3 | **LookupEvents polling lags ~2–15 min** but needs zero setup beyond an access key. | Confirmed as week-1 fallback. Already implemented: `scripts/aws_live_ingest.py`. |
| R4 | **Backend test suite has drifted: 12–13 of 57 tests fail against the current API** (e.g. tests expect `value`, API returns `shap_value`), and `.github/workflows/deploy.yml` deploys without running tests. | New workstream W0 (credibility): fix tests, gate deploy on green. |
| R5 | **Confirmed train/serve skew:** live cloud scoring passed `history=None` → `new_action_count` was always 0 in production, though the model trained with it. ~~Plausibly explains part of the 0.976 → 0.917 live AUROC gap~~ **Correction (W2, 2026-07-04): it does NOT — 0.917 is the CERT-AE replay path, causally independent of this cloud-AE fix.** | **W2 DONE** (branch `w2-cloud-skew`, Codex APPROVE): serving now mirrors training's per-UTC-day window + cumulative history. Offline cloud k-fold unchanged by construction (0.723); live cloud scores shift as intended. The CERT live-replay gap (0.917 vs 0.976) remains open — candidates: streaming aggregation differences, partial-day windows at replay time. Worth a scout pass during W3. |
| R6 | MCP registry available in this environment has no AWS/Postgres/GitHub connectors (finance-oriented deployment). | Add community/official MCP servers manually via `claude mcp add` (see §3). |
| R10 | **`/ingest` is NOT idempotent** (scout finding in W1-A, confirmed by reading `main.py::ingest_event` + `event_store.py::insert_event`): plain `INSERT`, the `events` table has no eventID column and no unique constraint, and `normalizer.py` writes CloudTrail `eventID` into the metadata blob but never reads it back for dedup. Re-posting the same eventID double-counts it in the 24h rolling window, AE-scorer history, and `total_event_count`. W1-A fixed this **client-side** (poller checkpoint) — but that only protects the poller. | **BLOCKS W1-B.** SQS standard queues are **at-least-once delivery** — the EventBridge→SQS path WILL redeliver duplicates, and the client-side checkpoint does NOT cover a different client. W1-B's spec MUST include a **server-side** idempotency fix (upsert-by-eventID or a unique index on eventID + `INSERT OR IGNORE`). That edit is ingest-spine → `heavy` agent + mandatory Codex review, as its own sub-task before the SQS consumer ships. Do not build W1-B's consumer without it. |
| R9 | **Threshold calibration** (research/q5-threshold-calibration.md): percentile/alert-budget top-K% is BOTH the anomaly-detection literature's standard label-free baseline AND matches commercial UEBA practice (Exabeam, Sentinel ship tunable defaults, not EVT). No CERT insider-threat paper nor either vendor uses a principled label-free calibration. SPOT (Siffer KDD'17) is the "more principled but under-adopted" contrast; fit on POOLED scores, not per-user (data-hungry). Reject IsolationForest contamination param (Perini ICML'23 — not a solved problem); keep MAD modified-z (Iglewicz-Hoaglin '93) as per-user cold-start fallback only. | W4 primary method CONFIRMED = percentile/alert-budget (already scoped). Add SPOT as secondary study contrast if time permits. **Honest paper framing (do NOT overclaim):** "percentile is the standard label-free baseline and matches commercial practice; EVT/POT is more principled but under-adopted in this sub-field" — NOT "EVT is best practice and we chose the simple option." Cite Siffer'17, Perini'23, Iglewicz-Hoaglin'93. |
| R8 | **Competitor sweep July 2026** (research/q2-competitor-2026.md): Table 2 rows all hold — Wazuh 4.12–4.14 added dashboards, not per-user ML UEBA (community request #14446 still open); OpenUBA/HELK effectively dormant. BUT: (a) **Splunk standalone UBA hit end-of-sale 2025-12-12** (EOL 2027-01-31), folded into ES Premier — still enterprise-priced/black-box; (b) **Graylog Security** has a paid ML UEBA module (~US$1,550/mo, not in free tier). | Paper actions before submission: rename the "Splunk UBA / Exabeam" column label + add EOL footnote (staleness an examiner could flag); add one pre-emptive sentence on Graylog Security's paid-tier UEBA (favourable to Argus's cost positioning). Re-run this sweep before the viva (absence claim is Medium confidence). |
| R7 | **EventBridge/CloudTrail gotchas** (research/q3-eventbridge-latency.md): (a) a trail must exist and be enabled — the built-in 90-day Event History does NOT feed EventBridge; (b) rules exclude READ-ONLY management events by default — need `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` state, settable via CLI only; (c) global-service events (IAM/STS/console sign-in) emit ONLY in us-east-1. No controlled EventBridge latency benchmark exists — "seconds to ~2 min" is docs+anecdote. Free tiers (SQS 1M req/mo, EventBridge 14M/mo) are permanent, first trail copy free. | W1-B setup must: create a free trail; set the rule state via CLI; put the rule+queue in **us-east-1** (read-only + IAM/sign-in events are exactly the UEBA signals). Treat < 60 s as demo target, not SLA; evaluator runs a timed end-to-end test after W1-B lands and the measured number goes in the report. |

---

## 1. Workstreams (ordered; each has owner-loop, steps, acceptance)

### W0 — Credibility floor: tests + CI  *(week 1, ~½ day, RM0)*
The cheapest high-value fix in the repo.
1. Repair the 12 drifted assertions in `backend/tests/test_api.py` (field renames: `value` → `shap_value`, etc.).
2. Add a `pytest` job to `.github/workflows/deploy.yml`; deploy only on green.
3. Run tests with `DATABASE_URL` forced to SQLite in CI (no Neon dependency).
- **AI teammates:** main session fixes; then `/code-review` on the diff; `/verify` to run the suite.
- **Accept when:** `pytest backend/tests` = 0 failures locally and in CI; a red test blocks deploy.

### W1 — Live AWS path, staged  *(weeks 1–4, RM0–5/mo)*
1. **Stage A (done):** `scripts/aws_live_ingest.py` LookupEvents poller. Needs: AWS account, $1 billing alarm, read-only IAM user. Proves real-tenant ingestion in week 1.
2. **Stage B (primary demo path):** EventBridge rule (`AWS API Call via CloudTrail`, management events) → SQS queue → new `scripts/aws_eventbridge_ingest.py` (long-poll SQS, POST to `/ingest`). Target: console action visible in Argus **< 60 s**. **Per R7:** create a (free) trail first; set rule state `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS` via CLI so read-only events flow; deploy rule + queue in **us-east-1** to capture IAM/STS/sign-in activity; evaluator measures actual end-to-end latency once live.
3. **Stage C (optional backfill):** CloudTrail → S3 → SQS for historical completeness; reuse Stage B consumer.
4. Measure and record p50/p95 console-to-dashboard latency for the report (feeds P3 #14).
- **AI teammates:** `Plan` agent designs Stage B message flow; main session builds; `/verify` drives an end-to-end check; `/loop 5m` babysits the poller during soak tests.
- **Accept when:** IAM action performed in console appears scored+alerted in dashboard in < 60 s, demonstrated 3× consecutively.

### W2 — Fix train/serve skew + re-evaluate  *(week 2, ~2 days, RM0)*
1. In `_CloudAEScorer.score_user`: split fetched events into current window vs prior history; pass history to `aggregate_window` so `new_action_count` is live.
2. Re-run `scripts/replay_eval.py` and `scripts/cloud_kfold_inductive_eval.py`; compare live AUROC before/after.
3. Whatever the result, write it up honestly (improvement → new result; no change → documented negative).
- **AI teammates:** main session; `/code-review high` on the change (scoring code = highest blast radius); `Explore` agent to confirm no other caller depends on the old semantics.
- **Accept when:** replay eval re-run committed to `results/`, delta documented.

### W3 — Ingest performance restructuring  *(weeks 3–5, RM0)*
Current `/ingest` is O(full user history) per event (fetch ≤ 50k events, rebuild vector, forward pass) — will sabotage the P3 throughput metrics.
1. Maintain incremental per-user daily aggregates in a table (extend `live_scores` or add `user_daily_features`), updated per event in O(1).
2. Score from aggregates, not raw event replay; keep raw events for drill-down only.
3. Benchmark before/after: events/sec, p95 ingest latency (this *is* P3 #14's data).
- **AI teammates:** `Plan` agent first (schema + migration design); `/simplify` after implementation; `/code-review` before merge.
- **Accept when:** ingest latency flat w.r.t. user history size; benchmark table in `results/`.

### W4 — Label-free threshold calibration  *(weeks 3–4, RM0 — FYP2 #3)*
1. Implement top-N daily alert budget + percentile threshold options over `_live_risk_tier` (single point of change already prepared in `backend/main.py`).
2. Study: measured gap vs the label-optimal F1 threshold (0.0662) on CERT.
- **AI teammates:** main session; `evaluation_proofs.ipynb` pattern for the study; `/code-review` on scorer changes.
- **Accept when:** thresholds configurable without labels; gap-to-optimal quantified in a table for the report.

### W5 — Learned active-hours + hygiene  *(weeks 4–5, RM0 — FYP2 #4, #5)*
1. Per-user hour-of-day histogram replaces the two hardcoded UTC windows (07–18 AE / 07–19 rarity — documented discrepancy in `rarity_scorer.py`).
2. Retention purge job + per-user volume baselines + typed timestamps (keeps Neon under 0.5 GB once pollers run).
- **AI teammates:** main session; `/schedule` a nightly cloud routine is NOT needed — purge runs inside the backend on a scheduler (APScheduler) so it ships with the product.
- **Accept when:** off-hours flag driven by learned profile; DB size stable over a week of live polling.

### W6 — Identity resolution  *(weeks 5–8, RM0 — FYP2 #6, biggest real-UEBA gap)*
1. Rule-based first: email local-part match + explicit mapping table (`identity_map`).
2. Entity = resolved human; all queries/timelines keyed by entity, source accounts listed under it.
3. Demo: same person acts in AWS + GitHub → one merged timeline.
- **AI teammates:** `Plan` agent for schema impact analysis (touches event_store, loader, API, frontend); build in slices; `/code-review` per slice.
- **Accept when:** ≥ 2 sources merge to one entity end-to-end in the dashboard (FYP2 success criterion #3).

### W7 — Auth → multi-tenancy → phished-account demo  *(weeks 9–12 — FYP2 #9–#11)*
Sequence is forced: tenancy needs auth; demo needs tenancy polish.
1. NextAuth (credentials provider), analyst/admin roles, analyst audit log.
2. `tenant_id` column + scoped queries + tenant switcher.
3. Scripted phished-account scenario (same login, new country, new IP, 3 AM, first-time mass download) — exercises `geo_rarity`/`new_ip`/`off_hours` live.
- **AI teammates:** `/security-review` after auth lands (it exists in the skills list — use it exactly once auth code exists); `/verify` walks the login → tenant-switch → alert flow.
- **Accept when:** unauthenticated API access impossible; 2 tenants isolated; scenario fires expected flags (FYP2 criteria #4).

### W8 — Evaluation centerpiece  *(weeks 12–14 — FYP2 #13, #14)*
1. ECLOGIC triage study (with/without SHAP+LLM explanations; time + confidence).
2. Engineering metrics: throughput, p95 latency, uptime + live AUROC re-run (W1/W3 already produced most of this data).
- **AI teammates:** `docx` skill for consent forms/study protocol; `xlsx` for results analysis; `pptx` for the final demo deck.

---

## 2. AI-teammate operating model (how to run the loops)

**Note on the requested "Ponytail skill": no skill by that name exists in this environment.**
The available skill list is fixed (visible to the session); the closest real capabilities are mapped below.
If "Ponytail" refers to something specific you've seen elsewhere, `skill-creator` can build a custom
project skill with that name and behaviour.

| Role | Mechanism | When |
|---|---|---|
| **Builder** | Main Claude Code session (this one) | Every workstream; keeps repo context + memory |
| **Architect** | `Plan` agent (Agent tool) | Before W3 schema change and W6 identity layer — returns step plans without touching code |
| **Scout** | `Explore` agent | "Where is X used?" fan-out searches before refactors (used in W2) |
| **Reviewer** | `/code-review` skill (low for docs, high for scoring code) | Before every merge to master; `ultra` variant for the W6/W7 big diffs |
| **Verifier** | `/verify` + `run` skills | After each feature: drive the real app, confirm behaviour, screenshot proof |
| **Janitor** | `/simplify` skill | After W3 and W6 land, to strip refactor residue |
| **Security gate** | `/security-review` skill | Once after W7 auth code exists |
| **Soak-test babysitter** | `/loop 5m` (loop skill) | Watch live pollers/CI during W1 Stage B soak runs |
| **Nightly QA routine** | `/schedule` (scheduled cloud agent) | Nightly: run pytest + replay smoke, report regressions — set up after W0 gives it a green baseline |
| **Report writers** | `docx` / `pptx` / `pdf` / `xlsx` skills | W8 and all supervisor-facing documents (already used for the paper) |

**Cadence:** per feature → Builder implements → Verifier proves → Reviewer gates → commit.
Weekly → nightly-QA report + memory update before each supervisor meeting (log in
`project_supervisor_meetings.md`).

## 3. MCP / tooling suggestions

The registry in this environment has no relevant connectors (R6), so add manually where useful:

| Tool | Purpose | How |
|---|---|---|
| **GitHub MCP (official)** | PR/issue management from the session; useful once CI gates exist (W0) | `claude mcp add` — github.com/github/github-mcp-server |
| **Neon MCP** | Inspect/query the production Postgres from the session (W5 retention validation) | Neon's official MCP server |
| **AWS MCP servers (awslabs)** | CloudWatch/CloudTrail inspection during W1 Stage B debugging | github.com/awslabs/mcp — pick only the CloudTrail/CloudWatch ones; least-privilege IAM |
| `gh` CLI (already available) | Lighter alternative to GitHub MCP for W0 CI work | already installed |
| **Not recommended** | Kafka/queue MCPs, k8s tooling | Off-spine per FYP2 plan (P4 #16) |

Priority: none of these block any workstream — `gh` + `boto3` + `psql` cover 90%. Add Neon MCP first
if any; it saves the most round-trips during W5/W6 schema work.

## 4. Sequencing summary

```
Week 1      W0 tests+CI ──── W1-A LookupEvents live (account + alarm + IAM = user tasks)
Weeks 2–4   W2 skew fix → W1-B EventBridge <60s → W4 calibration
Weeks 3–5   W3 ingest restructure (overlaps W4) → W5 active-hours + hygiene
Weeks 5–8   W6 identity resolution
Weeks 9–12  W7 auth → tenancy → phished demo
Weeks 12–14 W8 ECLOGIC study + metrics + report
Buffer      CUSUM Scenario-2 study (unchanged from FYP2_PLAN)
```

Success criteria unchanged from FYP2_PLAN §5, with one amendment: criterion #1's "< 60 s"
is delivered by **EventBridge → SQS** (R2), not S3 → SQS as originally assumed.
