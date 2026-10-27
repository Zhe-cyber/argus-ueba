# Controlled actor lab

This is a scripted, bounded AWS lab, not an unrestricted LLM swarm or six real
people. Six distinct role principals run neutral-named sessions against seven
private synthetic fixture buckets. Cloudflare and GitHub remain real connected
sources, but these actors do not impersonate six identities on those providers.
No new model is trained or activated by this lab.

## Review and provision

```powershell
python scripts/setup_simulation.py --account-id YOUR_ACCOUNT_ID
python scripts/run_simulation.py --account-id YOUR_ACCOUNT_ID
```

Both commands default to plans without cloud access, credential reads or writes.
The normal plan has 19 read operations and 28 API requests including STS/audit
checks. The transition plan has 38 read operations and 47 requests. Default budget
is 48 requests, maximum explicit budget 64, SDK automatic retries disabled.

With a temporary setup-only AWS login, provision explicitly:

```powershell
python scripts/setup_simulation.py --account-id YOUR_ACCOUNT_ID --deploy --configure-runner
```

The setup checks expected account and existing Argus stack ownership, validates
both templates, creates six restricted roles and seven private AES256-encrypted
buckets, and seeds only fixture.txt with known synthetic bytes. It enables S3
read data events only on those seven buckets while preserving management events.
It refuses to replace unrelated data-event coverage or foreign stack resources.
No compute service, public bucket, paid-plan upgrade or production data is created.
CloudTrail data-event logging and requests can incur usage charges; the bounded
lab is not a spending cap. Buckets expire fixture data after 30 days and are
retained on stack deletion to avoid unexpected data deletion.

The collector user is not broadened. A separate IAM bootstrap user can assume
only the six roles and read the named trail's status/selectors. Each role can
GetObject only on the seven exact fixture keys and GetBucketLocation only for
those buckets. Actors cannot write/delete, change IAM or logging, list the account,
or read other objects. Role credentials last 15 minutes and stay in memory.

Optional credential configuration saves a key for that bootstrap IAM user to the
standard local argus-simulator AWS profile; never root access keys. It reuses an
existing profile only after verifying its exact identity, and refuses to overwrite
another profile or create an extra user key. No keys appear in CloudFormation
resources/outputs, terminal output, process arguments, Git or experiment manifests.
The bootstrap IAM user is retained on stack deletion; key revocation/user cleanup
is an explicit operator task. Temporary setup login should be logged out afterward.

## Execute only the normal phase first

```powershell
python scripts/run_simulation.py --account-id YOUR_ACCOUNT_ID --execute
```

Runtime requires the exact non-root bootstrap identity and active, scoped audit
logging before assuming any role. It reads only allow-listed synthetic fixtures,
checks fixture metadata/size/content, and stops on failure. Private progress is
checkpointed under gitignored data/live/experiments/RUN/manifest.json, including
request IDs and stable lab principals, never credentials or downloaded contents.
An interrupted/failed manifest is not accepted as a completed normal baseline.

Normal actor 03 reads the synthetic confidential archive legitimately; actor 05
is a benign volume control. Persona 06 starts with its own normal routine. Later
its existing identity changes resource/action diversity. Names and API arguments
contain no attack/phase labels. Ground-truth phase/seed metadata stay in the
private manifest, outside event ingestion and model features. All provider audit
timestamps remain genuine; repeated short runs do not create weeks of history.

## Verify the actual log evidence

Restart the local backend after updating AWS normalization, which now preserves
the safe requestID/eventCategory/readOnly context. Collect SQS events using the
separate argus-collector profile, then audit the private manifest:

```powershell
python scripts/collect_live.py aws --account-id YOUR_ACCOUNT_ID --queue-url YOUR_QUEUE_URL --batches 5
python scripts/audit_simulation.py --manifest data/live/experiments/RUN/manifest.json
```

Audit compares each SDK request ID, principal, operation and bucket against real
native CloudTrail records in local connected SQLite. It writes a private audit.json
with matched native IDs and provider time range. Pending delivery is reported as
pending, not success. Do not overwrite/re-ingest old records or fabricate logs to
fill gaps. Queue acknowledgment follows the existing committed-receipt protocol.

Holdout/transition execution additionally requires the matching completed normal
manifest and complete audit, plus a frozen normal-only model manifest with exact
12-feature order, training-data digest and matching model/scaler hashes inside
ml/models. The new training pipeline must emit that manifest; the old benchmark
is not silently adopted. These local workflow checks are not tamper-proof evidence
or independent proof of training quality. Training/calibration history still needs
chronological separation and explicit evaluation as described in
CONTROLLED_EVALUATION.md.

Run `python -m pytest scripts/tests/test_simulation.py -q` for isolated safety and
evidence-correlation tests. No fake/native provider events are sent by those tests.
