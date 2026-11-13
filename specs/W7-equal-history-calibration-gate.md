# W7 stage 1: fixed-five-date novelty calibration gate

28 October 2026. Fix before computing v2 calibration. Development only; no
fresh data reservation/download, switch scoring, threshold tuning or activation.

For the frozen 55 CLUE accounts and 13-26 July fitting window, use exactly the
last five resource-active fitting dates per eligible account. Eligibility needs
five such dates; retain exclusions. The personal reference is the union of
source-scoped literal paths on those five dates. Later observations never update
it. The global vocabulary uses all selected accounts' full fitting window and
is a descriptive flag only, never a score exclusion or reference shortcut.

On a resource-active day with resolved native coverage and eligible account:
score = distinct paths absent from personal five-date reference / distinct paths.
Globally unseen paths are included in numerator and denominator. Report their
fraction separately. A login-only/no-resource day has status no_resource_activity
and no resource score; it is not insufficient baseline history or Low. Invalid
resource/required-path/unknown-action coverage remains unavailable. Unknown or
ineligible accounts remain unavailable. No ownership/ACL or intent inference.

Calibrate ONLY on 1-4 August normal days: linear q99, strict >, at least six
scorable account-days across three accounts. Report all original169 calibration
rows, availability, status and globally unseen fractions. Report exact and near
(absolute1e-12, reporting only) threshold ties. No parameter search or >= change.

Predeclared no-go: if q99 is exactly1, the bounded score can never strictly
exceed it. Reject this candidate and do not spend time scoring switches or fresh
evaluation. Report switch evaluation NOT RUN, not a measured0/25. If q99<1,
this gate only permits a subsequent fixed development comparison; it does not
validate a detector or authorize live use. Preserve this result either way.

Use the existing native prefix/manifest and hash-pinned W6 result for binding,
verify original projection/scorer source hashes and input files unchanged. No
cached AE claim is a newly run replication. Save and reload the new JSON
reference before calibration. Outputs in a new private directory; no data or
fitted dictionaries in Git. Frozen W6/CERT/AE/live contracts remain untouched.

Tests: exact last-five selection; no score/reference updates after fitting;
globally unseen resources count as novelty; no-resource state distinct from
missing baseline; sparse/unknown coverage; JSON contract/reload; strict
threshold1 no-go and ties; invalid/duplicate/date-overlap rejection. Full tests
use DATABASE_URL=sqlite-local. This stage neither implements a live annex nor
downloads later CLUE data.
