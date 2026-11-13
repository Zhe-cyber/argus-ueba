# Background GitHub/Cloudflare workload extension: preflight

30 October 2026. User requested background persona activity on both sources.
This is implementation preparation, not a claim that workloads are scheduled.
No resource, credential, policy or pilot source pin has been changed.

## Current hosting

AWS CloudTrail/S3/SQS, GitHub repository hosting and the Cloudflare Access test
Worker are real hosted services. Argus frontend, backend, collectors, SQLite
stores, scheduler and local inference run on the laptop. The dashboard is
loopback-only, not an Internet deployment. CLUE replay serves precomputed model
outputs. There is no approved model configured for live account risk scoring.

## Verified preflight

- Cloudflare saved credentials can read service-token inventory (zero tokens)
  and existing test-app policies (one human Allow policy). Read access does not
  establish permission to create tokens or prove successful machine access.
- GitHub CLI can read the existing public project repository and reports owner
  admin/push permissions. No project commits or events were generated.
- Original AWS profile explicitly disables automated Cloudflare/GitHub actions.
  Leave that profile, ledger, reserved study, source pins and dates unchanged.
- Current Cloudflare collector requires a nonempty `user_email`. Normalization
  and native account attribution retain human `user_id` only. Service tokens
  cannot simply be switched on and represented as human login accounts.
- Existing Worker deliberately requires the approved human email. Do not loosen
  that check to admit machines; use a separate protected machine-only target.

## Proposed minimal implementation after identity choice

Use a separate versioned workload contract, ledger and scheduled task, 08:00–20:00
Asia/Kuala_Lumpur. Same stop dates as the current pilot: action generation ends
13 November; 14 November reconciliation only. No backfill, no timestamp edits,
no replay of missed actions. Deterministic varied per-profile times, capped
small daily calls, durable claim-before-call and provider receipt verification.
Stop on unknown outcomes; do not regenerate actions to fill count targets.

GitHub: a dedicated private toy repository and preferably a GitHub App/bot with
repository-scoped Contents read/write. Generate bounded toy-file commits under
six workload profiles. Six profiles/branches are still **one native bot account**,
not six GitHub users. An existing personal credential would instead generate
events under that person's real native ID; fake author names cannot change
that identity. Identity choice is pending the user's reply. Existing project
commits remain a separate human-controlled workflow. No issues/comments/PR
messages or collaborator invitations are needed. A separate collector must
actually monitor the toy repository; the current project-only poller will not.

Cloudflare: six separately named, expiring service tokens restricted by a
Service Auth policy on a separate toy app. Never automate email OTP/MFA or store
human login sessions. Store one-time service secrets encrypted with current-user
DPAPI, never in Git, command lines, prompts, logs or public outputs. Verify
unauthenticated denial and one successful authenticated request before any
schedule. Preserve actual Access service identity, native request/time and
allowed outcome in a separately tested ingestion extension. Missing native
machine identity remains unattributed, never an invented email/user ID.

Prove one provider-generated event round-trip from each source before installing
the new background task. Correlate by native receipts, not a forged native ID.
Require tests for duplicate delivery, missed/unknown claims, request caps,
expiry, machine/human identity separation and no accidental score activation.
Any running backend change requires the existing pin/restart/health procedure.

## Evidence boundary

This extension supplies **controlled machine-workload integration evidence**.
It is not an expanded independent human population, a cross-provider attack
dataset or a remedy for the failed CLUE detector. All profiles originate on
one laptop/network. Resource/action diversity may remain small. Keep genuine
owner activity and the frozen AWS study separate. No automatic person mappings,
new model training, threshold calibration or High/Medium/Low activation.

Official references: [Cloudflare service tokens](https://developers.cloudflare.com/cloudflare-one/access-controls/service-credentials/service-tokens/)
and [GitHub activity Events API](https://docs.github.com/en/rest/activity/events).
