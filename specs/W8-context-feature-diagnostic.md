# W8: action/context stability diagnostic, no detector

28 October 2026. Fix exploratory views and reporting before computing results.
Use the existing pinned prefix/population only. Fit 13-26 July, inspect normal
validation 27-31 July (188 account-days), all already development data. No
calibration, switch-case scores, later data, threshold selection or live changes.

Three fixed views: exact native action proportions by event count; literal
parent-prefix proportions at depth1 and depth2 by DISTINCT path count. Strip
empty slash components for the context proxy and omit the last component;
do not interpret that as a verified file/directory distinction or resolve ..,
case or encoding. A path without parent components goes into one root bucket.
Short parents retain their available components, without adding the leaf.
Hash source-scoped structured category tuples, never the current actor.

Per-view account reference = mean of fitting daily probability distributions,
so days are equally weighted; need five fitting dates with usable categories.
No-resource view is unavailable, not a root bucket fabricated for a login.
Unknown action/invalid resource/required-path gaps remain unresolved coverage.
Compare ONLY later validation distributions using base2 Jensen-Shannon
divergence (not sqrt). Include unseen categories in the union, never drop them.
References/vocabulary stay fitting-only and do not adapt after fitting.

For each eligible validation account-day, compare its distance to its own
reference with median distance to all other eligible account references. Need
three other eligible accounts. Report own-closer / tied / other-closer counts
with1e-12 comparison tolerance (diagnostic only); own uniquely nearest counts
and nearest-reference ties separately. Include own divergence1/no-overlap counts
and globally unseen category probability mass. Report all three views, all
The global-category flag uses the full fitting vocabulary across all 55
accounts, including categories only seen under an ineligible reference account;
it does not drop query categories or alter distances. Report all three views, all
original188 rows, per-view coverage and both pooled-day and equal-account
descriptive fractions. No accuracy claim, peer-group detector, attack recall,
p-value or independent validation is implied by this closed-set comparison.

Privately count distinct paths whose first two parent components contain an
exact native uid match. Emit only aggregate counts, not names/path strings or
token dictionaries. This is a limited identity-signature warning; absence of
an exact match cannot exclude encoded usernames, IDs or other namespace cues.
Literal path equality is not physical-object identity, ownership or ACL proof.

Save a separate private reference and diagnostic report; verify input hashes
and reference immutability before/after diagnostics. No data/reference
dictionaries in Git. No W6/W7/AE/CERT/core normalizer changes or external source
transfer. If no view separates accounts, retain that result rather than deepen
prefixes or change metrics in this run. Any next candidate needs its own fixed
method, normal calibration and fresh evaluation before deployment.

Tests: JS identity/disjointness/symmetry, daily reference weighting, unseen
categories, filename-change invariance, parent/actor/source semantics, no-resource
coverage, five-date eligibility, later-only diagnostics, immutable reference,
ties versus unique-nearest and date/duplicate rejection. Force
DATABASE_URL=sqlite-local for full regression.
