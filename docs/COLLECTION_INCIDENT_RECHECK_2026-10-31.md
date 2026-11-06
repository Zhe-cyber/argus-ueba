# Collection incident recheck — 31 October 2026

Checked about **19:20–19:25 MYT**, after a report citing the cached 14:05 daily
check. Read-only operational investigation; no actor replay, model action, source
repinning, power-policy/update change or live backend restart.

## Current state versus the earlier snapshot

- Original backend task Running; last start 30 October 17:50 MYT.
- Collector ticks currently completing successfully; latest initial inspection
  was 19:16 MYT with AWS, actor, audit, GitHub and Cloudflare phases all successful.
  Actor phase says no_due_actions, new_actions=0.
- Main collector, GitHub workload and Cloudflare workload tasks are enabled.
  They allow battery operation, do not stop on battery, and do not wake the
  laptop. No disabled/stuck task required restoration during this check.
- GitHub workload task completed successfully but today's four slots are missed.
- Cloudflare task's result 1 is its deliberate attention result: four unknown
  outcomes across both days, five missed, three native-verified. It is not proof
  that the scheduled task or backend crashed.
- Pilot runtime source-pin validation passed.

Refreshed the existing daily checker through its unchanged read-only command.
The new latest report no longer lists stale collectors/polls. Remaining issues:
`incomplete_closed_study_days` and `yesterday_tick_failures_or_gaps_review`.
Also refreshed the isolated preview's operational snapshot atomically. Native
event copy and all original action ledgers are unchanged.

## Today's loss is real

Read the frozen plan and ran the existing native-receipt readiness verifier.

| 31 Oct role | Planned | Verified | Missed |
|---|---:|---:|---:|
| persona-01 | 1 | 0 | 1 |
| persona-02 | 3 | 0 | 3 |
| persona-03 | 1 | 0 | 1 |
| persona-04 | 5 | 0 | 5 |
| persona-05 | 5 | 0 | 5 |
| persona-06 | 1 | 0 | 1 |
| Total | 16 | 0 | 16 |

The readiness tool correctly labels today's calendar day current_partial until
closure, but every scheduled AWS action is already marked missed and the last
15-minute opportunity ended before this inspection. This cannot be recovered by
running the actor late. No calls were backfilled or records changed.

31 October tick journal gaps greater than 20 minutes:

- 06:11–07:05 MYT (~55 min).
- 07:05–14:06 MYT (~420 min).
- 14:06–14:41 MYT (~35 min).
- 14:57–18:11 MYT (~193 min).

Windows Kernel-Power descriptions corroborate Modern Standby: idle timeout at
06:11; additional standby transition at 07:05; wake by power button at 14:05;
idle again at 14:06; power-button wake 14:41; idle at 14:42; standby transition
14:57; power-button wake 18:09. These overlap the intended action windows.
This supports laptop availability as the main operational issue; it is not
evidence that the new preview restarted the original backend.

## Cloudflare wake-up failures

Three new unknown claims today were made just after wakes, around 14:05, 14:41
and 18:09 MYT. Their journal entries report ConnectionError. Earlier API-access
failures also produced SetupError entries. Logs do not establish every exact
network cause or whether each protected request reached Cloudflare.

Current DNS/TLS handshake to the configured machine Worker succeeded. That probe
sent **zero HTTP requests and zero service credentials**. It shows transport
availability now; it cannot resolve past requests. Keep those outcomes unknown,
without automatic retry. Today's Cloudflare breakdown is three unknown and three
missed; yesterday's remains one unknown, two missed, three verified.

## Correct the AWS study interpretation

The “study has not failed; each role can lose one more day” interpretation omits
the independent span gate. The unchanged authoritative requirements are:

- V2 protocol: at least five active fitting dates **spanning seven calendar dates**.
- Method annex: **all six roles** must satisfy that gate.
- Existing code: `fit_ok = len(fit) >= 5 and span >= 7`.
- Fitting window: **30 October–5 November**.

The four roles with unusable 30 October can begin their usable fitting history
no earlier than 31 October, so their maximum possible span is six days. Thus
the original all-six-role release gate is already unattainable under unchanged
rules. Today's additional losses do not change that mathematical conclusion.
The count-only five-of-seven condition is necessary but not sufficient.

This affects the specified AWS reserved study, not the separate W33 experiment
or all live engineering diagnostics. Continue genuine collection as authorized;
do not silently amend dates, accept imputed receipts or lower gates. The user
previously chose to leave records/rules unchanged.

## Required operating condition

The laptop was on battery and discharging at inspection. Current scheduled
tasks do not prevent sleep or wake it. For the chosen laptop pilot it must stay
plugged in, awake, online and with the lid open during 08:00–20:00 MYT. A
scheduled process cannot guarantee execution through Modern Standby. No global
power or Windows Update setting was changed without a direct user instruction.

Private evidence: `data/live/collection-incident-20261031/readiness-current.json`
and `worker-transport-probe.json`; original timestamped tick/claim journals and
Windows event log remain the sources of truth. No code, model or study artifacts
were modified by this incident check.
