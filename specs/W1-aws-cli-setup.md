# W1: Reproducible AWS CLI setup

Date: 2026-10-27. Branch: codex/w1-aws-cli-setup, stacked on PR #5.
User explicitly authorized CLI setup. Temporary argus-setup login verified;
existing argus-readonly IAM user has CloudTrail read permissions. No existing trail,
Argus queue, rule or stack was found in us-east-1.

Goal: deploy a small, account-checked CloudFormation stack using AWS CLI: private
encrypted audit bucket, single-region management-event trail, EventBridge rule
including read-only events, SQS queue and DLQ, queue-specific IAM permission for
the existing collector user. No root access keys or secret values in output/git.

Approach: JSON template and stdlib Python CLI wrapper. Default is inspect/validate;
--deploy opts in to CloudFormation deployment. Require expected account ID and
us-east-1 to prevent accidentally configuring a different account/region. Reuse
existing IAM identity without changing its other policies or keys.

Acceptance: template validates; wrapper tests cover wrong-account/wrong-region
refusal before mutation; deployed trail logging and queue/rule policies inspected;
a real AWS management action reaches the queue. Receiving a test message is not
proof of dashboard detection or a <60-second latency SLA. Keep messages until a
duplicate-safe consumer and protected local backend are wired.

Non-goals: production app deployment, new compute instances/databases, IAM console
passwords, root access keys, automatic deletion, model feature changes. The
user's default profile remains unchanged. New audit objects expire after 30 days;
bucket and DLQ are retained on stack deletion. No public bucket/queue access.

Collector authentication: the existing user had one active key, but no matching
local credentials. A second key was created for that restricted user only and
saved to the local AWS shared credentials file under argus-collector. No key was
printed or committed; the existing user key and default profile were preserved.
IAM propagation briefly rejected the new key; a later retry verified its exact
non-root ARN and successful queue access. Temporary root login is setup-only.

Cost: one management trail, S3 storage/requests and SQS/EventBridge usage at student
volume. Credits are not a spending cap; no paid-plan upgrade or compute provisioned.
