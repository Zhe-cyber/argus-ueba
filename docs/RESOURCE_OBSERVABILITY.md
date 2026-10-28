# Resource-aware model preparation

28 October 2026. This implements the resource-identity layer and audits existing
CLUE fitting data. It does **not** implement, select or evaluate a new detector.
The frozen AE and live application remain unchanged.

## Why this is necessary

The account-conditioned ten-count reference missed all 25 existing switched
development days. Its native-event counterexample showed that a resource change
can leave all ten numeric inputs identical. Before adding resource familiarity,
we must establish what resource identifiers mean and where they are missing.

`scripts/resource_observability.py` is a separate pure adapter. It hashes
structured, source-scoped tuples; the current actor is never inserted into a
resource identifier. Equal CLUE literal paths therefore remain comparable after
an account switch. Equality still does not prove that two relative namespaces
refer to the same underlying object, or establish access rights or ownership.

For raw AWS S3 records it requires `recipientAccountId`, S3 `eventSource` and
`requestParameters.bucketName`. Bucket and object keys are separate identities.
A missing key yields bucket-only coverage. Keys retain literal case, slashes
and encoding; the adapter does not guess URL-decoding semantics or canonicalize
object keys as filesystem paths. Source/account/bucket scopes prevent accidental
collisions. This is a versioned comparison convention, not proof that all
CloudTrail encodings of the same physical object will compare equal.

The existing AWS normalizer prefers the bucket name, while retaining the raw
event. The experiment can consequently extract richer S3 identity from raw
records without changing the frozen normalizer or claiming that historical
normalized resource strings already contain object keys. No live records were
read to produce this audit. Tests use synthetic S3 events.

Other providers are explicitly unsupported by this experimental adapter. This
does not remove their existing normalizers or ingestion. GitHub repository and
Cloudflare Access application semantics need separate contracts; a missing or
unsupported resource is coverage information, not a Low score.

## Fitting-only audit

`scripts/audit_clue_resources.py` checks the existing native-prefix and manifest
hashes, restricts aggregates to the frozen 55 identities and 13-26 July 2017,
and checks that the projection has 605 account-days. No later account activity
contributes to the counts below. The bounded existing prefix is streamed locally;
no new native data, downloads, provider calls, labels or switch cases are used.

| Observation | Fitting data |
|---|---:|
| Events across selected accounts | 834,907 |
| Events with a literal path | 664,034 |
| Events with missing/invalid path | 170,873 |
| Accounts with any observed path | 54 / 55 |
| Account-days with any observed path | 528 / 605 |
| Accounts with paths on at least five fitting dates | 49 / 55 |
| Distinct literal path tokens | 186,882 |
| Tokens appearing under multiple accounts | 1,347 |
| Events using those multi-account literal tokens | 124,261 |

Missing/invalid paths here include events where paths may not apply, such as
logins; this is not a measured log-loss rate. All observed strings have a leading
slash, but that alone does not establish their namespace or ownership. Distinct
paths per frozen account range from 0 to 157,563 (median 312), illustrating
uneven resource history, not evidence of malicious activity.

The five-date count is a coverage diagnostic, not a frozen new eligibility rule.
It warns that the 55-account count-model population cannot automatically become
a 55-account resource-model population. Report unavailable coverage explicitly.

## What this changes about the next experiment

Represent per-account resource and action familiarity separately from activity
volume. Keep globally unseen resources distinct from resources observed under
other accounts. Never assign ownership from frequency. Freeze the candidate
score, vocabulary/history policy, eligibility, calibration and reporting before
the next development comparison; use fitting-only reference state unless a new
causal update policy is explicitly versioned. Preserve all earlier misses.

The earlier raw novel-path fraction had a normal q99 of 1.0. This audit does
not justify reusing it with a changed inequality or lowering its threshold.
Resource representation is necessary for the proposed resource-substitution
scenarios, but it does not guarantee useful discrimination or attack detection.
It also cannot distinguish an approved change from an otherwise identical
unapproved action without external context.

## Reproduction and verification

```powershell
$env:DATABASE_URL = 'sqlite-local'
python -m pytest scripts/tests/test_resource_observability.py -q
python scripts/audit_clue_resources.py --prefix EXISTING_NATIVE_PREFIX --manifest FROZEN_MANIFEST --out data/processed/NEW_RESOURCE_AUDIT.json
```

The corrected private artifact is
`data/processed/clue-resource-fitting-audit-v1-corrected.json`. The first audit
artifact is retained but superseded: a missing-path test caught a defaultdict
lookup inserting an empty account into the observed-path count. The correction
uses a nonmutating lookup; the correct observed-path count is 54, not 55.
The corrected report includes source hashes and aggregate values only, without
native paths, identities or token dictionaries. Neither artifact enters Git.

Local full backend/script regression: **300 passed, one optional PostgreSQL
test skipped**, with `DATABASE_URL=sqlite-local`. Synthetic tests cover source,
account and bucket scope; actor independence; missing context; exact key
preservation; fitting/population filters; and aggregate-only reporting.
