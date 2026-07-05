# FYP 2 Plan — Argus
**Yap Zhe Cheng · 23004982 · Supervisor: Dr. Firdaus Sahran · Partner: ECLOGIC Sdn Bhd**
*Decided after FYP 1 viva (panel: "very good project — pick ONE direction, don't fit everything"). Direction chosen: **real-life implementation**, with one small algorithm study as buffer.*

---

## 1. The Specialty (what differentiates Argus — don't just chase parity)

> **Glass-box behavioural account-threat detection for SMEs — delivered through their MSPs.**
> One engine catches both the **phished/hijacked account** and the **departing insider**, explains every alert in plain English (SHAP + multi-LLM copilot), and costs nothing to run.

**Why this framing (and not plain "insider-threat UEBA for SMEs"):**
- SMEs' #1 threat is **account takeover via phishing**, not classic insiders — but to the detector they are the *same signal*: a legitimate credential behaving abnormally. `new_ip`, `geo_rarity`, `off_hours`, `first_time_action` are literally compromised-account detectors. Nothing in the engine changes — only the claim. (Departing-employee data theft — the salesperson taking the client list — stays in scope; it's the one insider scenario SMEs genuinely suffer.)
- **SMEs don't buy security tools; their MSPs do.** The buyer persona is the managed-service provider running IT for dozens of small clients — i.e. exactly what ECLOGIC is. One MSP engineer monitoring 20 client tenants in one Argus dashboard is a real market motion. This puts **multi-tenancy back on-spine** (it's the MSP delivery requirement, not enterprise vanity).
- Structural moats — why commercial vendors can't follow: their business model forbids free, their IP forbids glass-box, their margins forbid SME-sized deals.

**Differentiation table (future slides):**

| | Splunk UBA / Exabeam | Wazuh / HELK | **Argus** |
|---|---|---|---|
| Detection | ML, black-box | Rules / DIY | ML, **glass-box** |
| Explanation | Opaque "risk reasons" | None | **SHAP + multi-LLM copilot** |
| Cost | RM500k+/yr | Free but heavy infra + expertise | **RM0, free-tier** |
| Deploy effort | Months, consultants | Weeks, specialists | **An afternoon, docker-compose** |
| Auditable | Never (IP) | Partially | **Fully — open benchmark + Demo Lab** |
| Built for | Enterprise SOC | Enthusiasts | **SMEs via their MSPs** |

One-liner: *"Commercial UEBA serves the 1% of companies with a SOC. Argus is glass-box account-threat detection for everyone else."*

---

## 2. Master Work Plan (all considerations combined: audit gap × specialty × cost × effort × risk)

### P0 — Week-1 starters (calendar-bound, near-zero effort)
| # | Item | Effort | Cost | Why now |
|---|---|---|---|---|
| 1 | **Repositioning language** — "insider threat" → "insider & account-compromise detection" across README/slides/paper | days | RM0 | Word-level edits, big positioning gain; everything after builds on this claim |
| 2 | **Signups + safety rails** — AWS account (+ **billing alarm at $1**), M365 Developer Program sandbox, send **ECLOGIC NDA request** | days | RM0 | All calendar-bound, not effort-bound; surprises must surface in week 1 |

### P1 — Core: production-gap fixes that ARE specialty requirements (weeks 1–9, all RM0)
| # | Item | Effort | Audit gap | Specialty link |
|---|---|---|---|---|
| 3 | **Label-free threshold calibration** (top-N daily alert budget / percentile; study: how close does it get to the F1-optimal 0.0662?) | 1 wk | #2 — deployed threshold needs labels | SMEs have **zero labels** — this is the SME requirement, not a workaround |
| 4 | **Learned active-hours profiles** (per-user hour-of-day histogram replaces hardcoded UTC 07–19 Mon–Fri) | 1 wk | #4 — timezone bug + FP class | SME staff (and SEA timezones) don't live in UTC |
| 5 | **Hygiene bundle** — retention purge job, per-user volume baselines, typed timestamps | 1 wk | #10 | Retention keeps **Neon free tier (0.5 GB)** viable once live pollers run — governance AND budget |
| 6 | **Identity resolution layer** — `alice` (AWS) = `alice@contoso.com` (Azure) = `alice-dev` (GitHub) → one entity (rule-based: email local-part + mapping table) | 2–3 wk | #1 — the biggest real-UEBA gap | An SME has no AD team to stitch identities manually; MSP sees one timeline per human |
| 7 | **Continuous re-scoring + baseline decay** (EWMA/rolling window, scheduled re-score) — finally implements the proposal's rolling-window claim honestly | 2 wk | #3 — frozen scores, no aging | Behaviour aging matters for high-turnover SMEs |
| 8 | **AWS CloudTrail live poller — the real way** (CloudTrail → S3 → SQS → Argus; `LookupEvents` polling as zero-setup fallback; pattern already proven by `github_live_ingest.py`) | 2 wk | — | The "connect in an afternoon" promise + the killer live demo (act in AWS console → alert in Argus seconds later) | Cost ~RM0–5/mo (S3 pennies, SQS free tier) |

### P2 — Specialty enablers (weeks 9–12)
| # | Item | Effort | Cost | Notes |
|---|---|---|---|---|
| 9 | **Auth + RBAC + analyst audit log** (NextAuth, analyst vs admin) | 1–1.5 wk | RM0 | Audit gap #5; **prerequisite for multi-tenancy** — can't have tenants without auth |
| 10 | **Multi-tenancy (MSP mode)** — tenant column + scoped queries + tenant switcher in dashboard | 1.5–2 wk | RM0 | Back on-spine: the MSP delivery requirement; demo = "one ECLOGIC engineer, N client orgs" |
| 11 | **Phished-account demo scenario** — same login, new country, new IP, 3 AM, first-time mass download → rarity flags light up | days | RM0 | Cheap, showcases geo_rarity/new_ip; the account-compromise claim made visible |
| 12 | **Azure AD live poller** (Graph API sign-in logs via M365 dev sandbox — E5 incl. Entra P2, required for the sign-in API) | 2 wk | RM0 (renewal friction) | Completes "multi-cloud live"; fallback: Azure free account $200 credit |

### P3 — Evaluation centerpiece (weeks 12–14)
| # | Item | Effort | Why it's the gem |
|---|---|---|---|
| 13 | **ECLOGIC triage-time user study** — 2–3 engineers triage alerts **with vs without** SHAP+LLM explanations; measure time + confidence | 1 wk + calendar | Directly tests the Inayat-gap claim; an *evaluation of explainability itself* — almost no FYP does this; uses the partner in a way no cohort-mate can; not model-accuracy-dependent |
| 14 | **Live-path engineering metrics** — events/sec throughput, p95 ingest latency, uptime; re-run `replay_eval.py` for live AUROC before/after | 1 wk | The implementation path's "results chapter" |

### P4 — Buffer / stretch (only if ahead of schedule)
| # | Item | Notes |
|---|---|---|
| 15 | **CUSUM / longitudinal Scenario-2 study** (secondary algorithm thread) | RM0, pure local compute, zero dependencies — the designated **buffer task** if anything external stalls; negative result still valid |
| 16 | **Queue backbone** (Kafka in local docker-compose demo, or Postgres-backed queue in prod) | Kafka won't fit HF free tier — don't let plumbing eat poller time |
| 17 | MITRE ATT&CK mapping, OCSF output | Enterprise-parity features — off-spine for the SME/MSP story; FYP 3/portfolio material |

---

## 3. 14-Week Timeline

| Weeks | Focus |
|---|---|
| 1 | P0: signups, billing alarm, NDA request, repositioning edits |
| 1–3 | P1 quick wins: label-free calibration (#3), active-hours (#4), hygiene (#5) |
| 4–9 | P1 core: identity resolution (#6), continuous re-scoring (#7), AWS live poller (#8) |
| 9–12 | P2: auth (#9) → multi-tenancy (#10), phished-account demo (#11), Azure poller (#12) |
| 12–13 | P3: ECLOGIC user study (#13) — system must be demo-ready by here |
| 14 | P3: engineering metrics (#14) + report writing |
| any | P4 buffer: CUSUM study slots in wherever an external dependency stalls |

**Milestone demo (monitoring session):** perform an action in a real AWS console → watch it appear in Argus, scored and explained, seconds later.

---

## 4. Budget & Risk

**Total cash cost: ≈ RM0–5/month.** HF free CPU + Vercel hobby + Neon free stay RM0. AWS S3+SQS effectively free at student volume — **set the $1 billing alarm on day 1**.

| Risk | Mitigation |
|---|---|
| ECLOGIC NDA/study timeline slips | Request in week 1; study is a bonus, not a dependency — system stands alone |
| AWS needs credit card / cost anxiety | Billing alarm + `LookupEvents` fallback needs nothing but an access key |
| M365 dev sandbox renewal tightened | Renewal needs visible dev activity; fallback = Azure free credit |
| Neon 0.5 GB fills from live pollers | Retention purge job (#5) is scheduled early on purpose |
| Transformer-style flat results | Doesn't apply — CUSUM study is the buffer, not the spine; no single technique can sink this plan |

---

## 5. Success Criteria (end of FYP 2)

1. Raw event performed in a **real** AWS/Azure account appears scored in Argus in < 60 s (live multi-cloud claim, demonstrated)
2. Thresholds calibrated **without labels**, within a measured gap of the label-optimal point (deployability claim, quantified)
3. One human = one entity across ≥ 2 cloud sources (identity resolution working)
4. ≥ 2 tenants viewable by one MSP analyst account, isolated by auth (MSP mode working)
5. User study result: explanations reduce triage time by a measured % (Inayat gap, tested with real engineers)
6. Everything still runs at ≈ RM0/month (the specialty's cost promise, kept)

---

*Origin: combined from (a) the production-reality audit — identity resolution, label-free calibration, frozen baselines, hardcoded off-hours, no auth; (b) cost/source analysis of free tiers; (c) the glass-box specialty thesis; (d) the SME→MSP buyer correction and insider→account-compromise threat reframe. The panel's advice — one direction, done deep — is the spine: implementation, with CUSUM as the only algorithm thread, used as buffer.*
