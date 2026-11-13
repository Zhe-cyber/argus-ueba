# W5 stage 1: resource observability before model design

28 October 2026. Follow-up to the negative numeric-baseline comparison.

Deliver a separate offline resource adapter and a fitting-only CLUE audit.
Do not change the frozen ten-feature extractor, normalizer, model or live store.
This stage does not define or calibrate a new anomaly detector.

Resource identifiers are opaque, source-scoped SHA256 tokens over structured
JSON tuples, not ownership assertions or cross-provider identity links. Preserve
literal CLUE paths; do not prefix with the observed actor (which would make
every borrowed resource look like a new resource). A shared literal path can
also mean a shared folder or a relative-path collision; do not infer ownership.

For AWS S3 native records, require recipientAccountId, eventSource s3.amazonaws.com
and requestParameters.bucketName. Retain bucket and object tokens separately;
an absent key yields bucket-only coverage, never an invented object. Preserve
the key literally: no URL decoding, path resolution or removal of slashes.
The experimental adapter reads raw records, not the current normalized bucket
field. Unsupported sources and missing fields return explicit coverage states.
No generic resource fallback or zero-as-normal conversion.

Audit only the frozen 55 identities and fitting dates 13-26 July 2017 from the
existing hash-pinned prefix. Output aggregate coverage, resource distinctness,
cross-account literal-token reuse and path-shape counts. Never emit native
paths, account IDs or token dictionaries. No switch cases, validation,
calibration or development features enter the audit. No downloads/cloud calls.
The already inspected prefix includes partial 10 August; this is not a fresh test.

Acceptance: synthetic tests prove scope isolation, literal key preservation,
bucket/object distinctions, missing/unsupported states, actor-independent
CLUE paths, fitting date/population filtering and aggregate-only output.
Retain the audit even if resources fail to separate identities. Choose and
document a small next candidate family only after understanding this coverage;
freeze its method before another scored comparison. Raw novelty alone already
had a saturated normal threshold and must not be sold as a proven fix.
