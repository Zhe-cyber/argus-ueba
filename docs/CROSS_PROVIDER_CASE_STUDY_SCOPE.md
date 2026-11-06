# Cross-provider identity-correlation case study

29 October 2026. Scope proposal and read-only preflight, following Claude's review. This does not amend the frozen AWS study, provision identities, approve mappings or claim a new feature is implemented.

## Claims

1. Working multi-source ingestion: AWS CloudTrail, Cloudflare Access and GitHub repository Events API. Normalised records preserve available source context; unavailable fields remain missing and source completeness is not guaranteed.
2. Proposed single-owner identity correlation: evidence-backed approved mapping and chronological activity report, with provenance/missingness retained. This is the achievable cross-provider demonstration, pending implementation and verification.
3. Validated multi-cloud detection: not established. One owner and partly induced history cannot establish general detection rates, superiority over per-source methods or a fused cross-provider risk score.

## Read-only findings

- The shipped AWS live template includes account-wide management events and console sign-ins, excludes KMS/rdsdata event sources, and separately adds toy S3 data reads. Its EventBridge pattern does not restrict to persona identities. This is template evidence, not verification of the currently deployed configuration.
- Stored events include root and program/workload principals. The non-root inventory found collector/tool identities, the actor runner and an Argus assumed-role identity; no dedicated human identity has been verified.
- The user confirmed they still use root. Root, machine collectors and six synthetic roles will not be approved as the owner's personal AWS identity.
- The collector's non-root credentials could authenticate, but the deployed-stack inspection returned AccessDenied. The existing setup CLI session also failed its read-only STS check and needs local reauthentication. No privileges were expanded to work around this.
- All 2,683 AWS rows in the inspected snapshot retained metadata.eventSource, which can support future service-specific descriptive/novelty evidence. This is field availability, not validation of a new signal.

## Personal AWS identity prerequisite

Use a dedicated non-root human identity, separate from collector/actor credentials. AWS recommends federation/temporary credentials for human access. Inspect IAM Identity Center availability before selecting setup; do not silently create an organization or broad administrator permissions.

If a narrowly scoped IAM pilot user is selected for the single-account demonstration, keep its policy separate: only approved read-only actions and explicit self-authentication/MFA management as needed, with browser-based CLI temporary sessions rather than new long-lived access keys. Prepare the exact policy before provisioning. The user completes passwords/MFA locally, never in chat.

After configuration, verify its exact principal and one native receipt before proposing a mapping. Reusing account ownership as evidence does not turn collector automation into the owner's genuine personal behavior. Label tool-assisted/induced actions.

## Minimum read-only implementation

- Separate versioned mapping records: person pseudonym, provider namespace, exact native identity/key basis, evidence references, approving actor/time and validity interval. Initial records pending approval join nothing. No inferred links from names. Never rewrite source events.
- For AWS IAM users prefer stable native principal ID plus account namespace; an ARN/name alone can be reused after deletion/recreation. Federated/shared roles need stronger per-person/session attribution; do not link every session of a shared role to one person.
- Timeline report applies approved links at read time, preserves provider/native IDs and explains missing fields. Public sharing requires keyed aliases/redaction; private mappings contain identity evidence and remain local.
- Fixed prospective separate source signals only if histories qualify: Cloudflare IP/country novelty and personal-AWS action/service novelty. Specify history window, minimum active dates/event counts, canonicalization, baseline cutoff, missingness and exclusions BEFORE any controlled case. No fused score. GitHub is descriptive repository activity.
- Cloudflare sign-ins induced for collection are owner's controlled lab activity, not independent ordinary users. Single-owner/short-history limitations remain explicit. Insufficient history stays unknown.
- Optional controlled correlation demonstration on 14 November: preregister owner actions/network change only after verifying input isolation. Novelty is not guaranteed: a console visit may call familiar APIs. A shared timeline does not imply a causal chain or compromise.
- Verify the existing normal-study exporter selects only planned persona receipts; still confirm exact isolation before scheduling owner actions during frozen windows. Do not reuse persona roles as the owner's identity.

## Sequence

Protect manual commit and frozen AWS evaluation first. Verify personal identity and actual collection scope, then implement mapping validation and standalone read-only timeline before 15 November. Freeze any source rules/case before use. Integrate the frozen report into the dashboard during 16–24 November only after review. Broader validated multi-cloud detection needs a separate future protocol and representative linked identities/history.

No new AWS user, permission, provider call workload, mapping approval, collector change, rule, live scoring or timeline deployment occurred during this preflight.

Official setup references:
- https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html
- https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html
