# W29: one action-mix development decision

30 October 2026. Written before computing the new switch scores. This is the
single permitted follow-up development round, with a decision due 3 November.
It is not a new independent test or a live release protocol.

## Reuse and exclusions

W4 account-conditioned numeric centres failed; W6 familiarity has a
history-dependent ceiling; W7 equal-five-date raw novelty saturated at one
(51/154 normal calibration days); W10 context/primary also saturated. Do not
rerun, tune or combine those failed candidates. Globally unseen categories must
remain in any scored distribution, not be dropped as unavailable.

The only candidate in this round is the existing W8/W10 **action_mix control**:
base-2 Jensen-Shannon divergence from the account's equally weighted fitting-day
action distributions, with at least five usable fitting days. Its maximum is
one regardless of history length. Reuse the original saved reference, unchanged
normal calibration and strict threshold 0.8723298381957394. No refitting,
reference updates, threshold search, OR rule or fallback to another view.
This is a newly declared development candidate, not a replacement for W10's
failed historical primary. Keep all previous no-go results.

## Data and comparisons

Use the existing verified prefix only, never the full archive. Fit reference
13–26 July, normal calibration 1–4 August, diagnostic normal days 5–9 August
2017 UTC. Use exactly the original hash-bound three reciprocal switch pairs
and all 25 switched account-days, starting 5 August. These pairs and days have
already influenced earlier work. Even a positive result is exploratory.
Do not read 11–24 August again or any September row. September remains a
possible future test, not a reservation/release made by this document.

Project the original native events once using the unchanged W10 projector.
For each switch pair, relabel the donor's entire projected day to the receiving
account; donor inactivity produces no fabricated day. All references remain
fitting-only. Check original count/coverage parity against the existing W6
report and cached AE scores. Retain donor-only normal rows and all missing
coverage counts. The comparator is the cached original **ten-feature CLUE AE**
on these exact days, not the later five-feature model. No model deserialization
is needed. No numerical values from different contracts are pooled.

Report candidate coverage, normal alerts, switch recall, per-pair hits, AUROC
and average precision against normal originals; AP prevalence must be stated.
Report common-scorable comparison denominators as well as all-input coverage.
The same-day counterfactuals/accounts are dependent; no significance or
independent-binomial confidence claim. Exclusions never become negatives.

## Fixed engineering go/no-go

Advance only if ALL hold: at least 90% of the 191 normal and 25 switched days
are scorable; normal alert fraction <=5%; at least 5/25 switched days alert;
at least two of the three pairs have an alert; common-scorable AUROC >=0.65.
These are pragmatic development screening targets, selected now without new
switch scores, not evidence of deployed sensitivity or a statistical guarantee.
A pass only permits designing one fresh, fully frozen test. A failure closes
this follow-up: no new scalar, view, history length, threshold or scenario run
to repair this round. Unexpected input/hash errors stop execution rather than
loosening a binding or silently selecting other data.

## Applicability and schedule

Action composition cannot detect pure time shifts or proportional volume
increases, and is not a general compromise detector. Cloudflare's one app and
near-constant sign-in action provide little discrimination. GitHub has limited
repository variety; AWS S3 reads also have near-constant action kinds. Do not
infer transfer from CLUE or promise one effective scorer for all three sources.
Any later time feature uses time-of-day only, including weekends, with declared
source timezone. This candidate has no time feature.

Decision by 3 November; only if go, freeze the complete new method/test protocol
before any fresh native test row, target 7 November freeze / 10 November result.
Final project results freeze 15 November. The existing AWS study, its source
commit deadlines and identity timeline take precedence over this follow-up.
No provider calls, runtime repinning, risk-score writes or live activation.

Save the plan hash, all source/input hashes, scores and decision in a new private
directory; publish aggregate findings only. One source-bound successful run;
engineering tests use synthetic fixtures and do not consume another comparison.
