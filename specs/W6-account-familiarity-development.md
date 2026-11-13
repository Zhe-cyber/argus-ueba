# W6: fitting-only account familiarity, development experiment

28 October 2026. Fix this method before computing candidate calibration or
switch scores. Based on resource-observability (PR #21); all existing August
development dates and pairs remain inspected development data. This is not a
new independent test, AE retraining, live model or completed live method annex.

## Question and fixed representation

Can account familiarity with resources/actions add information lost by the ten
count features? Use the same frozen CLUE population, splits, prefix and three
switch pairs. Preserve the frozen AE and all previous misses and reports.

For each account-day, collect distinct source-scoped literal-path tokens using
resource_observability_v1 and distinct tokens of exact native action names.
Count event/path/invalid/unknown-action coverage separately. Do not encode the
current actor in a resource token or infer ownership/ACLs from frequency.
Account switches reassign native events, preserving resources/actions. Fit all
state only on 13-26 July; no warmup, validation, calibration or development
observations update the reference/vocabulary. Daily distinct presence, not
raw event frequency, limits influence of one high-volume actor/day.

## Two fixed candidates, no search or outcome-based selection

For each dimension (resource, action), D_u is account u's fitting dates with
at least one usable token; k_u(t) is the number of those dates containing t.
D is the sum of all selected accounts' such dates and k(t) the sum of their
incidences. Vocabulary is fitting-only. For known token t:

    p_pool(t) = (k(t) + 1) / (D + 2)
    p_user(t) = (k_u(t) + 5 * p_pool(t)) / (D_u + 5)
    deviation(t,u) = max(0, log(p_pool(t) / p_user(t)))

This is a smoothed daily-incidence familiarity contrast with fixed shrinkage
strength five dates. It is a heuristic score, not an attack probability,
ownership attribution, likelihood of the whole day, SHAP or a causal cause.
Take the mean over today's distinct fitting-known tokens for each dimension.
Report globally unseen token counts/fractions separately. If no today's token
is fitting-known, that dimension is unavailable, never silently zero. This
explicitly cannot score entirely new resource namespaces; do not hide that gap.

Candidate R = resource contrast. Candidate J = max(resource contrast, action
contrast), requiring both dimensions available. Personal eligibility: at least
five usable fitting dates in each required dimension. A required-path gap or
unknown native action makes the resource/joint account-day unavailable; ordinary
non-path actions are coverage, not missing-required-path errors. Invalid supplied
path/params also yields unavailable. An absent resource for a login does not.
Positive source coverage and account eligibility remain separate from a score.

Calibrate R and J independently on normal calibration (1-4 August), q99 linear
interpolation, strict >, minimum six scorable calibration account-days across
at least three accounts. If a minimum fails, report no-go; no relaxed gates.
Report both candidates regardless of result; no tuning strength, vocabulary,
aggregation, inequalities or thresholds using switch results. Also compare the
frozen AE and fixed AE OR J, with tri-state unavailable logic and actual union
normal-alert rate. No detector winner selected from this small development run.

## Execution and reporting

Before loading trusted weights, reuse pinned-input/native-ten-feature checks
from W4. Build a separate resource/action projection; match its native counts
and account-days to frozen rows. Reject altered earlier partitions for every
switch case. Reproduce AE 2/191 normal and 0/25 switched results. Calibrate and
save new reference/threshold JSON before scoring development cases, then reload
JSON and require identical scoring. Private artifacts only, new output folder.

Report original 191 normal/25 switched denominators, per-method scored/missing
counts, common scorable subsets and paired AE outcomes on those subsets, three
case-level counts, globally unseen fractions, eligibility and overlap. Repeated
normal controls across cases are not independent observations. Missing actor
activity is unavailable, never a true negative. Components are contrasts, not
SHAP. Native resource equality is not proven physical-object identity or proof
that a recipient had permission for a donor's actions.

All results remain development-only. No later download, cloud call, live DB
write, normalizer edit, AE change, registration/deployment or activation. No
native IDs/paths/token dictionaries in Git. No live AWS threshold transfer.
The fitting audit showed uneven resource history; eligibility may shrink the
population. Report shrinkage rather than calling excluded rows normal.

## Checks

Synthetic tests: same counts but different resources can change affinity;
actor-independent token identity; fit-only vocabulary and no later state
updates; same-day/future fitting scores rejected; five-date eligibility;
unknown-resource coverage and no known-token fallback; stable smoothing;
missing-required-path versus inapplicable path; unknown-action guard;
deduplicated daily presence; JSON validation/reload; strict q99 equality;
tri-state OR and report common denominators; native switching preserves prior
partitions. Run backend/scripts with DATABASE_URL=sqlite-local. Preserve negative
results; if an invariant fails stop, fix and document the failure before rerun.
