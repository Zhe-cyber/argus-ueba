# AWS setup runbook — crossing the gate to the live cloud path

*This is the human-only step (merge-gate owns credentials). ~15 min. Two tiers:
Tier 0 unblocks the W1-A poller demo; Tier 1 adds the <60 s EventBridge path (W1-B).
Research backing every non-obvious step: research/q3-eventbridge-latency.md (R7).*

---

## Tier 0 — minimum to run the live poller (W1-A). No trail needed.

The LookupEvents poller reads the **free 90-day Event History** that exists in every
AWS account. No S3, no SQS, no trail. You need three things:

### 1. Account + a $1 billing alarm (do this FIRST, before any key exists)
1. Create/using an AWS account.
2. Billing → **Billing preferences** → enable "Receive Free Tier alerts" + your email.
3. CloudWatch (in **us-east-1** — billing metrics only live there) → Alarms → Create:
   - Metric: Billing → Total Estimated Charge → USD
   - Condition: **Greater than 1 USD** → notify your email (create an SNS topic, confirm
     the subscription email).
   - This is your blast-radius cap. Everything below stays inside the always-free tier.

### 2. A dedicated read-only IAM user (never use the root account for this)
1. IAM → Users → Create user `argus-readonly`. **No console access**, programmatic only.
2. Attach the managed policy **`AWSCloudTrail_ReadOnlyAccess`** (or an inline policy with
   just `cloudtrail:LookupEvents`). Nothing else — least privilege.
3. Create an access key → **Application running outside AWS** → save the key ID + secret.

### 3. Wire credentials locally (not into .env — that file holds the Neon prod URL)
```powershell
$env:AWS_ACCESS_KEY_ID     = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY = "..."
$env:AWS_DEFAULT_REGION    = "us-east-1"   # see note below on why us-east-1
```
Then, with the backend running (`uvicorn` on :8001):
```powershell
.venv\Scripts\python.exe scripts\aws_live_ingest.py --lookback-hours 6
```
Do something in the AWS console (create/delete an IAM user, list S3 buckets), wait
~2–15 min (LookupEvents lag — this is expected, not a bug), watch it appear in Argus.

> **Why us-east-1 (R7):** global-service events — IAM, STS, and console **sign-in** — are
> only recorded in us-east-1. Those are the exact account-compromise signals the thesis is
> about. Run the poller against us-east-1 (add a second region later if you have workloads
> elsewhere). A poller pointed only at ap-southeast-1 would silently miss every login.

---

## Tier 1 — the <60 s EventBridge path (only when you start W1-B)

This is the "console action visible in Argus in under a minute" demo. It needs a trail.

1. **Create a trail** (CloudTrail → Trails → Create). Event History does NOT feed
   EventBridge — a trail must exist and be enabled. First copy of management events per
   region is **free**; you can skip the S3 log-file delivery cost concern at our volume.
2. **Put the EventBridge rule + SQS queue in us-east-1** (same global-events reason).
3. **Enable read-only management events on the rule** — via **CLI only** (the console
   defaults to write-only, which drops all the `List*`/`Get*` reconnaissance signals):
   set the rule's managed state to `ENABLED_WITH_ALL_CLOUDTRAIL_MANAGEMENT_EVENTS`.
   (Exact command goes in the W1-B spec when we write it.)
4. Free tiers used here are **permanent, not 12-month**: SQS 1M requests/mo, EventBridge
   14M invocations/mo. At <1k events/day you are nowhere near either ceiling.

---

## What NOT to do
- Do not put AWS keys in `.env`, in git, or in any HF Space secret you share.
- Do not attach `AdministratorAccess` or any write policy to `argus-readonly`.
- Do not skip the billing alarm "to do it later." Do it before the key exists.
