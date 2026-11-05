# User decision: live data flow during the competition (1 Nov 2026)

**Decision (user):** Argus must show **live data flowing during the competition, 25–26 Nov**,
not only data recorded from 1 to 16 Nov. Recorded by Claude and handed to Codex, who owns the
runtime, collectors and workloads. Claude does not implement this.

**Why this needs work:** the GitHub and Cloudflare workloads end on 13 Nov. The AWS backend,
collector and daily tasks expire on 17 Nov 00:00. Without changes, nothing new arrives after 17 Nov.

## Constraints proposed by Claude (for Codex to confirm or amend)

1. **Separate from the V3 study.** Post-study activity must be its own versioned phase, for
   example `demo-live-v1`, with dates starting after the V3 evaluation inputs close (15 Nov 20:00
   receipt cut-off).
   - It must never be readable as V3 fitting, calibration or case data.
   - It must not change the 18 bound V3 sources after 10 Nov 00:00. Put it in new files or a new
     runtime pin set.
2. **Honest labelling.** Scripted persona or bot activity is shown as controlled or generated
   activity, never as human users. Any real activity from your own accounts is labelled as real.
3. **No live risk tiers.** W33 diagnostics stay experimental raw scores, under the existing
   display decision.
4. **Approvals still needed from the user before installing:**
   - extending GitHub/Cloudflare token lifetimes and schedules;
   - extending AWS service expiry;
   - cost limits;
   - the competition-day host. The laptop or a hosted runtime must be online at the venue
     (venue network, power).
5. **Fallback:** if the venue network fails, keep a recorded replay of the same pipeline. Label it
   clearly as a replay.

## Decision deadline

The workload extension must be decided and staged **before 13 Nov** so that GitHub and Cloudflare
do not lapse. It does not need to be installed before then if it starts on or after 16 Nov.
