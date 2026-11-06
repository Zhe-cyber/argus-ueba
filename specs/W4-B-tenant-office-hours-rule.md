# Spec W4-B: company-time office-hours rule (post-collection)

**Status:** approved in principle by the user on 5 Nov 2026. **Do not implement before
collection ends:** `backend/` is pinned until the AWS V3 study closes on 16 Nov.
**Target date:** implement and deploy 16–17 Nov, after C4/A2, so B1 (18–22 Nov) and the
competition (25 Nov) use it.

## Problem

`backend/rarity_scorer.py` flags `off_hours` outside Mon–Fri 07:00–19:00 **UTC**, which is
15:00–03:00 MYT. Normal Malaysian office mornings (08:00–15:00 MYT) are therefore "off-hours".
Combined with `first_time_action`, this raises the High `anomalous_behavior` rule finding
(`backend/main.py:1095`). A panel reads this as a basic error.

## Change

1. **`rarity_scorer.py`:**
   - Evaluate `off_hours` in the company time zone.
   - Add `ARGUS_TENANT_TZ` (default `Asia/Kuala_Lumpur`) and `ARGUS_OFFICE_HOURS` (default
     `8-18`, end exclusive).
   - Weekends are evaluated in local time.
2. **`main.py:1098` title:** "First-time action outside office hours (MYT) for …". The time-zone
   abbreviation comes from the setting.
3. **`workspace_next/finding_context.py`:**
   - Findings created after the change: `display_title` "First-seen action outside office hours
     (MYT)", and `rule_window` states the local window.
   - Older findings keep the current UTC wording (they were raised under the old rule) and the
     MYT context line added on 5 Nov.
   - Decide old versus new by `created_at` against the deploy cut-over, recorded in config.
4. **Must NOT change:**
   - `scripts/clue_features.py` `utc_off_hours_events` (frozen W33 feature);
   - `backend/feature_extractor.py` `_BIZ_START/_BIZ_END` (frozen AE contract);
   - anything in `RECEIPT_SOURCES` or `EVALUATOR_SOURCES`;
   - recorded severities of existing findings.

## Tests

- `off_hours` at the boundaries 07:59, 08:00, 17:59 and 18:00 MYT; Saturday 10:00 MYT; and a UTC
  Friday-night event that is Saturday in MYT.
- A non-default `ARGUS_TENANT_TZ` (for example `Europe/London`).
- Title wording; `display_title` old versus new by cut-over.
- Full `scripts/tests` and the backend tests with `DATABASE_URL=sqlite-local`.

## Evidence and reporting

- Record the cut-over time.
- Report the alert counts for the same week before and after, as descriptive only, never as a
  tuning result.
- The pre-deploy UTC findings stay in the report as they were recorded.

## Review

Codex review of the `backend/` diff (scoring/ingest path, per `CLAUDE.md`). The evaluator agent
confirms the W33/A2 sources are unchanged.
