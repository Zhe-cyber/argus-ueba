# AWS CLI setup: author self-review

Date: 2026-10-27. Parent: PR #5 / 058ec94.
This is Codex author self-review, not an independent security assessment.

## Verification

- 99 backend/collector tests passed (six new setup safety tests).
- Wrong-account/region/name checks reject before resource mutations.
- AWS CloudFormation validate-template succeeded, then stack creation completed.
- Trail logging=true; EventBridge rule includes read-only management events.
- Encrypted queue, redrive policy and 120-second visibility inspected live.
- Non-root IAM collector identity verified by CLI and boto3.
- A genuine AWS API Call via CloudTrail event with native eventID was read from
  SQS as the collector user. No message was acknowledged or deleted.
- Existing root/default credentials were not repurposed for collection. A new key
  for the pre-existing restricted user was saved only in local AWS credentials;
  no key/secret appears in code, output screenshots or this report. Existing key
  and default profile preserved. Initial new-key rejection resolved after IAM
  propagation; retries then succeeded.

## Controls checked

S3 public access blocked, SSE-S3 enabled, TLS required; CloudTrail delivery policy
constrained by exact trail ARN and account log prefix. SQS service publishing is
limited to EventBridge from the exact rule/account. Collector gets access only to
the event queue plus DLQ attributes; its pre-existing CloudTrail read policy stays
unchanged. No public app endpoint or compute instance is deployed.

## Practical limits

The live delivery test proves the AWS collection backbone, not model quality,
dashboard ingestion, recovery under failure, or a sub-minute SLA. Regional scope
is us-east-1 plus applicable global-service events; S3 object data events are off.
No billing alarm was found. Credits are not a hard cap; configure an explicit
budget recipient before unattended collection. Audit objects expire after 30 days;
retained S3 bucket and DLQ require deliberate teardown.

The old consumer branch is not integrated: server-side idempotency remains a gate,
and its malformed-message deletion behavior needs correction before use. Cloudflare
account/Access/API readiness is still awaiting user information. GitHub activity
API is accessible; no webhook is installed without a verified receiver.

Keep this change draft for independent review. Infrastructure was deployed under
the user's explicit CLI setup authorization; neither application deployment nor
PR merging was performed. No new model benchmark numbers are claimed.
