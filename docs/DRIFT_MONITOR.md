# Drift monitor

Code: `backend/drift_monitor.py`. Thresholds: `config/drift_monitor.json` (read at start of each run).
Run: `python -m backend.drift_monitor --db <sqlite copy> [--day YYYY-MM-DD]` or call `drift_monitor.run_once(day, now)` once a day from the mirror pass or supervisor.

## What it detects

**Account drift.** The baseline score compares each account-day with the previous 28 days. A slow insider who shifts behaviour a little each day is absorbed into that baseline, so no single day stands out. The monitor instead compares the last 7 calendar days (recent window) with the 21 calendar days before them (reference window), for each account with at least 14 active days in those 28 days and at least 3 active days in the recent window. Measures:

| Measure | Definition | Flag at |
|---|---|---|
| Volume shift | abs(log2(median daily events recent / reference)), medians over active days | >= 1.0 (2x) |
| Action mix | Jensen-Shannon distance (base 2, 0..1) of event-weighted action histograms | >= 0.30 |
| Resource mix | the same for resources | >= 0.30 |
| New items | share of the recent distinct actions and resources absent from the reference window | >= 0.50 |

Any one measure over its threshold flags the account.

**Source drift.** Per provider, today's (MYT) event count against the median of the previous 14 calendar days (days with no events count as zero). Flagged when, by 18:00 MYT (or once the day is over), today's count is below 25% of that median, or when there is a stretch of 6 hours or more without events inside 08:00-20:00 MYT (up to now for the current day). Only providers whose median is above zero are evaluated.

## Output

An observation, not a security finding and not a baseline alert: an `alerts` row with `alert_type` `behaviour_drift` or `source_drift`, severity `Info`, one per account (or provider) per MYT day (the existing unique index; a re-run the same day refreshes the details and never the status). `details` holds the measures, windows, thresholds, which measures fired and plain-language facts, for example "Median daily events rose from 3 to 9 (3.0x) between the reference window and the last 7 days". Monitoring-infrastructure accounts (`workspace_next/system_accounts.py`) are evaluated and labelled `monitoring_infrastructure`.

The workspace lists these under "Account observations" (queries origin `observation`), not under security findings. Security counts on the Overview and queue are unchanged. The account panel shows a "Behaviour drift" line, Connections a "Source drift" line. The monitor never writes `baseline_scores`, baseline findings or tiers, and nothing in the L7 evaluation reads it.

## Why

Rubinstein et al., "Stealthy poisoning attacks on PCA-based anomaly detectors", Performance Evaluation Review, 2009 ("Boiling Frog"): a detector that retrains on recent data can be moved by a gradual shift that stays inside what it currently accepts. That work is on network traffic and a PCA detector, not UEBA; here it motivates the concern, it does not validate the thresholds. Vendor writing on low-and-slow insiders describes the same pattern (research/decision-evidence-2026-11-12.md, section 7).

The test `backend/tests/test_drift_monitor.py::test_slow_insider_absorbed_by_baseline_but_caught_by_drift` shows it on synthetic data: volume growing 15% a day for 21 days never leaves Low in the baseline score, and the monitor flags it.

## Limits

- The thresholds are design choices, not validated. No false-alarm rate or detection rate has been measured.
- At least 14 active days are needed (about three weeks of history); younger accounts are not evaluated.
- Observation only: it does not score, rank or alert on risk, and it does not stop the baseline absorbing a shift.
- Window medians use active days only; an account that is active on 3 of 7 days is judged on those 3 days.
- A shift that began more than 28 days ago is invisible to it (it is in both windows). A real, legitimate change of role looks the same as a slow insider.
- Source drift reads event timestamps only; it cannot tell a quiet source from a broken collector.
