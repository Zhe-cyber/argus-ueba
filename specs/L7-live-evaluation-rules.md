# Live evaluation rules v1 — scripted checks of Argus's live scoring and explanation path

Drafted 12 November 2026 (MYT); revised the same day after a Codex review. Committed only after
the scoring build (L8) is final, and before (a) the first scenario call and (b) any evaluation
score from 12 November onward is inspected. The pre-registration record is the commit SHA plus a
timestamp outside Git (§8). After the first scenario call nothing here changes; a needed change
becomes version 2 and both versions are reported.

## 1. What is evaluated

The baseline risk score that the Argus workspace displays and alerts on: per account and
Malaysian calendar day, 0–100 from five signals (new action, new resource, unusual hours for that
account, volume, new sensitive resource) against the account's own previous 28 days; tiers High
≥ 60, Medium 30–59, Low < 30; **Learning** below five prior active days.

**Frozen method: v1.2.** The method is the content of `config/baseline_method_v1_2.json` (weights, tier
cut-offs, history window, learning minimum, novelty and usual-hours parameters, the sensitive
first-access floor, sha256 of the sensitive-resource list and sha256 of the reference outputs
`backend/tests/data/baseline_reference_v1_2.json`), recorded with its own sha256 in §8.
The sensitive-resource list feeds only the new-sensitive-resource signal. The Malaysia-time
business-hours setting used by the rule engine does **not** feed any of the five signals (tested).
The scorer may live in any module; the reference outputs must reproduce exactly. One method
version scores the whole evaluation.

**How numbers are produced.** All evaluation numbers are recomputed once, after the last
scenario, from stored events with the frozen method (`backfill`). What the analyst saw live
(`ingest` scores and findings as they arrived) is reported alongside for alert timing. Each
row records which mode produced it.

## 2. Scenarios (scripted checks, designed with knowledge of the scorer)

Run by the owner with `scripts/demo_scenario_live.py`, inside the owner's lab account, using only
the personas' existing read-only permissions. Times are MYT. Scenarios run no earlier than
14 November 2026 and only after these rules have been sent to the supervisor. At most two scenarios
run per Malaysian day, on different personas (one daytime 10:00–17:00, one evening 21:00–22:00), so
no account-day contains two scenarios; the script refuses a second run for the same persona on the
same day.

| # | Persona | Behaviour | Expected tier (stated now) |
|---|---|---|---|
| S1 | persona-02 | 21:00–21:30: 12 reads of `confidential`, 6 each of p04/p05/p06, `GetBucketLocation` on those four, one `ListObjectsV2` on `confidential` (expected AccessDenied); its Cloudflare token requests the lab app 8 times in the same window | High |
| S2 | persona-05 | 21:00–22:00: 5 reads on its usual buckets (p05, p04), nothing new | Low |
| S3 | persona-04 | Within 10:00–17:00: 1 read of `confidential`; nothing else changed by the script | Medium |
| S4 | persona-06 | Within 10:00–17:00: 30 reads of its usual bucket p06; nothing new | Low or Medium |

Planned order: 14 Nov S3 (day) + S1 (evening); 15 Nov S4 (day) + S2 (evening). A later start keeps
the same pairing. S1 is on the first day because Cloudflare collection by the study pilot ends after
14 November, so S1's Cloudflare part needs 14 November or the post-study collector.
**Repeat rule:** a scenario is repeated only if its day is not evaluable under §3, at most once,
and never because of its score. Every attempt is reported with the reason for any repeat.
**Study end:** the evaluation window closes at the end of 22 November 2026 MYT; scenarios not
completed by then are reported as not run.

## 3. One coverage rule for scenario and normal days

An account-day (one provider account, one MYT day) is **evaluable** if, and only if:

1. the collector for that provider ran without a gap longer than 30 minutes between 07:00 and
   23:00 MYT that day, per `ops-status.json` / tick records; and
2. at least 90% of that account's planned or scripted calls that day are provider-confirmed
   within 24 hours after the day ends; an unresolved or unknown call counts as not confirmed; and
3. no fetch for that provider that day returned a full page (possible truncation; GitHub and
   Cloudflare fetch bounded samples of up to 100 records over 24 hours).

Eligibility is decided once, 24 hours after the day ends, by script, for scenario and normal days
alike. Non-evaluable days are listed with the failed condition. **Learning** days are reported
separately and are not in the tiered denominator.

## 4. Normal comparison

Every evaluable persona account-day (AWS role and Cloudflare service token of persona-01 …
persona-06) from 12 November 2026 to the end of the window that is not a scenario account-day for
that same account. Monitoring-infrastructure accounts and the shared GitHub bot are reported
separately and are not in the comparison.

## 5. Outcomes reported

1. **Per scenario:** final tier and score, each signal value and the facts shown, for the AWS
   account and the Cloudflare account **separately**, and for S1 also the cross-cloud group score.
2. **Analyst view:** whether a baseline finding appeared, when it **first** appeared and at which
   tier, and its latency measured from the **first provider-confirmed scenario event**. If the
   account already had an open finding that day before the scenario started, that is reported
   and latency is not computed. A tier that rose and later fell is reported as both.
3. **Normal comparison:** evaluable account-days N, Learning days L, counts at Medium and at High,
   each alerting account-day listed with its facts.
4. **Expected vs observed** tier per scenario: matched / higher / lower. Misses are reported with
   the same prominence as hits.
5. **Carry-over:** scenario days stay in each account's history, as they would in production. The
   next evaluable day of each attacked account is reported, flagged as following a scenario.

Counts with denominators only; no accuracy, recall or false-positive percentage from four cases.
The results table is generated by a script from the stored data, not by hand.

## 6. Limits stated in advance

These are scripted checks of the live scoring and explanation path, designed by the scorer's
author with knowledge of the method; they are not a measure of detection rates for real
attackers. The personas are controlled machine workloads, not people. The score is a fixed
heuristic, not a trained or validated model. Collection is local and polled; GitHub and
Cloudflare fetches are bounded samples, so completeness after downtime is not guaranteed.

## 7. Changes before freeze (disclosed)

Made on 12 November 2026, after a rehearsal on **simulated** events in a scratch copy and before any real
scenario call and before this file was committed:

1. **Method v1.1 → v1.2:** sensitive first-access floor. If the new-sensitive-resource signal (after the
   novelty discount) is ≥ 0.5, the account-day score is raised to at least 30 (tier at least Medium), with a
   fact line naming the resource. Reason: in the rehearsal a single first read of `confidential` (S3) scored
   27 Low. Nothing else changed.
2. **S2 expected tier Medium → Low.** Reason: S2 changes only the time of day; unusual hours alone is designed
   not to alert (weight 0.20, so at most 20 when every event is outside the account's usual hours).
3. Rehearsal predictions under v1.2 (simulated, one day each after the latest real day; not evidence):
   S1 AWS 86 High (Cloudflare 35 Medium, group 96 High); S2 22 Low; S3 30 Medium; S4 15 Low.
   S1 High, S3 Medium and S4 Low or Medium are unchanged as stated expectations.
4. **Earliest run 16 → 14 November 2026.** The 16 November guard protected the V3 study, which is
   closed (its freeze cannot be released). Scenarios also wait until these rules have been sent to the
   supervisor.
5. **Schedule: one scenario per day → at most two per day on different personas** (one daytime, one
   evening; never two on one account-day), planned 14 Nov S3 + S1 and 15 Nov S4 + S2. Reason: S1's
   Cloudflare part depends on the study pilot's Cloudflare collection, which ends after 14 November.

## 8. Pre-registration record (filled in at commit time)

| Item | Value |
|---|---|
| Method binding file sha256 | (filled at commit) |
| Reference outputs sha256 | (filled at commit) |
| Sensitive-resource list sha256 | (filled at commit) |
| Commit SHA of this file | (the commit itself) |
| Timestamp outside Git | Push to GitHub, then e-mail this file's commit link to the supervisor (server-side time), before the first scenario |
