# Cloudflare machine pilot: running

30 October 2026. A separate Access-protected static Worker now accepts the six
explicit lab service tokens. Original approved-human app and frozen AWS study
remain unchanged. This is controlled machine activity, not six independent
human users, and does not establish detector effectiveness.

## Verified end to end

Unauthenticated request denied; one commissioning service request returned
HTTP 200. Its exact native Cloudflare ray ID matched a successful Access log.
The log carries `connection=nonidentity`, the native Client ID in `user_email`
and no human `user_id`. Original log JSON was forwarded unchanged, stored once
with its real timestamp and attributed to a distinct service_token account.
The observed account appears in Argus with Unknown priority and no AE score.
It is excluded from the human identity-link picker and cannot be linked as a
human via the API. No detector was activated or threshold changed.

Backend tests: **197 passed**. Setup/commissioning/pilot tests: **11 passed**.
Worker tests: **3 passed**. Coverage includes exact token policy/read-back,
unauthenticated/forged-header denial, native identity separation, denied human
link, original payload/receipt scope, durable claim before HTTP, no repeat on
timeout, missed-window handling, source tamper rejection and expiry.
The initial sandboxed backend run stalled and was stopped; the isolated full
suite completed outside that sandbox. One new test's expected rejection status
was corrected to the API's existing 409 convention before the passing run.

## Operation

Task: `Argus-Cloudflare-Machine-Pilot`, every five minutes while the laptop is
awake/online; no wake-from-sleep setting. Each profile makes at most one actual
request/day in its fixed daytime window. Six requests/day, 90 over the pilot,
plus the separately labelled one-time commissioning request. No backfill,
timestamp edits or retries of uncertain actions. Collection may poll overnight;
it does not generate overnight workload requests.

Actions: 30 October–13 November; 14 November delayed-log reconciliation only;
task and credentials expire by 15 November 00:00 MY. Due times vary
deterministically by profile/date under the prospective W32 contract. Today
the first scheduled request is persona-05 at **08:56 MY**, executable through
09:41. The first installed task run completed with zero actions, as expected
before the daytime slots. Actual native events, not credential count, determine
how many accounts appear in the dashboard. One service account is observed at
commissioning; the other five appear only after their first real log arrives.

Private ignored state: `data/live/cloudflare-workload-lab-v1/`:

- `pilot-config.json`: fixed scopes, dates and source hashes; no client secrets.
- `machine-ledger.db`: claimed/missed/pending/provider-verified action receipts.
- `last-pilot-status.json`: latest execution/collection counts and errors.
- `persona-01.dpapi` through `persona-06.dpapi`: current-user encrypted secrets.
- commissioning request/log/ingestion receipts, separately labelled.

Native events are saved in the existing connected SQLite store. Same-ID
duplicates do not inflate history. Log polling is a bounded 100-row, last-24h
sample; completeness is unknown and laptop gaps can lose events. Sleeping
through an entire date is an unobserved gap, not a zero-activity normal day.
Missed previous dates are not replayed. Permission/network failures remain
visible in status and are not silently counted as successful history.

The temporary Cloudflare commissioning checker was disabled after its log was
captured. The original collector/backend were briefly paused for the three
reviewed backend attribution changes, repinned, restarted and health-checked;
the collector is enabled again. AWS role profile/ledger/method/dates did not
change. The user-owned GitHub project repository is untouched.

## Limits

One Cloudflare app and mostly login-kind events provide little behavioural
diversity. Six service identities do not solve human baseline cold start or
validate transfer from CLUE. No cross-provider person mappings are fabricated.
This new stream is separate from both CLUE evaluation and the frozen AWS
study. GitHub bot event reconciliation remains a separate setup step.

References: [W32 prospective contract](../specs/W32-cloudflare-controlled-machine-pilot.md),
[Cloudflare Service Auth policies](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/common-policies/).
# Status-history correction, 30 October 2026

The pilot now reports `attention_required` while any `claimed_unknown` action
remains, instead of a generic completed status. Sanitized tick results append to
`pilot-attempts.jsonl` so a later successful collection poll cannot erase the
failure history. The original missed/unknown/provider-verified ledger records,
workload windows, dates and budgets are unchanged. No failed request was retried.
Only the reviewed `cloudflare_machine_pilot.py` source pin was updated after
tests and a configuration backup; the task resumed before the remaining slot.

