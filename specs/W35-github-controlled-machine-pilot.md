# W35: finite GitHub controlled machine workload

30 October 2026. Live-system work, separate from Claude's offline W33 model work
and the frozen AWS study. Commissioning ingestion through W34 is complete.

## Scope and representation

One installed App, one private repository `Zhe-cyber/argus-activity-lab`, one
native Bot account. Six workload profiles are timing/content templates, not six
people or six GitHub accounts. Every created file and commit says controlled
machine workload. No GPT/LLM calls, human login automation, project-repository
edits, response decisions or score writes. No claim of independent human habits
or sufficient AE training data; repository-level resource diversity remains one.

Start prospectively 31 October, last action day 13 November 2026, reconcile only
14 November, hard expiry 15 November 00:00 Asia/Kuala_Lumpur. Do not generate
replacement actions for 30 October or days the laptop was unavailable.

## Frozen generator and budgets

Seed 20261031. SHA256 over canonical compact sorted-key JSON selects a daily
count `2 + hash([seed,day,"count"]) mod 5`, then profiles in ascending hash order
of `[seed,day,profile,"active"]`, then profile ID as tie-break. Thus 2–6 planned
commits/day. Each active profile gets one slot using hash of
`[seed,day,profile,"time"]`, modulo its window length minus 45 minutes.
The slot lasts 45 minutes. Time-of-day windows (MYT): p01 08–11, p02 10–17,
p03 11–17, p04 16–19, p05 08–10, p06 12–16. All remain within 08–20.

Action ID is SHA256 of `["github-machine-v1",day,profile]`. Write only
`workloads/<profile>/<day>.json`, with no update SHA or overwrite, using the
repository default branch. Payload includes provenance, action ID, day, profile
and `independent_human_user:false`. Commit message contains the full action ID.
At most one write attempt per active profile/day, six/day and 84 across 14 days,
excluding the earlier one-time commissioning commit. Known failures and unknown
outcomes consume their claim; they are never blindly retried.

## Receipt and safety gates

Require the actual ingested commissioning receipt and matching repository,
installation, owner and Bot IDs. Bind configuration, generator, code and this
spec before installing the task. Validate the local backend identity before any
work and verify the private repository context using restricted App credentials.

Claim each write durably in SQLite before the provider call. Save its returned
commit SHA before any secondary read. Verify the native commit's Bot actor ID;
then reconcile the exact SHA/actor to native repository activity. Preserve raw
activity privately and require Argus's matching durable ingest receipt before
`provider_verified`. Do not also ingest the lab Events feed. No fabricated log
or invented success after a timeout. Unresolved unknown writes block further
writes; read-only reconciliation continues. A known SHA with pending identity
can be rechecked, but no new write occurs until identity is confirmed.

Maintain original missed/unknown outcomes and explicit pending counts. The
default activity read is bounded to 30 rows; report a cap hit rather than claim
complete history. Never treat missing evidence as a negative. A per-task lock and
SQLite scope bind prevent concurrent/foreign claims. Existing configuration and
ledger are never overwritten on setup.

## Operations

Laptop task checks every 15 minutes and at logon; laptop must be awake/online.
No global power or update settings change. The task invokes hidden Python,
suppresses raw exception/payload/credential logs, and expires automatically.
Latest status plus an append-only attempt journal preserve failures across later
successful polls. The user can disable the task without changing the AWS study.
This schedule is an integration workload, not the model evaluation population.
