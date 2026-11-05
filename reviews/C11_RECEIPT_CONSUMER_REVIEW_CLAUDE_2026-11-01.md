# C11: independent receipt-consumer tests and review (Claude, 1 Nov 2026)

**Target:** `workspace_next/diagnostic_receipts.py` against
`docs/LIVE_DIAGNOSTIC_RECEIPT_CONSUMER_CONTRACT_V1.md`.
- The consumer was not edited.
- Synthetic artifacts only: random-weight models, synthetic events, no real store, archive or
  provider.

## Method: producer → consumer round trip

New file: `scripts/tests/test_c11_receipt_consumer_roundtrip.py`, **28 tests, all passing**.
- Claude's real generator (`live_receipts_clue_v2.run` / `build_receipts`) writes the artifact.
  The consumer must accept it unchanged.
- Each negative case applies **one** corruption and then re-seals the body hash, counts and
  receipt IDs. Each case therefore reaches its own check, and the test asserts the exact
  `ReceiptError.code`, not just "some error".
- The provenance uses the current source hashes, so live-mode source verification really runs.

**Accepted as intended:**
- valid v2 output;
- explicit legacy v1;
- a scored day (`diagnostic`) and a cold-start day (`unscored`);
- a zero-event gap day (`unscored`, `observed_events` 0);
- more than 28 accepted days: expanding has 34, rolling the last 28;
- stale output in `recorded_mode`.

**Missing data stays missing:**
- An absent account, or another source for the same account and day, returns `unavailable`
  with no receipt and no score.
- A malformed query raises `invalid_query`.

**Rejected with the right code:**

| Corruption | Code |
|---|---|
| Risk tier or alert set | `activation_not_allowed` |
| Score forged onto a cold-start or coverage-incomplete day | `ineligible_score` |
| Negative term; MSE/additive mismatch; share mismatch | `invalid_terms` |
| NaN | `invalid_json` |
| Rolling list not the last ≤28; history date after the receipt day | `invalid_history` |
| Missing `why_unscored` | `missing_reason` |
| Altered row cut-off | `receipt_binding_mismatch` |
| Wrong source or malformed account | `invalid_key` |
| Day not yet closed | `open_day` |
| Duplicate account-day | `duplicate_key` |
| Key changed without a new ID | `receipt_id_mismatch` |
| Body tampering | `receipts_hash_mismatch` |
| Manifest tampering | `manifest_hash_mismatch` |
| Scored-count mismatch | `receipt_count_mismatch` |
| v3 schema | `unsupported_schema` |
| Model, policy or projection pin mismatch | `provenance_mismatch` |
| Stale code hash or path escaping the checkout (live mode) | `source_binding_mismatch` |
| Output stale beyond 48 h; cut-off in the future | `stale_artifact` / `future_cutoff` |

## Real artifact check

`live-receipts-20261101-022339` (v2, 63 receipts) loads in **live** mode and in recorded mode.
- Taking the trust inputs from its own manifest was done for this check only. Production pins
  must stay external.
- None of the receipt-bound sources have changed since it was generated, so X9's projection is
  already included. No regeneration is needed yet.

## Findings

**No consumer defects.** Every contract rule I tested behaves as specified.

**F1. Raw AWS account ID reaches the UI. Privacy; for X8 display.**
- All 51 AWS receipts carry the raw **12-digit AWS account ID** as `key.scope`.
- `lookup()` returns the receipt unchanged, and nothing in `workspace_next/` masks it.
- The project rule is never to show real account IDs, so the panel must mask or alias `scope`
  before display.
- Receipts also carry `verified_native_event_ids`. These are not secret, but treat them as
  drawer detail only.
- Masking belongs in display. The producer cannot drop `scope`, because it is part of the
  identity key.

**F2. Live mode needs a receipt run at least every 48 hours. Operational; for the live demo.**
- The receipts are currently generated only when a Claude session runs them by hand.
- For live data during the competition, X10 needs an installed scheduled receipt job, for
  example daily after the daily check. It would call
  `scripts/live_receipts_clue_v2.py` with fresh output paths and an external pin update.
- Otherwise the panel will show `stale_artifact` or must fall back to recorded mode.
- Claude owns the generator; the scheduling belongs to the runtime owner.
