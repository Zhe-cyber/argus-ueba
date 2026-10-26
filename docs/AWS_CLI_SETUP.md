# AWS CLI deployment and verified state

## Verified 27 October 2026 (Asia/Kuala_Lumpur)

- Stack `argus-ueba-live`: CREATE_COMPLETE in us-east-1.
- CloudTrail `argus-ueba-live-trail`: IsLogging=true, single-region management
  events plus global-service events. KMS and RDS Data API management events excluded.
- EventBridge `argus-ueba-live-management`:
  ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS. Account-scoped API and console
  sign-in event types route to the queue; delivery failures route to a DLQ.
- Private encrypted S3 audit bucket with 30-day object expiry. Bucket and DLQ
  retained on stack deletion; manual teardown must account for retained resources.
- SQS event queue: encryption enabled, 120-second visibility, three-day retention,
  20-second long polling and dead-letter routing after five unsuccessful receives.
  DLQ retention: 14 days.
- Existing IAM user `argus-readonly` kept its CloudTrail read policy and received
  a queue-specific inline policy. No queue-publishing or administrative permission
  was added. Its previous policy is unchanged, not retroactively narrowed.
- CLI profile `argus-collector` verified as that IAM user, not root. A new restricted
  user key is saved in the local AWS credentials file, never in this repository.
  The older key and default profile remain unchanged. Rotate/revoke the new key
  when the local collector is retired, or move to temporary workload credentials.
- One genuine CloudTrail `ListTargetsByRule` event was received as the collector
  user from the EventBridge queue. Its native event ID was present; no message was
  deleted. This verifies source-to-queue delivery, not dashboard detection accuracy.
- A real ListBuckets call was also issued; its individual arrival/latency was not
  established by the single queue peek. No sub-minute latency result is claimed.
- Existing billing alarms query returned none. Credits are not a spending cap;
  no new paid-plan upgrade, compute instance, RDS database or notification recipient
  was configured. Monitor usage while collecting; add a budget notification with
  an explicitly chosen recipient before unattended operation.

## Reproduce with AWS CLI

First complete `aws login --profile argus-setup --region us-east-1`. This profile
may have setup permissions; do not use it for the long-running collector.
Explicitly supply your intended account ID rather than deriving it blindly from
whichever account happens to be signed in.

```powershell
# Read-only identity and template validation first:
python scripts/setup_aws.py --account-id YOUR_12_DIGIT_ACCOUNT_ID

# Explicit provisioning/update, using the existing IAM collector user:
python scripts/setup_aws.py --account-id YOUR_12_DIGIT_ACCOUNT_ID --deploy

# Non-root identity verification:
aws sts get-caller-identity --profile argus-collector --region us-east-1

# Retrieve non-secret output values locally:
aws cloudformation describe-stacks --stack-name argus-ueba-live `
  --profile argus-setup --region us-east-1 --query 'Stacks[0].Outputs'
```

The script rejects mismatched accounts, unsupported regions and invalid stack
names before deployment. CloudFormation owns the resources, so rerunning deploy
does not create a fresh trail or queue. The script does not create credentials.

For boto3-based collectors, set `AWS_PROFILE=argus-collector` and the region to
us-east-1. Never copy credentials into .env, command-line arguments, screenshots,
chat, notebooks or git. Do not delete or replace the existing user's older key
without establishing who uses it. IAM key propagation can take time after creation.

## Coverage and wiring still required

Regional events outside us-east-1 are not covered by this initial single-region
trail/rule configuration. S3 GetObject/PutObject data events are not enabled.
This setup must not be described as complete multi-region or object-download coverage.

Do not drain the queue into the current endpoint until server-side idempotency and
the consumer are integrated and tested. SQS is at-least-once. A consumer must delete
only after durable ingestion; malformed events must be quarantined or allowed to
reach the DLQ, not silently discarded. The old W1-B1 spec's poison-message deletion
behavior must be corrected before that consumer ships.

Application authentication, model calibration, source/account identity scoping,
faithful live AE explanations and measured end-to-end detection remain separate
release gates. This stack does not deploy the application or open a public endpoint.

## GitHub and Cloudflare

GitHub CLI authentication is working and an actual repository activity event was
read. There are no repository webhooks. Configure a webhook only after a signed,
authenticated receiver exists; the Events API is activity telemetry, not the
organization security audit feed. Do not embed the CLI token in repository files.

Cloudflare has no configured local account ID/API token yet. Confirm whether a
Zero Trust Access application exists before implementing a login collector.
Access audit-log API credentials must be account-scoped and stored locally; a
Workers Wrangler login is not evidence of permission to read Access logs.

## Primary references

- https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html
- https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-service-event-cloudtrail-management.html
- https://docs.aws.amazon.com/awscloudtrail/latest/userguide/create-s3-bucket-policy-for-cloudtrail.html
- https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-events-rule.html
