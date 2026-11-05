# Judge-style dashboard walkthrough (Claude → Codex, 4 Nov 2026)

**Target:** preview dashboard `http://127.0.0.1:3011` with API `127.0.0.1:8015`.
**Owner of the fixes:** Codex (dashboard and runtime).

**Method:**
- Read-only. Only one finding drawer (#52) was opened and closed.
- No case was created, no note added and no status changed.
- Pages checked: Overview, Work queue, the drawer, Entities, Connections.
- No console errors. The single 404 came from a URL I typed (`/workspace/overview`).

This note deliberately does **not** repeat the leaked values.

## 🔴 Blockers for the competition demo (live data required, 25–26 Nov)

### D1. The preview shows a stale snapshot, not live data

- The header reads "workspace preview · isolated data copy".
- Connections reads "Operational snapshot: 31/10/2026, 19:25:44 MYT". Its event counts are
  AWS 3040, Cloudflare 6 and GitHub 70.
- The newest finding is 30 Oct.
- AWS "Today (2026-10-31) … 16 missed" is displayed. A judge sees the 31 Oct outage and none of
  the 1–4 Nov days, which are 100% verified for AWS.
- **Ask:** for the demo, serve current data, either from the live store or with a scheduled
  refresh of the copy.
  - Any snapshot-derived "Today" line must show its capture date prominently as recorded, never
    as today. This is B1.11.
- "Refresh snapshot" reloads the same 31 Oct capture. Decide whether the copy should be
  re-captured; that involves the case-writer switch, which is your call.

### D2. Privacy leaks on screen (B1.9; project rule: no real account IDs, emails or IPs)

| Where | What leaks |
|---|---|
| Work queue titles #12 and #33, "Multi-signal anomaly: 4 rarity flags fired for …" | The raw 12-digit AWS account ID |
| Work queue titles #29 and #35 | A raw IAM role unique ID (`AROA…:resource-explorer-2`) |
| Entities → Accounts, Cloudflare Access row | The user's full email address as the account name |
| Entities and Work queue #30 | The user's GitHub username (owner may accept; decide explicitly) |

- **Likely cause (not traced in code):** the rarity "multi-signal" title seems to embed the raw
  entity key when the finding is created. The Account column is already aliased, but the title
  is not.
- **Ask:** mask or alias at display, in one shared formatter used by titles, Account cells and
  Entities. Reuse the same aliasing that produces "Cloudflare service 9692e242" and "AWS root".
  This also covers C11 F1 (`key.scope` in receipts).

## 🟡 Quality, as seen by a judge

- **D3.** All 33 open findings are "High", and about 25 are "First-seen action outside the UTC
  rule window", repeated per persona. This reads as alert fatigue, the problem UEBA claims to
  reduce.
  - Consider grouping repeats per rule and day, or showing why each is High.
  - Do not retune rules without the usual protocol.
- **D4.** Finding #10 has an empty Account cell.
- **D5.** The "UTC rule window" label sits next to MYT timestamps. This is consistent with the
  design (two after-hours windows), but a judge needs a one-line hint, for example "rule window
  07:00–19:00 UTC = 15:00–03:00 MYT".

## ✅ Working, and good for the demo

- **Finding drawer:** account, rule window, event time, action, resource, plus "novelty alone does
  not establish misuse".
- **Diagnostic panel** under "Account-day diagnostic context":
  - it loads the **4 Nov 08:25 MYT** receipt, so `Argus-Diagnostic-Refresh` is working (C11 F2);
  - it shows "Insufficient history: 0 of 5 usable prior days" instead of a score (B1.8 pass).
- **Overview** states "Model scoring is not enabled in this workspace preview" (B1.10).
- **Connections** wording on unresolved and missed receipts is honest and needs no change.

## Suggested order

1. D2 (masking).
2. D1 (live data, before about 18 Nov, so B1 can run on 18–22 Nov).
3. D4.
4. D3 and D5 if time allows.

Claude can rerun this walkthrough after the fixes.

## Addendum, 5 Nov 2026: automated check

New script: `scripts/b1_acceptance_check.py` (read-only GETs, local API only). Run it with:

```bash
python scripts/b1_acceptance_check.py --base http://127.0.0.1:8015
```

It exits 1 on any FAIL. Use it to verify D2 after the fix.

**D1 update:** the copy was re-captured at 4 Nov 20:18 MYT. The 4 Nov counts on Connections are
now current for that capture.

**D2 is wider than the walkthrough showed.** The 9:38 MYT run found **18 leaks** in display
fields:
- security findings #12, #29, #33 and #35 (`display_title`);
- observations #3, #6, #7, #17, #19, #21, #23, #25 and #27:
  - `display_title`;
  - for #3, also `account_label`, which carries the email;
- case `d8edd672…`: its `notes` contain an AWS unique ID;
- `/workspace/accounts` and `/workspace/people` labels, which contain the email.

Raw `title` is skipped wherever `display_title` exists, because the UI renders `display_title`.

**Other results:**
- B1.10 passes: no risk tier, no live activation, no model-origin findings.
- B1.1 is WARN only because the data is a snapshot.

**D5 appears fixed:** `rule_window` now includes the MYT conversion.

## Correction, 5 Nov 2026: D2 and D4 withdrawn (Claude, with the user's approval to act on Codex items)

### D2 was a Claude test error, not a dashboard defect

- The walkthrough and the first B1 run had **Presentation mode off**.
- With it on, `maskText` hides every leak kind. I checked the rendered text of:
  - the 8 list pages;
  - findings #3, #33 and #35 with every `details` element expanded;
  - all 9 case pages;
  - the People approval evidence.
- Result: **0 account IDs, AWS unique IDs, emails or IPs.**
- The API keeping native IDs is the documented design ("Visual masking only").
- **No dashboard code was changed.**

### D4 is already fixed in the current copy

Finding #10 now shows "Account unavailable".

### B1 script corrected

B1.9 now passes the display fields through the frontend's own
`workspace_next/frontend/lib/presentationPrivacy.mjs` `maskText` (via node) and fails only if
anything survives the masking.
- If node is missing, the result is MANUAL.
- Current result: **PASS**. All 18 raw display fields that carry native IDs are masked.
- Tests: 10.

### Still open: a decision for the user, not a defect

- Presentation mode is **read-only** by design: it hides forms and blocks writes.
- So a masked live demo cannot show case create, note or close (B1.6/B1.7) on screen.
- Options:
  - run the case workflow with masking off, on non-sensitive records only;
  - pre-record the workflow and show it in Presentation mode;
  - (Codex) allow writes in Presentation mode with masked inputs. This is riskier, because masked
    text could be saved into case records.
