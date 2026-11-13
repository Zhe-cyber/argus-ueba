# Live evaluation report: how to generate it

`scripts/live_eval_report.py` produces the results of the pre-registered live evaluation. It follows
`specs/L7-live-evaluation-rules.md` (v1.2 rules), `specs/L7a-autoencoder-comparator-addendum.md` (comparator)
and `specs/L7b-coverage-clarification.md` ("planned calls" means claimed calls). Run it **once, after the last
scenario and at least 24 hours after the window ends** (after 2026-11-24 00:00 MYT for the default window end
of 22 Nov). Before then, days that are not yet 24 h past are reported as `pending`.

It opens every input read-only and writes only into a new `--out` folder. It refuses to start when the method
binding sha256 is not the L7 one (`4a44bb16…3f2`), when the comparator bundle's manifest sha256 is not the L7a one
(`d41e86a9…ffc0`), or when the output folder already exists.

## Command (PowerShell, from the repository root)

```powershell
$env:DATABASE_URL = "sqlite-local"
$P = "C:\Users\yyzhe\.codex\worktrees\argus-cloud-live\fyp-ueba\data\live"      # AWS pilot (ticks, AWS ledger), read-only
$M = "C:\Users\yyzhe\.codex\worktrees\clue-benchmark-replay\fyp-ueba\data\live" # Cloudflare/GitHub machine pilots, read-only
$O = "<ops checkout>\data\live\ops"                                             # ops status dir and persona ledger
.venv\Scripts\python.exe scripts\live_eval_report.py `
  --db      <copy of the events DB with baseline_scores, ml_scores, alerts> `
  --runs    data\live\demo-scenario `
  --ticks   "$P\pilot-local-v1" --ticks "$O\ticks" `
  --groups  <workload-groups.json next to the workspace copy> `
  --bundle  <the pinned bundle folder bundle-v2-20261113T010640> `
  --ledger  "aws=$P\persona-history-v1\ledger.db" `
  --ledger  "cloudflare=$M\cloudflare-workload-lab-v1\machine-ledger.db" `
  --ledger  "github=$M\github-app-lab-v1\machine-ledger.db" `
  --ledger  "aws=$O\persona-ledger\ledger.db" `
  --ledger  "cloudflare=$O\persona-ledger\cloudflare-ledger.db" `
  --window-end 2026-11-22 `
  --out     results\live-eval-v1
```

Take the `--db` copy from the operational store after the last day is collected (a copy, never the live file
while it is being written). `live-ae-loaded.json` (the comparator manifest the deployment actually loaded) and
`system-accounts.json` are read from the folder of `--db`; pass `--loaded <file>` if it lives elsewhere.
`--now` (ISO time with offset) is only for reproducing a past run.

## Inputs and what each one decides

| Input | Used for |
|---|---|
| `--db` events, `alerts`, `baseline_scores`, `ml_scores` | all scores are recomputed from `events` (backfill mode, frozen method); `alerts.first_raised_at` gives the analyst-view timing; stored rows are shown as "stored live row" |
| `--runs` `run-*.json` | scenario attempts, their scripted calls (matched to events by AWS requestID / Cloudflare ray ID) |
| `--ticks` folders | coverage conditions 1 (collector gap) and 3 (full-page fetch): pilot `<date>-ticks.jsonl` and ops `ticks\<date>-ticks.jsonl` (merged by time); ops-status documents are still read if present |
| `--ledger KIND=PATH` | coverage condition 2: every executor ledger row is a planned call; `provider_verified` within 24 h = confirmed |
| `--groups` | the S1 cross-cloud group score (members of `persona-02`) |
| `--bundle` | the pinned comparator, used to recompute the autoencoder scores |

**Collector history after the pilot.** The ops collector appends `ticks\<MYT date>-ticks.jsonl` under its status folder (see `docs/OPS_CONTINUITY.md`). Pass both tick folders: `--ticks <pilot state dir> --ticks <ops status dir>\ticks`. The report merges them by time: the combined lines (pilot-shaped `phases`) decide condition 1, so on the cutover day the gap runs across both sources (last pilot tick to first ops tick); the ops per-provider lines (`possibly_truncated`) decide condition 3. Planned calls from 16 Nov also come from the ops persona ledger (the two `--ledger` lines for `persona-ledger`). Ops days with no tick history (only `ops-status.json`) still fail or are `unknown`; the generator never guesses.

## Outputs

- `results.json`: everything, machine-readable.
- `results.md`: the tables for the report (executors by day, scenarios per attempt and account, expected vs
  observed, signals and facts, carry-over, normal comparison, autoencoder counts, separately reported accounts,
  non-evaluable days).
- `coverage.csv`: one row per account-day with the three conditions and their details.

Each starts with the provenance block: method sha256, manifest sha256, generation time, the `now` used for the 24 h
decision, the script's git commit and sha256, and the sha256 of every input file. No 12-digit numbers, e-mail or
IP addresses are written.

## Reading the results

- **Coverage status**: `evaluable`, `not evaluable` (with the failed condition and its detail) or `pending`
  (less than 24 h after the day ended). `unknown` conditions mean a needed input was missing.
- **Scenarios**: every attempt is listed. `(counted)` marks the attempt that is the result; a second attempt is
  counted only when the first was not evaluable (the reason is quoted). Expected vs observed is `matched`,
  `higher` or `lower` on the AWS account-day; S1 also shows its Cloudflare account and group score.
- **Latency** is minutes from the first provider-confirmed scenario event to the finding's first raise;
  `pre-existing` means a finding already existed that day before the run started.
- **Normal comparison**: N evaluable account-days, L Learning days, the tiered denominator N - L, and Low /
  Medium / High counts; each alerting day is listed with its facts (`follows_scenario` marks carry-over days).
- **Autoencoder**: flagged counts out of scored days at the primary and the secondary operating point, all days
  and excluding 12 Nov (a calibration day). If the deployment's loaded manifest was not the pinned one, the
  comparator is reported as not evaluated and no counts are shown.
- Counts with denominators only: do not convert them into accuracy or false-positive percentages (L7 section 5).

The generator's conservative readings of unclear points are listed in the "Rules resolved conservatively" section
of `results.md`.
