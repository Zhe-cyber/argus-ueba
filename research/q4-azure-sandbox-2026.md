# Q4 — Azure AD (Entra ID) sign-in logs via Microsoft Graph API on the M365 dev sandbox: 2026 state

## Answer

The Microsoft 365 Developer Program's free E5 sandbox (the route UPGRADE_PLAN/FYP2_PLAN currently
name for W7/P2's Azure poller) is **still gated exactly as it was in 2024-2025**: as of Microsoft's
own FAQ (content dated 2025-10-01, last updated 2026-02-20), the only ways to qualify are (a) an
active Visual Studio Professional/Enterprise subscription, (b) membership in specific Microsoft
partner tiers (ISV Success / MAICPP), or (c) a Premier/Unified Support contract — a GitHub Student
Developer Pack alone does **not** qualify a student. So unless a team member personally already
holds a VS Pro/Enterprise subscription, this specific route is closed. However, the actual thing
W7 needs — Graph API access to `auditLogs/signIns` — does **not** require the dev-program sandbox
at all: it only requires a Microsoft Entra ID **P1 (or P2)** licensed tenant, and Microsoft offers a
genuinely free, self-service 30-day Entra ID P1/P2 trial (25 licenses, no existing paid subscription
required, sign up directly at a Microsoft trial-signup link) that creates a brand-new tenant on the
spot. That is the RM0-feasible route for W7 — not the dev-program sandbox, and not spending the
$200 Azure free-account credit (also viable but unnecessary since the license, not compute, is the
blocker). The poller is feasible at RM0, but on a tighter and more time-boxed clock (30-day trial,
manual renewal, some reuse friction) than the plan currently assumes, and its log latency (~5–15 min
typical, no published SLA) is materially slower than the AWS EventBridge <60 s bar already
established for W1-B (Q3), so it should not be held to the same "<60s live" success criterion.

## Evidence

- M365 Developer Program FAQ: qualification is limited to (1) active VS Professional/Enterprise
  subscribers (auto-qualify, auto-renew), (2) ISV Success/MAICPP partner tiers, (3) Premier/Unified
  Support customers — no open "any developer/student" path exists. Doc metadata shows
  `ms.date: 2025-10-01`, `updated_at: 2026-02-20` — i.e. this is the current, actively-maintained
  2026 policy, not stale 2024 info. [Microsoft 365 Developer Program FAQ](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq) (accessed 2026-07-11)
- Same FAQ: subscription is "good for up to 90 days depending on activity," renewed via an
  automated activity-detection algorithm (GitHub-account linking is one accepted signal); if
  ineligible for renewal you get a 30-day grace + 30-day admin-only window before deletion at day 60.
- GitHub Student Developer Pack gives Azure-for-Students credit ($100) and discounted tools, but
  multiple independent sources (Microsoft Q&A threads, 2025-2026) confirm it does **not** include a
  Visual Studio Professional/Enterprise subscription that would auto-qualify for the M365 dev
  sandbox — this is an "important 2026 update" repeatedly flagged in current Microsoft Q&A threads.
  [Microsoft Q&A: student options for MS developer account](https://learn.microsoft.com/en-us/answers/questions/5875942/best-student-options-for-getting-microsoft-develop) (2026)
- If the dev-program sandbox *is* obtained, it does bundle both **Microsoft Entra ID P1** and
  **Microsoft Entra ID P2** in its license list, which is more than sufficient for the sign-in API.
  [M365 Dev Program FAQ, "What's included" section](https://learn.microsoft.com/en-us/office/developer-program/microsoft-365-developer-program-faq)
- Independent of the dev program: `auditLogs/signIns` access requires an **Entra ID P1 (or P2)**
  license on the tenant — confirmed by both the Graph resource docs and community reports of the
  exact error ("Accessing sign-in reports requires a Microsoft Entra ID P1 or P2 license") returned
  without it. [Entra audit logs API overview](https://learn.microsoft.com/en-us/graph/api/resources/azure-ad-auditlog-overview?view=graph-rest-1.0) (doc dated 2024-12-30, updated 2025-12-20); [Microsoft Q&A — P1/P2 licenses needed for sign-in API](https://learn.microsoft.com/en-us/answers/questions/1256688/how-many-p1-or-p2-licenses-need-to-be-purchased-to)
- Retention: 7 days on Entra ID Free, **30 days with P1/P2** (including a trial P1/P2) — plenty
  for a semester-scale demo window. [Microsoft Entra data retention](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/reference-reports-data-retention)
- **Free P1/P2 trial route confirmed**: Microsoft's own sign-up docs (updated 2026-06-23) point to a
  self-service "Microsoft Entra ID P2 Trial" sign-up link (P2 trial includes P1 capability) as a
  distinct path from the Developer Program/EMS-license path; multiple secondary sources describe
  this as a 30-day, no-purchase-required trial that provisions a new tenant.
  [Sign up for premium editions](https://learn.microsoft.com/en-us/entra/fundamentals/get-started-premium) (updated 2026-06-23)
- Permissions: the app needs `AuditLog.Read.All` (application permission, admin consent) to call
  `GET /v1.0/auditLogs/signIns`; delegated/interactive callers additionally need a directory role
  such as Reports Reader/Security Reader. [List signIns — Graph v1.0](https://learn.microsoft.com/en-us/graph/api/signin-list?view=graph-rest-1.0); [AuditLog.Read.All permission reference](https://graphpermissions.merill.net/permission/AuditLog.Read.All)
- Rate limits (Graph service-specific throttling doc): sign-in/audit resources are capped at
  **5 requests/10 s per app per tenant** (122/10s per app across all tenants), and the related
  `signInActivity` field is separately capped at 10 requests/minute. This is comfortably enough
  for a low-frequency poller (well under what a per-minute polling loop needs).
  [Microsoft Graph throttling limits](https://learn.microsoft.com/en-us/graph/throttling-limits)
- Latency: no published SLA (Microsoft no longer publishes one for audit logs); practitioner
  reports on current Microsoft Q&A threads (2025-2026) converge on **roughly 5–15 minutes** typical
  for sign-in events to appear via the API, with occasional reports of much longer delays (hours)
  under load — i.e. materially slower and less predictable than the AWS CloudTrail→EventBridge
  "seconds to ~2 min" figure already logged for W1-B (Q3). [Microsoft Q&A — Graph API delay in signIn audit logs](https://learn.microsoft.com/en-us/answers/questions/5777289/microsoft-graph-api-delay-in-signin-audit-logs); [Microsoft Q&A — Sign-in log API latency](https://learn.microsoft.com/en-us/answers/questions/1688846/microsoft-entra-id-sign-in-log-api-latency)

## Impact on Argus (UPGRADE_PLAN / FYP2_PLAN #12)

- **FYP2_PLAN.md line 56** currently reads "Azure AD live poller (Graph API sign-in logs via M365
  dev sandbox — E5 incl. Entra P2, required for the sign-in API) | 2 wk | RM0 (renewal friction) |
  fallback: Azure free account $200 credit." This should be corrected: the primary blocker isn't
  renewal friction on a sandbox we can get — it's that the sandbox itself is very likely
  unobtainable for this team (no VS Pro/Enterprise subscription, no partner status) as of the
  current, actively-maintained 2026 policy. The credit-based fallback is also not quite right: the
  $200 Azure credit buys compute/storage, not the missing license; a standalone Entra ID P1 license
  is ~$6/user/month if paid, but a **free 30-day self-serve Entra ID P1/P2 trial tenant** achieves
  the same access at RM0 without needing the credit at all.
- **Recommended route for W7 #12**: skip the M365 Developer Program entirely; provision a fresh
  Entra ID tenant via the self-service P1/P2 trial sign-up, register an app registration with
  `AuditLog.Read.All` (application permission + admin consent), and poll `GET
  /v1.0/auditLogs/signIns` on a 5–15 min-tolerant schedule. Budget the 2-week slot to fit inside one
  30-day trial window; do not assume automatic multi-month renewal the way the dev-program sandbox
  has (that auto-renews on detected dev activity — the trial does not have the same mechanism, and
  reuse of the trial by the same person/tenant/phone has anti-abuse limits, so treat it as a
  single-shot 30-day window, not an indefinitely renewable resource).
- **Latency claim discipline**: do not fold the Azure poller into the same "<60 s live" success
  criterion used for AWS (W1-B, Q3). Log Azure sign-ins as "near-real-time, ~5–15 min typical, no
  SLA" — a materially different and weaker latency claim that the paper/demo should state
  explicitly rather than imply parity with the AWS path.
- **Hedge recommendation**: given (a) the license/tenant risk is real and outside the team's
  control if VS-subscription/partner eligibility isn't already held, and (b) W7's 2-week slot is
  tight and sequenced behind auth/tenancy work, the plan should treat the Azure poller as a
  **stretch goal**, not a blocking gate for the "second/third live source" demo claim. GitHub
  (already supported, zero setup risk) plus AWS remains the safe, already-working multi-source
  story; Azure/Entra should be attempted in parallel once auth work frees capacity, with graceful
  degradation to "documented Graph API integration, demonstrated against a live trial tenant via
  Graph Explorer" if the full poller doesn't land before the trial window or the 12-week clock
  runs out.
- No change needed to the frozen 12-dim cloud feature contract — this is purely an ingestion/access
  question, not a feature-semantics question.

## Confidence: High on eligibility/licensing facts (multiple corroborating, dated-2025/2026 primary
Microsoft Learn sources plus community reports pointing the same direction); Medium on the exact
trial renewal/reuse friction (Microsoft doesn't publish precise anti-abuse thresholds, so "single
30-day window, plan conservatively" is the safe reading, not a hard confirmed rule) and on the
5–15 min latency figure (no SLA exists; this is a practitioner-report range, not a guaranteed
number — could be faster or slower per tenant/workload). What would change this: if a team member
already holds an active Visual Studio Professional/Enterprise subscription (trivially reopens the
dev-program route with a longer-lived, auto-renewing tenant), or if Microsoft changes the
Developer Program eligibility policy again before W7's slot (worth a quick re-check right before
starting #12, since this has already changed twice in 2024-2025).
