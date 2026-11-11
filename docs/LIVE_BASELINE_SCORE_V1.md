# Live baseline risk score v1.1 (method note)

A transparent 0-100 score per **(account, Malaysia calendar day)** on AWS, GitHub and Cloudflare,
computed from that account's own previous 28 days. Code: `workspace_next/baseline_score.py`.

## Method
- Day = MYT (UTC+08:00). Events without an `account_key` are ignored.
- History = the account's earlier active days inside the 28 calendar days before the scored day.
  Fewer than 5 such days: no score, tier **Learning** ("n of 5 days of history").

| Signal | Weight | Definition (today vs history) |
|---|---|---|
| `new_action` | 0.25 | distinct `(source, action)` not in history: 0 -> 0, 1 -> 0.6, 2+ -> 1.0; x (1 - rho_action) |
| `new_resource` | 0.25 | same rule over distinct non-empty resources, x (1 - rho_resource); **unavailable** if none today |
| `unusual_hours` | 0.20 | usual hours = every MYT hour within +-1 h (circular, 23 <-> 0) of an hour holding >= 5% of history events; signal = min(1, share outside / 0.5) |
| `volume` | 0.15 | r = events today / median daily count; clip(log2(r)/3, 0, 1) (8x -> 1, drops -> 0) |
| `sensitive_new` | 0.15 | 1 if a resource today is new and matches `rarity_scorer.SENSITIVE_PATTERNS`; x (1 - rho_resource) |

**Novelty rate rho** (separately for actions and resources): over the history active days from the 4th
onward (chronological, each compared with all earlier history days), the share on which the account
introduced at least one item not seen before. Fewer than 2 such days: rho = 0. When rho >= 0.25 and a
novelty signal was non-zero, a fact says novelty is discounted. rho_action / rho_resource are returned by the API.

**Score** = round(100 x sum(w*s) / sum(w) over available signals). **Tier:** >= 60 High, 30-59 Medium, < 30 Low.
Weights and cut-offs are fixed by the spec and were not tuned on observed data.
Facts are display-safe: 12-digit runs show as `<account>`, at most 3 names then `+N more`, names cut at
60 characters, request-parameter blobs show their first key only.

## Why v1.1 (change from v1)
A review of the normal days 1-10 Nov, before any test days existed, found two design defects: one
AWS-managed crawler role showed new actions or resources almost daily and produced 10 of 11 High
account-days, and `unusual_hours` fired at 75-100% for sparse accounts (about 4 events/day) because a single
hour rarely holds 5% of a thin history. v1.1 widens the usual window by one hour and discounts novelty by the
account's own novelty rate. Weights and tier cut-offs are unchanged.

## Workload groups (cross-cloud)
`workload-groups.json` is a *declared lab mapping, not identity proof*. Group score = highest member score,
+10 when two different sources each score >= 30 that day, capped at 100. The six lab personas pair the
AWS role `argus-ueba-actors-persona-0N` with the Cloudflare service token whose requests carry the
`/workloads/persona-0N/` path (the path `scripts/cloudflare_machine_pilot.py` calls); the shared lab GitHub bot is its own group.

## What it is not
Not trained, not validated against labelled incidents, not the V3 study method, and not the AE diagnostic
(which stays hidden). Recorded finding severity is unchanged and shown beside the score. The
`sensitive_new` patterns are loose substrings (e.g. `iam`, `sts`) imported unchanged from the rarity scorer.

## Sanity counts (preview copy, taken 10 Nov 2026; account-days per tier, 1-10 Nov MYT, v1.1)
| Source | High | Medium | Low | Learning |
|---|---|---|---|---|
| aws_cloudtrail | 1 | 4 | 86 | 12 |
| cloudflare_access | 0 | 0 | 31 | 27 |
| github_events | 0 | 0 | 6 | 5 |
| **Scored total** | 1 (0.8%) | 4 | 123 | - |

(v1 for comparison: 11 High / 10 Medium / 107 Low.) 26-31 Oct is entirely Learning.
Reproduce: `python -m workspace_next.baseline_score --db <copy> --report` (counts only).

## Baseline findings (L2)

Every account-day scored Medium or High becomes one finding (`origin = baseline`, `alert_type = baseline_risk`) in the
copy-only table `workspace_baseline_alerts` (ids shown as `1000000 + rowid`). A re-score updates score, tier and facts and
never changes an analyst's status. The only automatic status change: an Open row that no analyst touched and whose day falls
below Medium becomes Resolved ("score fell below Medium"); it reopens if the day rises to Medium again. High baseline
findings are triaged "Review first". Analysts disposition findings (rule or baseline) through
`POST /findings/{id}/status`, audited in `workspace_finding_audit`.

The live mirror (`python -m workspace_next.live_mirror`) adds new source events and alerts to the copy every 60 s, keeps the
study guard (nothing dated 14 Nov 2026 MYT or later before 16 Nov 2026 00:00 MYT), then re-syncs baseline findings.

## Monitoring infrastructure context (display only)

Accounts that are Argus's own monitoring or provider plumbing are labelled infrastructure and ranked below workloads. An account is infrastructure when its kind is `service` (provider service principals), its label starts with `AWSServiceRole`, or its label is listed in `system-accounts.json` beside the copy DB (declared: the collector's read-only identity and the lab runner). Such findings get the triage label `Context: monitoring infrastructure` instead of `Review first`, sort after workload findings, and are left out of the Overview top-5 (with a link to view them). Scores, tiers, weights and which account-days raise alerts are unchanged. Consecutive identical feed events (same account and action) are collapsed into one line with a count; per-source counters still count every event.

