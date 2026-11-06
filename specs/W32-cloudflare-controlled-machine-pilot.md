# W32: prospective Cloudflare machine workload, separate from AWS study

Fixed 30 October 2026 before first scheduled action. Six service credentials,
one protected static app, one actual GET per profile per day. Native Access
logs expose authentication/app access, not activity inside an application.
This is controlled integration evidence, not six humans or attack accuracy.

Dates: 30 October–13 November inclusive; 14 November arrival reconciliation
only; expire at 15 November 00:00 MY. All scheduling Asia/Kuala_Lumpur. Profile
windows: p01 08–11, p02 10–17, p03 11–17, p04 16–19, p05 08–10, p06 12–16.
Due minute is fixed by SHA256([20261030, day, persona]) modulo the window's
minutes minus 45. Each action has a 45-minute opportunity, entirely inside
08–20. Task may collect delayed logs overnight; no overnight actor requests.
Use actual provider timestamps only. No catch-up for missed previous dates.

Exactly six maximum workload requests/day, 90/pilot, excluding the one separately
labelled commissioning request. Every action is durably claimed before sending;
unknown outcomes never retry. Missed windows are recorded as missed when seen,
not replayed. Sleeping through an entire day leaves a coverage gap, not normal.
One task instance and local file lock; immutable configuration/source hashes
and scoped ledger. No automatic source repinning, lower gates or model training.

Only six explicit token IDs allowed by a read-back-verified Service Auth policy
on the new machine app. Each current-user DPAPI credential is bound by native
token ID/client ID. No human app change, email/MFA automation or session reuse.
No redirects with credentials, no proxy routing, no secret output. Call limits
include claimed/failed actions. Authentication failures remain failures.

Collect at most 100 Access logs from the last 24 hours per tick, retaining only
the configured app and native machine client IDs with explicit allowed outcome.
Forward original records once through the existing native-receipt protocol;
provider ray ID/time remain untouched. Reconcile exact response ray IDs only
after durable local ingest. Sampling/retention and laptop gaps remain coverage
limitations. Native nonidentity client IDs are service accounts, barred from
human identity mapping. No High/Medium/Low or compromise inference is enabled.

Existing frozen AWS profile, ledger, schedule, method and scenarios remain
unchanged. This new stream is not silently added to the AWS reserved study or
CLUE training/calibration. One human+one GitHub bot still cannot become six
linked human users by assigning six profile labels. Resource/action variety
remains narrow: one Cloudflare app, mostly login-kind events.
